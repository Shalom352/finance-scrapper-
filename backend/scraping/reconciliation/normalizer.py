"""
UMOA Banking Intelligence — Institution Name Normalizer

Cleans and standardizes extracted bank and financial institution names
while preserving distinguishing identifiers (country codes, entity types, group names).
"""
import re
import unicodedata


class InstitutionNameNormalizer:
    """Normalizes financial institution names for robust, deterministic matching."""

    # UMOA Member States mapping to ISO 3166-1 alpha-2
    COUNTRY_PATTERNS: list[tuple[str, str]] = [
        (r"\b(?:c[ôo]te\s+d\s*['’\s]?\s*ivoire|c\s*\.?\s*i\b)", "CI"),
        (r"\b(?:s[ée]n[ée]gal|s\s*\.?\s*n\b)", "SN"),
        (r"\b(?:burkina\s+faso|burkina|b\s*\.?\s*f\b)", "BF"),
        (r"\b(?:b[ée]nin|b\s*\.?\s*j\b)", "BJ"),
        (r"\b(?:mali|m\s*\.?\s*l\b)", "ML"),
        (r"\b(?:niger|n\s*\.?\s*e\b)", "NE"),
        (r"\b(?:togo|t\s*\.?\s*g\b)", "TG"),
        (r"\b(?:guin[ée]e\s*[- ]\s*bissau|guinea\s*[- ]\s*bissau|g\s*\.?\s*w\b)", "GW"),
    ]

    # Legal forms to strip from the edges of institution names
    LEGAL_FORM_SUFFIXES = [
        r"\b(?:s\.?\s*a\.?\s*r\.?\s*l\.?|sarl)\b",
        r"\b(?:s\.?\s*a\.?\s*s\.?|sas)\b",
        r"\b(?:s\.?\s*a\.?|soci[ée]t[ée]\s+anonyme)\b",
        r"\b(?:succursale(?:\s+de\s+l\s*umoa)?)\b",
    ]

    # Standard abbreviations expansion
    ABBREVIATIONS = [
        (r"\bst[ée]\b", "SOCIETE"),
        (r"\bbqe\b", "BANQUE"),
        (r"\bcie\b", "COMPAGNIE"),
        (r"\bintl\b", "INTERNATIONAL"),
        (r"\bintern\b", "INTERNATIONAL"),
        (r"\bcoop\b", "COOPERATIVE"),
    ]

    def normalize(self, name: str) -> str:
        """
        Normalize an institution name to uppercase, ASCII, without legal suffixes.

        Preserves:
          - Country tokens (CI, SENEGAL, etc.)
          - Distinctive entity types (LEASING, FINANCE, CREDIT)
          - Core brand identifiers (ECOBANK, BOA, SG, etc.)
        """
        if not name:
            return ""

        # 1. Unicode decomposition to remove accents safely
        nfkd = unicodedata.normalize("NFKD", name)
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c)).upper()

        # 2. Expand common abbreviations
        for pattern, replacement in self.ABBREVIATIONS:
            ascii_text = re.sub(pattern, replacement, ascii_text, flags=re.IGNORECASE)

        # 3. Remove punctuation (dots, commas, hyphens, slashes, quotes, brackets)
        cleaned = re.sub(r"[^\w\s]", " ", ascii_text)

        # 4. Remove legal forms from edges (SA, SARL, SAS)
        for suffix_pat in self.LEGAL_FORM_SUFFIXES:
            cleaned = re.sub(suffix_pat, " ", cleaned, flags=re.IGNORECASE)

        # 5. Collapse spaces
        return " ".join(cleaned.split()).strip()

    def extract_country_hint(self, raw_name: str) -> tuple[str, str | None]:
        """
        Detect if an institution name contains an explicit UMOA country reference.

        Returns:
            Tuple of (cleaned_name_without_country_suffix, country_code_or_None).
        """
        if not raw_name:
            return "", None

        detected_country: str | None = None
        nfkd = unicodedata.normalize("NFKD", raw_name)
        ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))

        for pattern, code in self.COUNTRY_PATTERNS:
            if re.search(pattern, ascii_name, flags=re.IGNORECASE):
                detected_country = code
                break

        normalized = self.normalize(raw_name)
        return normalized, detected_country
