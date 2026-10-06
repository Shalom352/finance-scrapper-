"""
Entity & Source Discovery Engine — coverage-driven search loop (Phase 15).

    OFFICIAL REFERENCE (always re-checked) → ENTITY HUB → COVERAGE → GAPS
        → next strategy able to close an open gap → COVERAGE → GAPS → ... → STOP

Stop conditions (recorded on discovery_runs):
  A_UNIVERSE_COVERED      every official line is resolved and no discoverable gap is left;
  B_STRATEGIES_EXHAUSTED  every enabled strategy able to close the remaining gaps has run, and the
                          last full pass brought nothing new (remaining gaps → NOT_FOUND + retry date);
  C_REFERENCE_UNAVAILABLE no self-consistent official list is available → COVERAGE INCOMPLETE;
  SAFETY_CAP_REACHED      technical round cap hit — explicitly NOT a completion.
The loop never stops because "enough" results were found.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import HUMAN_ONLY_GAP_TYPES, UMOA_COUNTRY_CODES
from app.core.logging import get_logger
from app.models.discovery import DiscoveryRound, DiscoveryRun
from scraping.universe.coverage import CoverageSnapshot, compute_coverage
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.gaps import GapQueue
from scraping.universe.http import OfficialFetcher
from scraping.universe.resolution import EntityResolver
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult
from scraping.universe.strategies.institution_documents import (
    BrvmIssuerFilingsStrategy,
    InstitutionDocumentExtractionStrategy,
)
from scraping.universe.strategies.market_and_web import (
    BrvmMarketListingsStrategy,
    OfficialLinksInDocumentsStrategy,
    OfficialWebsiteCrawlStrategy,
    SecondaryVerifiedStrategy,
)
from scraping.universe.strategies.reference_lists import (
    BceaoReferenceListStrategy,
    CbUmoaReferenceListStrategy,
)
from scraping.universe.strategies.regulatory_fascicle import BceaoFascicleStrategy

logger = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def default_strategies() -> list[DiscoveryStrategy]:
    """Ordered by source priority (regulator first, secondary last)."""
    return [
        BceaoReferenceListStrategy(),
        CbUmoaReferenceListStrategy(),
        BceaoFascicleStrategy(),
        # Phase 17: analyse the institution documents already known BEFORE searching for new ones.
        InstitutionDocumentExtractionStrategy(),
        OfficialLinksInDocumentsStrategy(),
        OfficialWebsiteCrawlStrategy(),
        BrvmIssuerFilingsStrategy(),
        BrvmMarketListingsStrategy(),
        SecondaryVerifiedStrategy(),
    ]


class DiscoveryEngine:
    def __init__(
        self,
        strategies: list[DiscoveryStrategy] | None = None,
        fetcher_factory: Callable[[], Any] = OfficialFetcher,
        registrar: DocumentRegistrar | None = None,
        max_rounds: int = 30,
        max_passes: int = 3,
    ) -> None:
        self.strategies = strategies if strategies is not None else default_strategies()
        self.fetcher_factory = fetcher_factory
        self.registrar = registrar
        self.max_rounds = max_rounds
        self.max_passes = max_passes

    @property
    def enabled(self) -> list[DiscoveryStrategy]:
        return [s for s in self.strategies if s.enabled]

    def strategies_by_gap_type(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in self.enabled:
            for gap_type in s.handles:
                out.setdefault(gap_type, []).append(s.code)
        return out

    # ================================================================== run
    async def run(
        self,
        db: AsyncSession,
        *,
        universe_code: str,
        trigger_type: str = "cli",
        country_codes: tuple[str, ...] = UMOA_COUNTRY_CODES,
        target_years: list[int] | None = None,
        options: dict[str, Any] | None = None,
    ) -> DiscoveryRun:
        years = target_years or [utcnow().year - i for i in range(6)]
        run = DiscoveryRun(
            universe_code=universe_code, trigger_type=trigger_type, status="running", started_at=utcnow(),
            parameters={
                "countries": list(country_codes), "target_years": years, "options": options or {},
                "strategies": [{"code": s.code, "enabled": s.enabled, "priority": s.priority,
                                "disabled_reason": s.disabled_reason} for s in self.strategies],
                "max_rounds": self.max_rounds,
            },
        )
        db.add(run)
        await db.commit()
        run_id = run.id  # kept as a plain value: the ORM object may expire after a rollback
        try:
            return await self._execute(db, run_id, universe_code, country_codes, years, options)
        except Exception as err:
            # The run is never left 'running': an interruption (e.g. the database restarted) is recorded.
            logger.error("discovery_run_interrupted", run_id=run_id, error=str(err))
            await db.rollback()
            failed = await db.get(DiscoveryRun, run_id)
            failed.status = "failed"
            failed.finished_at = utcnow()
            failed.stop_reason = f"interrupted: {type(err).__name__}: {str(err)[:500]}"
            await db.commit()
            return failed

    async def _execute(self, db, run_id, universe_code, country_codes, years, options) -> DiscoveryRun:
        run = await db.get(DiscoveryRun, run_id)
        resolver = EntityResolver()
        await resolver.load(db)
        gaps = GapQueue()
        await gaps.reopen_due(db, force=bool((options or {}).get("retry_now")))
        cov = await compute_coverage(db, universe_code)
        run.coverage_before = cov.summary()
        await db.commit()

        round_no = 0
        errors: list[dict[str, Any]] = []
        stop, reason = None, None
        async with self.fetcher_factory() as fetcher:
            ctx = DiscoveryContext(
                db=db, fetcher=fetcher, registrar=self.registrar or DocumentRegistrar(), resolver=resolver, run=run,
                universe_code=universe_code, country_codes=country_codes, target_years=years,
                options={**(options or {}), "_run_id": run_id},
            )
            # ---------------------------------------------- 1. official reference (every run)
            reference_notes = []
            for strategy in [s for s in self.enabled if s.always_run]:
                round_no += 1
                res, cov = await self._round(ctx, strategy, round_no, [], cov, gaps, errors)
                if res.reference_unavailable:
                    reference_notes.append(f"{strategy.code}: {res.reference_reason}")
            if not cov.reference_available:
                stop = "C_REFERENCE_UNAVAILABLE"
                reason = "COVERAGE INCOMPLETE — no self-consistent official list available: " + "; ".join(
                    reference_notes or ["no official list processed"])

            # ---------------------------------------------- 2. gap-driven rounds
            tried: set[str] = set()
            passes, pass_progress = 1, False
            gap_strategies = [s for s in self.enabled if not s.always_run and s.handles]
            discoverable = set(self.strategies_by_gap_type()) - set(HUMAN_ONLY_GAP_TYPES)
            while stop is None:
                open_gaps = await gaps.open_targets(db, discoverable) if discoverable else []
                open_types = {g.gap_type for g in open_gaps}
                if not open_gaps:
                    waiting = await gaps.pending(db, discoverable)
                    complete = cov.expected_total is not None and cov.matched_total >= cov.expected_total
                    if waiting:
                        # Already searched by every applicable strategy: NOT a completion.
                        stop = "B_STRATEGIES_EXHAUSTED"
                        next_retry = min((g.next_attempt_at for g in waiting if g.next_attempt_at), default=None)
                        blocked = sum(1 for g in waiting if g.status == "BLOCKED")
                        reason = (f"{len(waiting)} gaps already searched by every applicable strategy "
                                  f"({len(waiting) - blocked} NOT_FOUND, {blocked} BLOCKED); next retry "
                                  f"{next_retry.isoformat() if next_retry else 'not scheduled'}")
                    elif complete:
                        stop, reason = "A_UNIVERSE_COVERED", "every official line resolved; no discoverable gap left"
                    else:
                        stop = "B_STRATEGIES_EXHAUSTED"
                        reason = "no discoverable gap left but official lines remain unresolved (human review)"
                    break
                candidates = [s for s in gap_strategies if s.code not in tried and s.handles & open_types]
                if not candidates:
                    if pass_progress and passes < self.max_passes:
                        passes += 1
                        tried.clear()
                        pass_progress = False
                        continue
                    stop = "B_STRATEGIES_EXHAUSTED"
                    reason = (f"all {len(tried)} applicable strategies tried over {passes} pass(es); "
                              f"last pass brought no new source/document/data; {len(open_gaps)} gaps remain")
                    break
                if round_no >= self.max_rounds:
                    stop = "SAFETY_CAP_REACHED"
                    reason = f"round cap {self.max_rounds} reached with {len(open_gaps)} open gaps (NOT complete)"
                    break
                strategy = candidates[0]
                targets = [g for g in open_gaps if g.gap_type in strategy.handles]
                round_no += 1
                res, cov = await self._round(ctx, strategy, round_no, targets, cov, gaps, errors)
                tried.add(strategy.code)
                pass_progress = pass_progress or res.progress

        finalize = await gaps.finalize(db, self.strategies_by_gap_type())
        run = await db.get(DiscoveryRun, run_id)
        run.coverage_after = cov.summary()
        run.coverage_after["gap_finalization"] = finalize
        run.stop_condition = stop
        run.stop_reason = reason
        run.errors = errors or None
        run.status = "completed"
        run.finished_at = utcnow()
        await db.commit()
        logger.info("discovery_run_finished", run_id=run.id, stop=stop, rounds=round_no)
        return run

    # ================================================================== one round
    async def _round(
        self, ctx: DiscoveryContext, strategy: DiscoveryStrategy, number: int, targets, cov: CoverageSnapshot,
        gaps: GapQueue, errors: list[dict[str, Any]],
    ) -> tuple[StrategyResult, CoverageSnapshot]:
        db = ctx.db
        started = utcnow()
        before = cov.summary()
        target_ids = [g.id for g in targets]
        try:
            result = await strategy.run(ctx, targets)
            if targets:
                from sqlalchemy import select

                from app.models.discovery import DiscoveryGap

                fresh = (await db.execute(select(DiscoveryGap).where(DiscoveryGap.id.in_(target_ids)))).scalars().all()
                await gaps.record_attempt(db, fresh, strategy.code, result.blocked_entity_ids)
            await db.commit()
        except Exception as err:  # a strategy failure is recorded, never fatal for the loop
            logger.error("discovery_strategy_failed", strategy=strategy.code, error=str(err))
            await db.rollback()
            ctx.run = await db.get(DiscoveryRun, ctx.options["_run_id"])  # re-attach after the rollback
            await ctx.resolver.load(db)
            result = StrategyResult(targets=len(targets))
            result.errors.append({"error": f"{type(err).__name__}: {err}"})
        cov = await compute_coverage(db, ctx.universe_code)
        await gaps.reconcile(db, cov)
        db.add(DiscoveryRound(
            run_id=ctx.options["_run_id"], round_number=number, strategy_code=strategy.code,
            strategy_description=strategy.description, targets_count=result.targets or len(targets),
            sources_found=result.sources_found, new_entities=result.new_entities,
            new_documents=result.new_documents, new_document_links=result.new_document_links,
            new_observations=result.new_observations, started_at=started, finished_at=utcnow(),
            coverage_before=before, coverage_after=cov.summary(), details=_jsonable(result.details),
            errors=result.errors or None,
        ))
        for e in result.errors:
            errors.append({"round": number, "strategy": strategy.code, **e})
        await db.commit()
        return result, cov


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
