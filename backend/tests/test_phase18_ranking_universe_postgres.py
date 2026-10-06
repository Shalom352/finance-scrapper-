"""
Ranking universe = members of the CURRENT official reference snapshot (real PostgreSQL).

Seed (fiscal year 2023, total_actifs, annual):
  current snapshot (2026-06-29), CI members:
    V verified 100 + extracted 90 (verified wins) · R reviewed 80 · X extracted 70
    N needs_review 60 · J rejected only · K conflict (extracted 10 vs 20) · M no data
    S scope incoherent (scope individual / consolidation_scope consolidated)
    L observation_level 'group' only
    V is also listed on the UMOA-level snapshot row (same entity, two member lines)
  current snapshot, SN members: SX 10 XOF · SE 5 EUR (heterogeneous currencies)
  older snapshot (2025-12-31), CI: branch Z (extracted 999) — not in the current snapshot
  institution I (insurance), no snapshot at all

Skipped automatically when no PostgreSQL server is reachable.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

YEAR = 2023
CI_MEMBERS = ("V", "R", "X", "N", "J", "K", "M", "S", "L")


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase18_universe_pytest"
    asyncio.run(
        _exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"')
    )
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    ids = asyncio.run(_seed(_async_dsn(params, test_db)))
    yield {"url": _async_dsn(params, test_db), "ids": ids}

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.discovery import ReferenceUniverse, ReferenceUniverseMember
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        countries = {c.code: c for c in (await db.execute(select(Country))).scalars().all()}
        source = (await db.execute(select(Source))).scalars().first()
        doc = Document(title="Fascicule", document_type="annual_report", source_id=source.id,
                       download_status="downloaded", extraction_status="extracted")
        list_new = Document(title="Liste CB-UMOA 2026", document_type="regulatory_report", source_id=source.id,
                            download_status="downloaded", extraction_status="extracted")
        list_old = Document(title="Liste BCEAO 2025", document_type="regulatory_report", source_id=source.id,
                            download_status="downloaded", extraction_status="extracted")
        db.add_all([doc, list_new, list_old])
        await db.flush()

        def universe(document, country, current, ref_date):
            u = ReferenceUniverse(
                universe_code="UMOA.BANKING", entity_class="financial_institution", entity_type="commercial_bank",
                country_id=countries[country].id if country else None, reference_document_id=document.id,
                reference_date=ref_date, is_current=current, status="COMPLETE",
            )
            db.add(u)
            return u

        cur_umoa = universe(list_new, None, True, date(2026, 6, 29))
        cur_ci = universe(list_new, "CI", True, date(2026, 6, 29))
        cur_sn = universe(list_new, "SN", True, date(2026, 6, 29))
        old_ci = universe(list_old, "CI", False, date(2025, 12, 31))
        await db.flush()

        banks: dict[str, Institution] = {}

        def bank(key, country, institution_type="bank", entity_type="commercial_bank"):
            entity = Entity(entity_class="financial_institution", entity_type=entity_type,
                            canonical_name=f"Banque {key}", country_id=countries[country].id, status="active")
            db.add(entity)
            banks[key] = Institution(name_official=f"Banque {key}", institution_type=institution_type,
                                     country_id=countries[country].id, status="active", entity=entity)
            db.add(banks[key])
            return entity

        entities = {k: bank(k, "CI") for k in (*CI_MEMBERS, "Z")}
        entities.update({k: bank(k, "SN") for k in ("SX", "SE")})
        bank("I", "CI", institution_type="insurance", entity_type="insurance_company")
        await db.flush()

        def member(u, key, line):
            db.add(ReferenceUniverseMember(
                universe_id=u.id, category="bank", raw_name=f"Banque {key}", official_name=f"Banque {key}",
                normalized_name=f"BANQUE {key}", registration_number=f"REG {key} {line}", row_index=line,
                entity_id=entities[key].id, resolution_status="matched", resolution_method="registration_number",
            ))

        for n, key in enumerate(CI_MEMBERS, start=1):
            member(cur_ci, key, n)
        member(cur_umoa, "V", 1)  # same entity reached through a second member line
        member(cur_sn, "SX", 1)
        member(cur_sn, "SE", 2)
        member(old_ci, "V", 1)
        member(old_ci, "Z", 2)

        def fd(key, value, *, status="extracted", currency="XOF", scope="individual",
               consolidation_scope="individual", level="entity"):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "analyst"} if status == "verified" else {}
            db.add(FinancialData(
                institution_id=banks[key].id, source_id=source.id, document_id=doc.id, metric_code="total_actifs",
                scope=scope, consolidation_scope=consolidation_scope, observation_level=level,
                period_type="annual", period_year=YEAR, value_original=str(value),
                value_normalized=Decimal(str(value)), currency_normalized=currency,
                extraction_method="pdf_table", status=status, page_number=3, **extra,
            ))

        fd("V", 100, status="verified")
        fd("V", 90)
        fd("R", 80, status="reviewed")
        fd("X", 70)
        fd("N", 60, status="needs_review")
        fd("J", 50, status="rejected")
        fd("K", 10)
        fd("K", 20)
        fd("S", 40, consolidation_scope="consolidated")
        fd("L", 30, level="group")
        fd("SX", 10)
        fd("SE", 5, currency="EUR")
        fd("Z", 999)
        await db.commit()
        ids = {k: v.id for k, v in banks.items()}
    await engine.dispose()
    return ids


@pytest_asyncio.fixture
async def api(pg_db: dict) -> AsyncGenerator[AsyncClient, None]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.session import get_db_session
    from app.main import create_app

    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncGenerator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await engine.dispose()


async def _ranking(api: AsyncClient, country: str) -> dict:
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "period_year": YEAR,
                                                  "country_code": country})
    assert r.status_code == 200, r.text
    return r.json()


def _excluded_sum(ex: dict) -> int:
    return sum(v for k, v in ex.items() if k.startswith("excluded_") and k != "excluded_population")


@pytest.mark.asyncio
async def test_universe_is_the_current_snapshot_without_duplicates(pg_db: dict):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from scraping.rankings.universe import resolve_banking_universe

    engine = create_async_engine(pg_db["url"])
    async with async_sessionmaker(engine)() as db:
        res = await resolve_banking_universe(db, "UMOA")
    await engine.dispose()
    ids = pg_db["ids"]
    member_ids = [inst.id for inst, _ in res.members]
    assert res.source == "reference_universe"
    assert res.reference_date == date(2026, 6, 29)
    assert sorted(member_ids) == sorted(ids[k] for k in (*CI_MEMBERS, "SX", "SE"))
    assert len(member_ids) == len(set(member_ids))  # V listed twice, counted once
    assert res.duplicate_member_lines == 1
    excluded = {x.institution.id: x.reason for x in res.excluded}
    assert excluded == {ids["Z"]: "not_in_current_reference_universe", ids["I"]: "institution_type_not_bank"}


@pytest.mark.asyncio
async def test_ranking_counts_and_explicit_exclusions(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    d = await _ranking(api, "CI")
    assert [(e["rank"], e["institution_name"], e["status"], Decimal(str(e["value"]))) for e in d["items"]] == [
        (1, "Banque V", "verified", Decimal("100")),  # verified > extracted for the same bank
        (2, "Banque R", "reviewed", Decimal("80")),
        (3, "Banque X", "extracted", Decimal("70")),
    ]
    ex = d["exclusions"]
    assert ex["universe_source"] == "reference_universe"
    assert ex["universe_reference_date"] == "2026-06-29"
    assert ex["universe_total"] == 9
    assert ex["eligible_count"] == 3
    assert (ex["excluded_needs_review"], ex["excluded_missing"], ex["excluded_conflict"], ex["excluded_rejected"],
            ex["excluded_scope"], ex["excluded_observation_level"], ex["excluded_currency"],
            ex["excluded_other"]) == (1, 1, 1, 1, 1, 1, 0, 0)
    assert ex["eligible_count"] + _excluded_sum(ex) == ex["universe_total"]
    assert d["coverage"]["expected_count"] == 9

    reasons = {u["institution_id"]: u["reason"] for u in d["unavailable"]}
    assert reasons == {
        ids["N"]: "needs_review", ids["M"]: "missing", ids["K"]: "conflict", ids["J"]: "rejected_only",
        ids["S"]: "scope_incompatible", ids["L"]: "observation_level_incompatible",
    }
    # The branch of the older snapshot and the insurer stay in the database, outside the universe.
    population = {u["institution_id"]: (u["status"], u["reason"]) for u in d["excluded_population"]}
    assert population == {
        ids["Z"]: ("excluded", "not_in_current_reference_universe"),
        ids["I"]: ("excluded", "institution_type_not_bank"),
    }
    assert ex["excluded_population"] == 2
    ranked_or_listed = {e["institution_id"] for e in d["items"]} | set(reasons)
    assert ids["Z"] not in ranked_or_listed and ids["I"] not in ranked_or_listed


@pytest.mark.asyncio
async def test_needs_review_is_never_ranked(api: AsyncClient, pg_db: dict):
    d = await _ranking(api, "CI")
    assert all(e["status"] in ("verified", "reviewed", "extracted") for e in d["items"])
    assert pg_db["ids"]["N"] not in {e["institution_id"] for e in d["items"]}


@pytest.mark.asyncio
async def test_heterogeneous_currency_gives_an_empty_explained_ranking(api: AsyncClient):
    d = await _ranking(api, "SN")
    assert d["status"] == "needs_review" and d["reason"] == "heterogeneous_currency"
    assert d["items"] == []
    ex = d["exclusions"]
    assert (ex["universe_total"], ex["eligible_count"], ex["excluded_currency"]) == (2, 0, 2)
    assert ex["eligible_count"] + _excluded_sum(ex) == ex["universe_total"]


@pytest.mark.asyncio
async def test_umoa_universe_has_no_population_mixing(api: AsyncClient):
    d = await _ranking(api, "UMOA")
    ex = d["exclusions"]
    assert ex["universe_total"] == 11  # 9 CI + 2 SN members, the duplicated line counted once
    assert ex["excluded_population"] == 2
    assert d["status"] == "needs_review" and d["reason"] == "heterogeneous_currency"  # XOF + EUR never mixed
    assert ex["eligible_count"] + _excluded_sum(ex) == ex["universe_total"]


@pytest.mark.asyncio
async def test_no_period_counts_the_universe_as_missing(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "depots_clients", "country_code": "CI"})
    d = r.json()
    assert d["reason"] == "no_period"
    assert (d["exclusions"]["universe_total"], d["exclusions"]["excluded_missing"]) == (9, 9)


@pytest.mark.asyncio
async def test_ranking_reads_only(api: AsyncClient, pg_db: dict):
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.financial_data import FinancialData
    from app.models.institution import Institution

    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine)

    async def snapshot():
        async with maker() as db:
            inst = (await db.execute(select(func.count()).select_from(Institution))).scalar_one()
            rows = (await db.execute(
                select(FinancialData.id, FinancialData.status, FinancialData.value_normalized)
                .order_by(FinancialData.id)
            )).all()
            return inst, rows

    before = await snapshot()
    for country in ("CI", "SN", "UMOA"):
        await _ranking(api, country)
    after = await snapshot()
    await engine.dispose()
    assert before == after
    assert before[0] == 13  # Z (outside the universe) and I are still in `institutions`
