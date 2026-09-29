"""
UMOA Banking Intelligence — Institution Resolver

Orchestrates institution name normalization, candidate matching, and confidence evaluation.
Supports loading registered institutions directly from the database or in-memory registry.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.institution import Institution
from scraping.reconciliation.confidence import ConfidenceScorer
from scraping.reconciliation.matcher import InstitutionMatcher
from scraping.reconciliation.models import (
    InstitutionEntity,
    ResolutionResult,
)
from scraping.reconciliation.normalizer import InstitutionNameNormalizer

logger = get_logger(__name__)


class InstitutionResolver:
    """High-level resolver converting raw extracted strings to official institution IDs."""

    def __init__(
        self,
        matcher: InstitutionMatcher | None = None,
        normalizer: InstitutionNameNormalizer | None = None,
        scorer: ConfidenceScorer | None = None,
    ) -> None:
        self.normalizer = normalizer or InstitutionNameNormalizer()
        self.matcher = matcher or InstitutionMatcher(normalizer=self.normalizer)
        self.scorer = scorer or ConfidenceScorer()

    async def load_from_db(self, db: AsyncSession) -> int:
        """
        Query all active registered institutions from the database and populate matcher index.

        Returns:
            Number of institutions loaded into index.
        """
        stmt = (
            select(Institution)
            .options(selectinload(Institution.country))
            .where(Institution.deleted_at.is_(None))
        )
        res = await db.execute(stmt)
        rows = res.scalars().all()

        entities: list[InstitutionEntity] = []
        for r in rows:
            country_code = r.country.code if r.country else "UMOA"
            entities.append(
                InstitutionEntity(
                    id=r.id,
                    name_official=r.name_official,
                    name_commercial=r.name_commercial,
                    country_code=country_code,
                    institution_type=r.institution_type,
                    banking_group_id=r.banking_group_id,
                )
            )

        self.matcher.set_institutions(entities)
        logger.info("reconciliation_index_loaded", count=len(entities))
        return len(entities)

    def resolve(
        self,
        raw_name: str,
        country_hint: str | None = None,
        document_context: str | None = None,
    ) -> ResolutionResult:
        """
        Resolve an extracted bank string to an official institution record.

        Args:
            raw_name: Raw string extracted from document cell or text.
            country_hint: Optional country hint (e.g. 'CI', 'SN').
            document_context: Optional document title or section context.

        Returns:
            ResolutionResult detailing the matched institution or ambiguity.
        """
        if not raw_name or not raw_name.strip():
            return ResolutionResult(
                raw_input="",
                normalized_input="",
                status="no_match",
                confidence_level="no_match",
                notes="Empty input string",
            )

        # 1. Normalization & country extraction
        norm_name, extracted_country = self.normalizer.extract_country_hint(raw_name)
        effective_country = country_hint or extracted_country

        # 2. Match candidates
        candidates = self.matcher.match(raw_name, country_hint=effective_country)

        # 3. Confidence scoring & ambiguity detection
        best_cand, conf_level, status, notes = self.scorer.evaluate(
            candidates=candidates,
            expected_country_code=effective_country,
        )

        if status == "matched" and best_cand:
            return ResolutionResult(
                raw_input=raw_name,
                normalized_input=norm_name,
                institution_id=best_cand.institution_id,
                institution_name=best_cand.name_official,
                country_code=best_cand.country_code,
                confidence_score=best_cand.score,
                confidence_level=conf_level,
                status=status,
                matched_by=best_cand.match_type,
                notes=notes,
                candidates=candidates,
            )
        elif status == "ambiguous":
            # Rule: DATA MISSING > DATA WRONG. Do not assign institution_id automatically when ambiguous.
            return ResolutionResult(
                raw_input=raw_name,
                normalized_input=norm_name,
                institution_id=None,  # Not assigned automatically
                institution_name=best_cand.name_official if best_cand else None,
                country_code=best_cand.country_code if best_cand else None,
                confidence_score=best_cand.score if best_cand else 0.0,
                confidence_level="low_confidence",
                status="ambiguous",
                matched_by=None,
                notes=f"Ambiguous: {notes}",
                candidates=candidates,
            )
        else:
            return ResolutionResult(
                raw_input=raw_name,
                normalized_input=norm_name,
                institution_id=None,
                institution_name=None,
                country_code=None,
                confidence_score=0.0,
                confidence_level="no_match",
                status="no_match",
                matched_by=None,
                notes=notes,
                candidates=candidates,
            )
