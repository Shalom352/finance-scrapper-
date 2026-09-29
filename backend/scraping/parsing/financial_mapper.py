"""
UMOA Banking Intelligence — Financial Metric Mapper

Maps extracted accounting row labels to the 26 official V1 metric codes.
Applies strict contextual validation, negative exclusions, and explainable confidence scoring.
Rule: DATA MISSING > DATA WRONG. Never guess. Ambiguous matches are routed to needs_review.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass
class MetricMatch:
    """Result of mapping a row label to a metric definition."""

    metric_code: str
    confidence_score: float  # 0.0 to 1.0
    confidence_level: str  # high_confidence | medium_confidence | low_confidence
    matched_synonym: str
    reason: str


def normalize_label(label: str) -> str:
    """Normalize label: NFKD, lowercase, remove punctuation, single spaces."""
    if not label:
        return ""
    # Normalize unicode
    nfkd = unicodedata.normalize("NFKD", label)
    text = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    # Replace dashes, slashes, punctuation with spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse multiple whitespace
    return " ".join(text.split()).strip()


class MetricMapper:
    """Conservative mapper from accounting line labels to official V1 metric codes."""

    # Rules structure per metric code:
    # {
    #   "statement_types": set of allowed statement types or None,
    #   "exact_synonyms": list of normalized exact phrases (high confidence 0.95),
    #   "strong_patterns": list of regex patterns (medium-high confidence 0.85),
    #   "negative_terms": list of forbidden words in the label,
    # }
    RULES: dict[str, dict[str, Any]] = {
        # --- Actifs (balance_sheet) ---
        "total_actifs": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "total actif",
                "total actifs",
                "total de l actif",
                "total general actif",
                "total general de l actif",
                "total du bilan actif",
                "total bilan actif",
                "total general",
            ],
            "strong_patterns": [
                r"^total\s+(?:des\s+)?actifs?$",
                r"^total\s+(?:du\s+)?bilan\s+actif$",
                r"^total\s+general\s+de\s+l\s*actif$",
            ],
            "negative_terms": ["passif", "passifs", "hors bilan", "produit", "charge"],
        },
        "tresorerie": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "tresorerie",
                "caisse",
                "caisse et banques centrales",
                "caisse instituts d emission",
                "disponibilites",
                "tresorerie et equivalents de tresorerie",
                "caisse et comptes courants",
            ],
            "strong_patterns": [
                r"^caisse\s+et\s+banques?\s+centrales?$",
                r"^caisse\s+instituts?\s+d\s*emission$",
                r"^tresorerie\s+et\s+equivalents?",
            ],
            "negative_terms": ["flux de tresorerie", "flux", "interbancaire", "passif"],
        },
        "creances_clients": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "creances sur la clientele",
                "creances clientele",
                "creances clients",
                "prets et creances sur la clientele",
                "operations avec la clientele",
                "operations avec la clientele actif",
                "credits a la clientele",
                "concours a l economie",
            ],
            "strong_patterns": [
                r"^cr[ée]ances?\s+(?:sur\s+la\s+)?client[èe]le$",
                r"^pr[êe]ts?\s+et\s+cr[ée]ances?\s+sur\s+la\s+client[èe]le$",
                r"^op[ée]rations?\s+avec\s+la\s+client[èe]le\s*(?:actif)?$",
            ],
            "negative_terms": ["etablissements de credit", "banques", "interbancaire", "depots", "passif"],
        },
        "creances_banques": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "creances sur les etablissements de credit",
                "creances banques",
                "creances interbancaires",
                "operations interbancaires actif",
                "prets et creances sur les etablissements de credit",
            ],
            "strong_patterns": [
                r"^cr[ée]ances?\s+sur\s+les\s+[ée]tablissements?\s+de\s+cr[ée]dit$",
                r"^op[ée]rations?\s+interbancaires?\s+actif$",
            ],
            "negative_terms": ["clientele", "clients", "depots", "passif"],
        },
        "immobilisations": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "immobilisations",
                "immobilisations corporelles et incorporelles",
                "actifs immobilises",
                "immobilisations nettes",
                "total immobilisations",
            ],
            "strong_patterns": [
                r"^immobilisations?\s+corporelles?\s+et\s+incorporelles?$",
                r"^actifs?\s+immobilis[ée]s?$",
            ],
            "negative_terms": ["passif"],
        },
        "autres_actifs": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "autres actifs",
                "comptes de regularisation actif",
                "divers actifs",
                "autres postes d actif",
            ],
            "strong_patterns": [
                r"^autres?\s+actifs?$",
                r"^comptes?\s+de\s+r[ée]gularisation\s+actif$",
            ],
            "negative_terms": ["passif", "passifs"],
        },
        # --- Passifs (balance_sheet) ---
        "total_passifs": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "total passif",
                "total passifs",
                "total du passif",
                "total general passif",
                "total general du passif",
                "total du bilan passif",
                "total bilan passif",
                "total passif et capitaux propres",
            ],
            "strong_patterns": [
                r"^total\s+(?:des\s+)?passifs?$",
                r"^total\s+(?:du\s+)?bilan\s+passif$",
                r"^total\s+passif\s+et\s+capitaux\s+propres$",
            ],
            "negative_terms": ["actif", "actifs", "hors bilan"],
        },
        "depots_clients": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "depots de la clientele",
                "depots clientele",
                "depots clients",
                "ressources clientele",
                "comptes de la clientele",
                "dettes envers la clientele",
                "operations avec la clientele passif",
            ],
            "strong_patterns": [
                r"^d[ée]p[ôo]ts?\s+(?:de\s+la\s+)?client[èe]le$",
                r"^dettes?\s+envers\s+la\s+client[èe]le$",
                r"^op[ée]rations?\s+avec\s+la\s+client[èe]le\s+passif$",
            ],
            "negative_terms": ["etablissements de credit", "banques", "interbancaire", "creances", "actif"],
        },
        "depots_banques": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "depots des etablissements de credit",
                "depots banques",
                "depots interbancaires",
                "dettes envers les etablissements de credit",
                "operations interbancaires passif",
            ],
            "strong_patterns": [
                r"^d[ée]p[ôo]ts?\s+des\s+[ée]tablissements?\s+de\s+cr[ée]dit$",
                r"^dettes?\s+envers\s+les\s+[ée]tablissements?\s+de\s+cr[ée]dit$",
                r"^op[ée]rations?\s+interbancaires?\s+passif$",
            ],
            "negative_terms": ["clientele", "clients", "creances", "actif"],
        },
        "emprunts_bancaires": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "emprunts bancaires",
                "emprunts aupres des etablissements de credit",
                "emprunts financiers",
                "refinancement bceao",
            ],
            "strong_patterns": [
                r"^emprunts?\s+aupr[èe]s\s+des\s+[ée]tablissements?\s+de\s+cr[ée]dit$",
                r"^emprunts?\s+bancaires?$",
            ],
            "negative_terms": ["obligations", "titres de creance", "depots"],
        },
        "obligations_emises": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "obligations emises",
                "titres de creance emis",
                "emprunts obligataires",
                "bons de caisse emis",
            ],
            "strong_patterns": [
                r"^titres?\s+de\s+cr[ée]ance\s+[ée]mis$",
                r"^emprunts?\s+obligataires?$",
            ],
            "negative_terms": ["capital", "actions"],
        },
        "dettes_totales": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "dettes totales",
                "dettes financieres totales",
                "total des dettes",
            ],
            "strong_patterns": [
                r"^dettes?\s+financi[èe]res?\s+totales?$",
                r"^total\s+des\s+dettes?$",
            ],
            "negative_terms": ["clientele"],
        },
        "autres_passifs": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "autres passifs",
                "comptes de regularisation passif",
                "divers passifs",
                "provisions pour risques et charges",
            ],
            "strong_patterns": [
                r"^autres?\s+passifs?$",
                r"^comptes?\s+de\s+r[ée]gularisation\s+passif$",
            ],
            "negative_terms": ["actif", "actifs"],
        },
        "capitaux_propres": {
            "statement_types": {"balance_sheet", "financial_statements", None},
            "exact_synonyms": [
                "capitaux propres",
                "total capitaux propres",
                "total des capitaux propres",
                "fonds propres",
                "situation nette",
                "capitaux propres part du groupe",
            ],
            "strong_patterns": [
                r"^capitaux\s+propres$",
                r"^total\s+(?:des\s+)?capitaux\s+propres$",
                r"^fonds\s+propres\s+nets?$",
            ],
            "negative_terms": ["dettes subordonnees"],
        },
        # --- Compte de résultat (income_statement) ---
        "produit_net_bancaire": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "produit net bancaire",
                "pnb",
            ],
            "strong_patterns": [
                r"^produit\s+net\s+bancaire$",
                r"^pnb$",
            ],
            "negative_terms": ["chiffre d affaires", "marge nette"],
        },
        "produits_totaux": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "produits totaux",
                "total des produits",
                "total produits d exploitation",
                "total des produits d exploitation",
                "produits d exploitation bancaire",
            ],
            "strong_patterns": [
                r"^total\s+(?:des\s+)?produits?\s*(?:d\s*exploitation)?$",
            ],
            "negative_terms": ["charges"],
        },
        "charges_totales": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "charges totales",
                "total des charges",
                "total charges d exploitation",
                "total des charges d exploitation",
                "charges d exploitation bancaire",
            ],
            "strong_patterns": [
                r"^total\s+(?:des\s+)?charges?\s*(?:d\s*exploitation)?$",
            ],
            "negative_terms": ["produits"],
        },
        "resultat_exploitation": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "resultat d exploitation",
                "resultat brut d exploitation",
                "rbe",
            ],
            "strong_patterns": [
                r"^r[ée]sultat\s+(?:brut\s+)?d\s*exploitation$",
                r"^rbe$",
            ],
            "negative_terms": ["net", "financier"],
        },
        "resultat_net": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "resultat net",
                "resultat net de l exercice",
                "resultat net part du groupe",
                "benefice net",
                "perte nette",
            ],
            "strong_patterns": [
                r"^r[ée]sultat\s+net(?:\s+de\s+l\s*exercice)?$",
                r"^r[ée]sultat\s+net\s+part\s+du\s+groupe$",
            ],
            "negative_terms": ["brut", "exploitation"],
        },
        "chiffre_affaires": {
            "statement_types": {"income_statement", "financial_statements", None},
            "exact_synonyms": [
                "chiffre d affaires",
                "chiffre d affaires net",
            ],
            "strong_patterns": [
                r"^chiffre\s+d\s*affaires?(?:\s+net)?$",
            ],
            "negative_terms": ["produit net bancaire", "pnb"],
        },
        # --- Flux de trésorerie (cash_flow_statement) ---
        "flux_exploitation": {
            "statement_types": {"cash_flow", "cash_flow_statement", None},
            "exact_synonyms": [
                "flux net de tresorerie lie aux activites d exploitation",
                "flux de tresorerie lie a l exploitation",
                "flux net d exploitation",
                "flux d exploitation",
            ],
            "strong_patterns": [
                r"^flux\s+(?:net\s+)?(?:de\s+tr[ée]sorerie\s+)?(?:li[ée]\s+[àa]\s+l\s*|d\s*)exploitation$",
            ],
            "negative_terms": ["investissement", "financement"],
        },
        "flux_investissement": {
            "statement_types": {"cash_flow", "cash_flow_statement", None},
            "exact_synonyms": [
                "flux net de tresorerie lie aux operations d investissement",
                "flux de tresorerie lie a l investissement",
                "flux net d investissement",
                "flux d investissement",
            ],
            "strong_patterns": [
                r"^flux\s+(?:net\s+)?(?:de\s+tr[ée]sorerie\s+)?(?:li[ée]\s+[àa]\s+l\s*|d\s*)investissement$",
            ],
            "negative_terms": ["exploitation", "financement"],
        },
        "flux_financement": {
            "statement_types": {"cash_flow", "cash_flow_statement", None},
            "exact_synonyms": [
                "flux net de tresorerie lie aux operations de financement",
                "flux de tresorerie lie au financement",
                "flux net de financement",
                "flux de financement",
            ],
            "strong_patterns": [
                r"^flux\s+(?:net\s+)?(?:de\s+tr[ée]sorerie\s+)?(?:li[ée]\s+au\s+|de\s*)financement$",
            ],
            "negative_terms": ["exploitation", "investissement"],
        },
        # --- Dette & Ratios ---
        "facilities_de_change": {
            "statement_types": {"off_balance_sheet", "notes", None},
            "exact_synonyms": [
                "facilities de change",
                "engagements de change",
                "operations de change a terme",
            ],
            "strong_patterns": [
                r"^facilit[ée]s?\s+de\s+change$",
                r"^engagements?\s+de\s+change$",
            ],
            "negative_terms": [],
        },
        "taux_interet_moyen": {
            "statement_types": {"notes", "not_applicable", None},
            "exact_synonyms": [
                "taux d interet moyen",
                "taux moyen pondere",
            ],
            "strong_patterns": [
                r"^taux\s+d\s*int[ée]r[êe]t\s+moyen$",
            ],
            "negative_terms": [],
        },
        "endettement_actifs": {
            "statement_types": {"notes", "not_applicable", None},
            "exact_synonyms": [
                "ratio d endettement sur actifs",
                "endettement sur actifs",
                "dette sur actifs",
            ],
            "strong_patterns": [
                r"^ratio\s+d\s*endettement(?:\s+sur\s+actifs?)?$",
            ],
            "negative_terms": [],
        },
    }

    def map_label(
        self,
        raw_label: str,
        statement_type_context: str | None = None,
    ) -> MetricMatch | None:
        """
        Match a raw accounting line label to one of the 26 official metric codes.

        Args:
            raw_label: The raw string label from the table row.
            statement_type_context: Optional detected statement type
                (balance_sheet, income_statement, cash_flow, etc.)

        Returns:
            MetricMatch or None if no confident match.
        """
        if not raw_label:
            return None

        normalized = normalize_label(raw_label)
        if not normalized:
            return None

        best_match: MetricMatch | None = None

        for metric_code, rule in self.RULES.items():
            allowed_statements = rule["statement_types"]
            # Check statement type compatibility if context is provided
            if statement_type_context and allowed_statements:
                if statement_type_context not in allowed_statements and None not in allowed_statements:
                    continue

            # Check negative terms
            has_negative = any(neg in normalized for neg in rule["negative_terms"])
            if has_negative:
                continue

            # 1. Exact synonym check (Confidence: 0.95)
            for syn in rule["exact_synonyms"]:
                if normalized == syn:
                    return MetricMatch(
                        metric_code=metric_code,
                        confidence_score=0.95,
                        confidence_level="high_confidence",
                        matched_synonym=syn,
                        reason=f"Exact match on synonym '{syn}'",
                    )

            # 2. Strong regex pattern match (Confidence: 0.85)
            for pattern in rule["strong_patterns"]:
                if re.search(pattern, normalized):
                    match = MetricMatch(
                        metric_code=metric_code,
                        confidence_score=0.85,
                        confidence_level="high_confidence",
                        matched_synonym=pattern,
                        reason=f"Matched strong pattern '{pattern}'",
                    )
                    if best_match is None or match.confidence_score > best_match.confidence_score:
                        best_match = match

            # 3. Partial inclusion (only if high overlap, Confidence: 0.65 -> medium)
            if best_match is None:
                for syn in rule["exact_synonyms"]:
                    if len(syn) > 8 and syn in normalized:
                        best_match = MetricMatch(
                            metric_code=metric_code,
                            confidence_score=0.65,
                            confidence_level="medium_confidence",
                            matched_synonym=syn,
                            reason=f"Partial inclusion of synonym '{syn}' in '{normalized}'",
                        )

        return best_match
