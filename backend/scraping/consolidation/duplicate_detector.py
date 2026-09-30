"""
UMOA Banking Intelligence — Duplicate Detector

Identifies identical and multi-source duplicate financial data observations
using deterministic logical keys without performing destructive operations.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

from scraping.consolidation.models import (
    DuplicateGroup,
    DuplicateType,
    ObservationSummary,
)


class DuplicateDetector:
    """Detects and categorizes potential duplicate observations across documents and sources."""

    @staticmethod
    def observation_from_orm(row: Any) -> ObservationSummary:
        """Convert a FinancialData ORM row (or dict-like object) to ObservationSummary."""
        def safe_str(val: Any) -> str | None:
            if val is None:
                return None
            if isinstance(val, str):
                return val
            if hasattr(val, "_mock_name") or hasattr(val, "_spec_class"):
                return None
            return str(val)

        source_name = safe_str(getattr(row.source, "name", None)) if getattr(row, "source", None) else None
        source_type = safe_str(getattr(row.source, "source_type", None)) if getattr(row, "source", None) else None
        doc_title = safe_str(getattr(row.document, "title", None)) if getattr(row, "document", None) else None

        source_priority = getattr(row.source, "priority", 2) if getattr(row, "source", None) else 2
        try:
            source_priority = int(source_priority)
        except (ValueError, TypeError):
            source_priority = 2

        val_norm = getattr(row, "value_normalized", None)
        if val_norm is not None and not hasattr(val_norm, "_mock_name"):
            val_norm = Decimal(str(val_norm))
        else:
            val_norm = None

        conf = getattr(row, "confidence_score", None)
        if conf is not None and not hasattr(conf, "_mock_name"):
            conf = Decimal(str(conf))
        else:
            conf = None

        metric_code = safe_str(getattr(row, "metric_code", None))
        if not metric_code and hasattr(row, "metric"):
            metric_code = safe_str(getattr(row.metric, "code", None))

        page_no = getattr(row, "page_number", None)
        if page_no is not None and not hasattr(page_no, "_mock_name"):
            try:
                page_no = int(page_no)
            except (ValueError, TypeError):
                page_no = None
        else:
            page_no = None

        return ObservationSummary(
            id=str(getattr(row, "id", "")),
            institution_id=str(getattr(row, "institution_id", "")),
            metric_code=metric_code or "",
            source_id=str(getattr(row, "source_id", "")),
            source_name=source_name,
            source_type=source_type,
            source_priority=source_priority,
            document_id=str(getattr(row, "document_id", "")),
            document_title=doc_title,
            period_year=int(getattr(row, "period_year", 0)),
            period_type=str(getattr(row, "period_type", "annual")),
            period_label=safe_str(getattr(row, "period_label", None)),
            scope=safe_str(getattr(row, "scope", None)),
            value_original=str(getattr(row, "value_original", "")),
            unit_original=safe_str(getattr(row, "unit_original", None)),
            currency_original=safe_str(getattr(row, "currency_original", None)),
            value_normalized=val_norm,
            unit_normalized=safe_str(getattr(row, "unit_normalized", None)),
            currency_normalized=safe_str(getattr(row, "currency_normalized", None)),
            page_number=page_no,
            status=str(getattr(row, "status", "extracted")),
            extraction_method=str(getattr(row, "extraction_method", "pdf_table")),
            confidence_score=conf,
            verified_by=safe_str(getattr(row, "verified_by", None)),
        )

    def detect_duplicates(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[DuplicateGroup]:
        """
        Group observations by logical key and classify duplicate groups.

        Logical Key: (institution_id, metric_code, period_year, period_type, scope)
        Individual and consolidated figures are never grouped together (Phase 13).

        Returns:
            List of DuplicateGroup objects representing groups with 2 or more matching records.
        """
        parsed_obs: list[ObservationSummary] = [
            obs if isinstance(obs, ObservationSummary) else self.observation_from_orm(obs)
            for obs in observations
        ]

        grouped: dict[tuple[str, str, int, str, str | None], list[ObservationSummary]] = defaultdict(list)

        for obs in parsed_obs:
            metric_code = getattr(obs, "metric_code", "")
            if not metric_code and hasattr(obs, "metric"):
                metric_code = getattr(obs.metric, "code", "")

            # If metric_code is still empty, try extracting from raw row if accessible
            key = (obs.institution_id, metric_code, obs.period_year, obs.period_type, obs.scope)
            grouped[key].append(obs)

        duplicates: list[DuplicateGroup] = []

        for (inst_id, metric_code, year, p_type, scope), items in grouped.items():
            if len(items) < 2:
                continue

            logical_key_str = f"{inst_id}:{metric_code}:{year}:{p_type}:{scope}"

            # Check value identity
            first_val = items[0].value_normalized
            values_match = all(
                self._are_values_equal(first_val, it.value_normalized)
                for it in items[1:]
            )

            # Check document origins
            unique_docs = {it.document_id for it in items}

            dup_type: DuplicateType
            if values_match and len(unique_docs) == 1:
                dup_type = "duplicate_identical"
            elif values_match and len(unique_docs) > 1:
                dup_type = "duplicate_different_source"
            else:
                dup_type = "duplicate_potential"

            duplicates.append(
                DuplicateGroup(
                    logical_key=logical_key_str,
                    institution_id=inst_id,
                    metric_code=metric_code,
                    period_year=year,
                    period_type=p_type,
                    duplicate_type=dup_type,
                    count=len(items),
                    observations=items,
                )
            )

        return duplicates

    @staticmethod
    def _are_values_equal(v1: Decimal | None, v2: Decimal | None) -> bool:
        """Evaluate decimal equality with tolerance for floating point representations."""
        if v1 is None and v2 is None:
            return True
        if v1 is None or v2 is None:
            return False
        return abs(v1 - v2) <= Decimal("0.0001")
