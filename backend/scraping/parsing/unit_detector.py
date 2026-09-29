"""
UMOA Banking Intelligence — Unit & Currency Detector

Extracts explicit currency and scale from financial tables, page text, and document headers.
Enforces documentary evidence: never invents scale or currency without text clues.
"""
import re

from scraping.parsing.table_models import UnitInfo


class UnitDetector:
    """Detects reporting currency and numeric scale from textual context."""

    # Currency patterns with regex and canonical currency codes
    CURRENCY_PATTERNS = [
        (r"\b(?:fcfa|f\s*cfa|xof|francs?\s*cfa)\b", "XOF"),
        (r"\b(?:eur|euros?|€)\b", "EUR"),
        (r"\b(?:usd|dollars?|\$)\b", "USD"),
    ]

    # Scale patterns: (regex, scale, unit_label)
    SCALE_PATTERNS = [
        (
            r"\b(?:en\s+milliards?\s+de\s+(?:fcfa|f\s*cfa|francs?|xof|euros?|dollars?)|en\s+milliards?|milliards?\s+de\s+francs?)\b",
            1_000_000_000,
            "milliards",
        ),
        (
            r"\b(?:en\s+millions?\s+de\s+(?:fcfa|f\s*cfa|francs?|xof|euros?|dollars?)|en\s+millions?|millions?\s+de\s+francs?|m\s*fcfa|mfcfa)\b",
            1_000_000,
            "millions",
        ),
        (
            r"\b(?:en\s+milliers?\s+de\s+(?:fcfa|f\s*cfa|francs?|xof|euros?|dollars?)|en\s+milliers?|milliers?\s+de\s+francs?|k\s*fcfa|kfcfa)\b",
            1_000,
            "milliers",
        ),
        (
            r"\b(?:en\s+unit[ée]s?|en\s+francs?\s+cfa|en\s+fcfa)\b",
            1,
            "unites",
        ),
    ]

    def detect_units(
        self,
        text_context: str,
        table_title: str | None = None,
        header_texts: list[str] | None = None,
    ) -> UnitInfo:
        """
        Detect currency and scale from available text context.

        Args:
            text_context: Text extracted from the candidate page or nearby blocks.
            table_title: Optional title of the extracted table.
            header_texts: Optional column headers.

        Returns:
            UnitInfo containing currency, scale, unit_label, and documentary evidence.
        """
        combined = " ".join([
            table_title or "",
            " ".join(header_texts or []),
            text_context or "",
        ]).strip()

        if not combined:
            return UnitInfo(currency=None, scale=1, unit_label="unites", evidence="No text context provided")

        lower_text = combined.lower()

        # 1. Detect Scale
        detected_scale = 1
        detected_unit_label = "unites"
        scale_evidence = ""

        for pattern, scale, label in self.SCALE_PATTERNS:
            match = re.search(pattern, lower_text)
            if match:
                detected_scale = scale
                detected_unit_label = label
                scale_evidence = match.group(0)
                break

        # 2. Detect Currency
        detected_currency = None
        currency_evidence = ""

        for pattern, curr in self.CURRENCY_PATTERNS:
            match = re.search(pattern, lower_text)
            if match:
                detected_currency = curr
                currency_evidence = match.group(0)
                break

        evidence_parts = []
        if scale_evidence:
            evidence_parts.append(f"scale: '{scale_evidence}' -> {detected_scale}")
        if currency_evidence:
            evidence_parts.append(f"currency: '{currency_evidence}' -> {detected_currency}")

        full_evidence = "; ".join(evidence_parts) if evidence_parts else "Default: scale=1, currency=None"

        return UnitInfo(
            currency=detected_currency,
            scale=detected_scale,
            unit_label=detected_unit_label,
            evidence=full_evidence,
        )
