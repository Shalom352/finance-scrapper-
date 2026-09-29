"""
UMOA Banking Intelligence — Institution Matcher

Matches normalized institution strings against registered institutions in UMOA.
Combines exact matching, commercial names, canonical aliases, and token overlap.
"""
from scraping.reconciliation.models import InstitutionEntity, MatchCandidate
from scraping.reconciliation.normalizer import InstitutionNameNormalizer

STOP_AND_COUNTRY_TOKENS = {
    "BANQUE", "SOCIETE", "DU", "DE", "LA", "DES", "ET", "L", "D", "EN", "AU", "AUX", "POUR", "LE", "LES",
    "INTERNATIONAL", "INTERNATIONALE", "GROUP", "GROUPE",
    "COTE", "IVOIRE", "SENEGAL", "BURKINA", "FASO", "BENIN", "MALI", "NIGER", "TOGO", "GUINEE", "BISSAU",
    "CI", "SN", "BF", "BJ", "ML", "NE", "TG", "GW", "UMOA", "UEMOA",
}


class InstitutionMatcher:
    """Matches candidate bank strings to registered UMOA institutions."""

    # Built-in canonical aliases mapping normalized alias -> (core_brand, country_code)
    KNOWN_NETWORK_ALIASES: dict[str, tuple[str, str]] = {
        # Société Générale
        "SGCI": ("SOCIETE GENERALE", "CI"),
        "SGBS": ("SOCIETE GENERALE", "SN"),
        "SGBF": ("SOCIETE GENERALE", "BF"),
        "SGBB": ("SOCIETE GENERALE", "BJ"),
        "SG BENIN": ("SOCIETE GENERALE", "BJ"),
        "SG COTE D IVOIRE": ("SOCIETE GENERALE", "CI"),
        "SG SENEGAL": ("SOCIETE GENERALE", "SN"),
        "SG BURKINA FASO": ("SOCIETE GENERALE", "BF"),
        # BICICI / BICIS
        "BICICI": ("BANQUE INTERNATIONALE POUR LE COMMERCE ET L INDUSTRIE", "CI"),
        "BICIS": ("BANQUE INTERNATIONALE POUR LE COMMERCE ET L INDUSTRIE", "SN"),
        # Banque Atlantique
        "BACI": ("BANQUE ATLANTIQUE", "CI"),
        "BASN": ("BANQUE ATLANTIQUE", "SN"),
        "BABF": ("BANQUE ATLANTIQUE", "BF"),
        "BABJ": ("BANQUE ATLANTIQUE", "BJ"),
        "BAML": ("BANQUE ATLANTIQUE", "ML"),
        "BANE": ("BANQUE ATLANTIQUE", "NE"),
        "BATG": ("BANQUE ATLANTIQUE", "TG"),
        # Coris Bank International
        "CBI": ("CORIS BANK INTERNATIONAL", "BF"),
        "CBI BF": ("CORIS BANK INTERNATIONAL", "BF"),
        "CBI CI": ("CORIS BANK INTERNATIONAL", "CI"),
        "CBI SN": ("CORIS BANK INTERNATIONAL", "SN"),
        "CBI ML": ("CORIS BANK INTERNATIONAL", "ML"),
        "CBI BJ": ("CORIS BANK INTERNATIONAL", "BJ"),
        "CBI TG": ("CORIS BANK INTERNATIONAL", "TG"),
        "CBI NE": ("CORIS BANK INTERNATIONAL", "NE"),
        # Bank of Africa (BOA)
        "BOA CI": ("BANK OF AFRICA", "CI"),
        "BOA COTE D IVOIRE": ("BANK OF AFRICA", "CI"),
        "BOA SENEGAL": ("BANK OF AFRICA", "SN"),
        "BOA SN": ("BANK OF AFRICA", "SN"),
        "BOA BENIN": ("BANK OF AFRICA", "BJ"),
        "BOA BJ": ("BANK OF AFRICA", "BJ"),
        "BOA BURKINA": ("BANK OF AFRICA", "BF"),
        "BOA BURKINA FASO": ("BANK OF AFRICA", "BF"),
        "BOA BF": ("BANK OF AFRICA", "BF"),
        "BOA MALI": ("BANK OF AFRICA", "ML"),
        "BOA ML": ("BANK OF AFRICA", "ML"),
        "BOA NIGER": ("BANK OF AFRICA", "NE"),
        "BOA NE": ("BANK OF AFRICA", "NE"),
        "BOA TOGO": ("BANK OF AFRICA", "TG"),
        "BOA TG": ("BANK OF AFRICA", "TG"),
        # SIB, BNI, CBAO
        "SIB": ("SOCIETE IVOIRIENNE DE BANQUE", "CI"),
        "BNI": ("BANQUE NATIONALE D INVESTISSEMENT", "CI"),
        "CBAO": ("CBAO GROUPE ATTIJARIWAFA BANK", "SN"),
        "CBAO ATTIJARIWAFA": ("CBAO GROUPE ATTIJARIWAFA BANK", "SN"),
        # Bridge Bank
        "BRIDGE BANK": ("BRIDGE BANK GROUP", "CI"),
        "BRIDGE BANK GROUP": ("BRIDGE BANK GROUP", "CI"),
        "BBG CI": ("BRIDGE BANK GROUP", "CI"),
    }

    def __init__(
        self,
        institutions: list[InstitutionEntity] | None = None,
        normalizer: InstitutionNameNormalizer | None = None,
    ) -> None:
        self.normalizer = normalizer or InstitutionNameNormalizer()
        self.institutions: list[InstitutionEntity] = institutions or []
        self._index_institutions()

    def set_institutions(self, institutions: list[InstitutionEntity]) -> None:
        """Update or load the institution registry index."""
        self.institutions = institutions
        self._index_institutions()

    def _index_institutions(self) -> None:
        """Pre-normalize names and build lookup maps."""
        self._norm_official_map: dict[str, list[InstitutionEntity]] = {}
        self._norm_commercial_map: dict[str, list[InstitutionEntity]] = {}

        for inst in self.institutions:
            norm_off = self.normalizer.normalize(inst.name_official)
            self._norm_official_map.setdefault(norm_off, []).append(inst)

            if inst.name_commercial:
                norm_comm = self.normalizer.normalize(inst.name_commercial)
                self._norm_commercial_map.setdefault(norm_comm, []).append(inst)

    def match(
        self,
        raw_name: str,
        country_hint: str | None = None,
    ) -> list[MatchCandidate]:
        """
        Find and score matching candidates for a raw extracted name.

        Args:
            raw_name: Extracted institution name string from document.
            country_hint: Optional expected country code (e.g. CI, SN).

        Returns:
            List of MatchCandidate objects scored between 0.0 and 1.0.
        """
        if not raw_name or not raw_name.strip():
            return []

        norm_input, detected_country = self.normalizer.extract_country_hint(raw_name)
        effective_country = country_hint or detected_country

        candidates: list[MatchCandidate] = []
        seen_ids: set[str] = set()

        # Strategy 1: Exact match on normalized official name (Score: 1.0)
        if norm_input in self._norm_official_map:
            for inst in self._norm_official_map[norm_input]:
                candidates.append(
                    MatchCandidate(
                        institution_id=inst.id,
                        name_official=inst.name_official,
                        name_commercial=inst.name_commercial,
                        country_code=inst.country_code,
                        score=1.0,
                        match_type="exact_official",
                        evidence=f"Exact match on official name: '{inst.name_official}'",
                    )
                )
                seen_ids.add(inst.id)

        # Strategy 2: Exact match on normalized commercial name (Score: 0.98)
        if norm_input in self._norm_commercial_map:
            for inst in self._norm_commercial_map[norm_input]:
                if inst.id in seen_ids:
                    continue
                candidates.append(
                    MatchCandidate(
                        institution_id=inst.id,
                        name_official=inst.name_official,
                        name_commercial=inst.name_commercial,
                        country_code=inst.country_code,
                        score=0.98,
                        match_type="exact_commercial",
                        evidence=f"Exact match on commercial name: '{inst.name_commercial}'",
                    )
                )
                seen_ids.add(inst.id)

        # Strategy 3: Known canonical network aliases (Score: 0.95)
        clean_upper = raw_name.strip().upper()
        if clean_upper in self.KNOWN_NETWORK_ALIASES:
            brand, alias_country = self.KNOWN_NETWORK_ALIASES[clean_upper]
            for inst in self.institutions:
                if inst.id in seen_ids:
                    continue
                if inst.country_code == alias_country:
                    norm_off = self.normalizer.normalize(inst.name_official)
                    if brand in norm_off:
                        candidates.append(
                            MatchCandidate(
                                institution_id=inst.id,
                                name_official=inst.name_official,
                                name_commercial=inst.name_commercial,
                                country_code=inst.country_code,
                                score=0.95,
                                match_type="canonical_alias",
                                evidence=f"Matched network alias '{clean_upper}' -> {brand} in {alias_country}",
                            )
                        )
                        seen_ids.add(inst.id)

        # Strategy 4: Brand + Country match (Score: 0.90)
        # e.g. "ECOBANK CI" -> Ecobank Côte d'Ivoire
        if not candidates and effective_country:
            for inst in self.institutions:
                if inst.id in seen_ids:
                    continue
                if inst.country_code != effective_country:
                    continue

                norm_off = self.normalizer.normalize(inst.name_official)
                # Check if core words overlap significantly
                input_words = set(norm_input.split())
                target_words = set(norm_off.split())

                # Remove country words from target for core comparison
                common_meaningful = (input_words & target_words) - {"BANQUE", "SOCIETE", "INTERNATIONAL", "GROUP", "GROUPE"}
                if common_meaningful:
                    jaccard = len(input_words & target_words) / max(1, len(input_words | target_words))
                    if jaccard >= 0.50 or any(len(w) >= 5 for w in common_meaningful):
                        candidates.append(
                            MatchCandidate(
                                institution_id=inst.id,
                                name_official=inst.name_official,
                                name_commercial=inst.name_commercial,
                                country_code=inst.country_code,
                                score=round(0.85 + (0.10 * jaccard), 2),
                                match_type="brand_country_match",
                                evidence=f"Matched core brand in {effective_country} (overlap: {', '.join(common_meaningful)})",
                            )
                        )
                        seen_ids.add(inst.id)

        # Strategy 5: Token overlap fallback
        if not candidates:
            input_tokens = set(norm_input.split()) - STOP_AND_COUNTRY_TOKENS
            if input_tokens:
                for inst in self.institutions:
                    if inst.id in seen_ids:
                        continue

                    norm_off = self.normalizer.normalize(inst.name_official)
                    target_tokens = set(norm_off.split()) - STOP_AND_COUNTRY_TOKENS

                    intersection = input_tokens & target_tokens
                    if intersection:
                        jaccard = len(intersection) / max(1, len(input_tokens | target_tokens))
                        if jaccard >= 0.50:
                            candidates.append(
                                MatchCandidate(
                                    institution_id=inst.id,
                                    name_official=inst.name_official,
                                    name_commercial=inst.name_commercial,
                                    country_code=inst.country_code,
                                    score=round(0.65 + (0.15 * jaccard), 2),
                                    match_type="token_similarity",
                                    evidence=f"Token overlap ({jaccard:.1%}): {', '.join(intersection)}",
                                )
                            )
                            seen_ids.add(inst.id)

        return candidates
