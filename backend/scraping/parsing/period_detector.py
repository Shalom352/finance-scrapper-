"""
UMOA Banking Intelligence — Period Detector

Detects and correlates financial columns with reporting periods and accounting years.
Distinguishes real fiscal years from descriptive labels, notes, variations, and reference columns.
"""
import re

from scraping.parsing.table_models import PeriodColumn


class PeriodDetector:
    """Analyzes table headers and columns to detect period years and types."""

    # Words indicating non-period columns
    NON_PERIOD_TERMS = {
        "libelle",
        "libellé",
        "poste",
        "rubrique",
        "actif",
        "passif",
        "charges",
        "produits",
        "note",
        "notes",
        "ref",
        "réf",
        "reference",
        "variation",
        "var",
        "evolution",
        "évolution",
        "ecart",
        "écart",
        "%",
        "taux",
    }

    # Month names in French
    FRENCH_MONTHS = (
        r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre|d[ée]c)"
    )

    def detect_period_columns(
        self,
        headers: list[str],
        base_document_year: int | None = None,
    ) -> list[PeriodColumn]:
        """
        Identify which columns represent accounting periods.

        Args:
            headers: List of string headers for each column in the table.
            base_document_year: Optional fallback year from document metadata (e.g. 2024).

        Returns:
            List of detected PeriodColumn objects with column_index, period_year,
            and documentary evidence.
        """
        period_columns: list[PeriodColumn] = []

        for col_idx, header in enumerate(headers):
            if not header or not header.strip():
                continue

            clean_header = header.strip()
            lower = clean_header.lower()

            # Skip explicitly non-period columns
            words = set(re.findall(r"\b\w+\b", lower))
            if words and words.issubset(self.NON_PERIOD_TERMS):
                continue
            if "variation" in lower or "evolution" in lower or "évolution" in lower or "écart" in lower:
                continue
            if lower in ("%", "var %", "var.", "notes", "note", "réf", "ref"):
                continue

            # 1. Check for explicit 4-digit year (1990 - 2050): e.g. "2024", "Exercice 2024", "au 31/12/2024"
            year_matches = re.findall(r"\b(19\d\d|20\d\d)\b", clean_header)
            if year_matches:
                # If multiple years mentioned (e.g. "2024/2023"), pick the most prominent or first
                year = int(year_matches[0])
                period_columns.append(
                    PeriodColumn(
                        column_index=col_idx,
                        period_year=year,
                        period_type="annual",
                        period_label=str(year),
                        evidence=f"Explicit year '{year}' found in header: '{clean_header}'",
                    )
                )
                continue

            # 2. Check for French accounting date: "31 décembre 2024", "au 31/12/24", etc.
            date_match = re.search(rf"\b\d{{1,2}}\s+{self.FRENCH_MONTHS}\s+(19\d\d|20\d\d)\b", lower)
            if date_match:
                year = int(date_match.group(1))
                period_columns.append(
                    PeriodColumn(
                        column_index=col_idx,
                        period_year=year,
                        period_type="annual",
                        period_label=str(year),
                        evidence=f"Date '{date_match.group(0)}' found in header: '{clean_header}'",
                    )
                )
                continue

            # Short date: "31/12/24" or "31/12/2024"
            short_date_match = re.search(r"\b\d{1,2}/\d{1,2}/(20\d\d|\d{2})\b", lower)
            if short_date_match:
                raw_yr = short_date_match.group(1)
                year = int(raw_yr) if len(raw_yr) == 4 else int(f"20{raw_yr}")
                period_columns.append(
                    PeriodColumn(
                        column_index=col_idx,
                        period_year=year,
                        period_type="annual",
                        period_label=str(year),
                        evidence=f"Date pattern '{short_date_match.group(0)}' in header: '{clean_header}'",
                    )
                )
                continue

            # 3. Check for relative "N" / "N-1" notation if base_document_year is provided
            if base_document_year:
                if re.fullmatch(r"(?:exercice\s+)?n", lower):
                    period_columns.append(
                        PeriodColumn(
                            column_index=col_idx,
                            period_year=base_document_year,
                            period_type="annual",
                            period_label=str(base_document_year),
                            evidence=f"Relative label 'N' resolved with base year {base_document_year}",
                        )
                    )
                    continue
                if re.fullmatch(r"(?:exercice\s+)?n\s*[-−]\s*1", lower):
                    year = base_document_year - 1
                    period_columns.append(
                        PeriodColumn(
                            column_index=col_idx,
                            period_year=year,
                            period_type="annual",
                            period_label=str(year),
                            evidence=f"Relative label 'N-1' resolved with base year {base_document_year} -> {year}",
                        )
                    )
                    continue

        return period_columns
