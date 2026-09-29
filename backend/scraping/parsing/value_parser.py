"""
UMOA Banking Intelligence — Value Parser

Robust numeric parsing for accounting amounts, percentages, and financial quantities.
Preserves original value representation and flags ambiguous formatting.
"""
import re

from scraping.parsing.table_models import ParsedFinancialValue


class ValueParser:
    """Parses raw text strings into numeric financial values."""

    # Zero / null markers frequently used in French financial statements
    NULL_MARKERS = {"-", "—", "–", "−", "n/a", "na", "nd", "n.d.", "néant", "p.m.", "pm", "."}

    def parse_value(self, raw_str: str) -> ParsedFinancialValue:
        """
        Parse a raw financial string into numeric representation.

        Args:
            raw_str: The raw string extracted from a cell or text block.

        Returns:
            ParsedFinancialValue with original_value, parsed_numeric_value,
            and ambiguity flags.
        """
        if raw_str is None:
            return ParsedFinancialValue(
                original_value="",
                parsed_numeric_value=None,
                is_ambiguous=False,
            )

        original = str(raw_str).strip()
        if not original:
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=None,
                is_ambiguous=False,
            )

        # Check for zero/null representation
        cleaned_lower = original.lower().strip()
        if cleaned_lower in self.NULL_MARKERS:
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=0.0,
                is_ambiguous=False,
            )

        # Strip currency symbols, percentages, or trailing characters for clean evaluation
        clean_text = original.replace("\u00a0", " ").replace("\u202f", " ")
        clean_text = re.sub(r"[FCFA|XOF|EUR|USD|€|\$|%]", "", clean_text, flags=re.IGNORECASE).strip()

        # Check negative markers: (450 000), -450 000, 450 000-
        is_negative = False
        if clean_text.startswith("(") and clean_text.endswith(")"):
            is_negative = True
            clean_text = clean_text[1:-1].strip()
        elif clean_text.startswith("-") or clean_text.startswith("−"):
            is_negative = True
            clean_text = clean_text[1:].strip()
        elif clean_text.endswith("-") or clean_text.endswith("−"):
            is_negative = True
            clean_text = clean_text[:-1].strip()

        # Remove extra whitespace inside number: "1 250 000" -> "1250000"
        no_spaces = re.sub(r"\s+", "", clean_text)

        # If after cleaning nothing is left or not numeric
        if not no_spaces or not re.search(r"\d", no_spaces):
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=None,
                is_ambiguous=True,
                ambiguity_reason="Non-numeric content",
            )

        # Detect ambiguous 3-digit dot or comma: e.g. "1.250" or "1,250"
        # In French banking, "1.250" can mean 1250 (dot as thousands) or 1.250 (dot as decimal).
        # When single separator with exactly 3 digits follows and no other separator exists:
        if re.fullmatch(r"\d{1,3}[.,]\d{3}", no_spaces):
            # Ambiguous: could be thousands separator or 3 decimal places
            # Per Rule 3 & 13: Do not guess, flag as ambiguous
            # We attempt standard integer parsing as most likely in SYSCOHADA (no cents),
            # but mark is_ambiguous = True so it can be routed to needs_review.
            numeric_val = float(re.sub(r"[.,]", "", no_spaces))
            if is_negative:
                numeric_val = -numeric_val
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=numeric_val,
                is_ambiguous=True,
                ambiguity_reason="Ambiguous 3-digit dot/comma separator (possible decimal or thousands)",
            )

        # Case 1: Standard French/European: dot for thousands, comma for decimals: "1.250.000,50" or "1250000,50"
        if "," in no_spaces and "." in no_spaces:
            if no_spaces.rfind(",") > no_spaces.rfind("."):
                # "1.250.000,50" -> 1250000.50
                norm_str = no_spaces.replace(".", "").replace(",", ".")
            else:
                # "1,250,000.50" (Anglo) -> 1250000.50
                norm_str = no_spaces.replace(",", "")
        elif "," in no_spaces:
            parts = no_spaces.split(",")
            # Multiple commas: "1,250,000" -> thousands separator
            if len(parts) > 2:
                norm_str = no_spaces.replace(",", "")
            elif len(parts) == 2:
                # Single comma: "1250,50" (decimal) vs "1,250" (handled in ambiguity check)
                if len(parts[1]) in (1, 2) or len(parts[1]) > 3:
                    norm_str = f"{parts[0]}.{parts[1]}"
                else:
                    # 3 digits was caught above, anything else treated as decimal
                    norm_str = f"{parts[0]}.{parts[1]}"
            else:
                norm_str = no_spaces
        elif "." in no_spaces:
            parts = no_spaces.split(".")
            # Multiple dots: "1.250.000" -> thousands separator
            if len(parts) > 2:
                norm_str = no_spaces.replace(".", "")
            elif len(parts) == 2:
                # Single dot with 1 or 2 digits: "1250.50" -> decimal
                if len(parts[1]) in (1, 2) or len(parts[1]) > 3:
                    norm_str = no_spaces
                else:
                    norm_str = no_spaces.replace(".", "")
            else:
                norm_str = no_spaces
        else:
            # Plain digits with spaces: "1 250 000" -> "1250000"
            norm_str = no_spaces

        try:
            val = float(norm_str)
            if is_negative:
                val = -val
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=val,
                is_ambiguous=False,
            )
        except ValueError:
            return ParsedFinancialValue(
                original_value=original,
                parsed_numeric_value=None,
                is_ambiguous=True,
                ambiguity_reason=f"Failed to convert '{norm_str}' to float",
            )
