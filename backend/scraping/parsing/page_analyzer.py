"""
UMOA Banking Intelligence — Page Analyzer

Analyzes extracted page text for French banking and financial statement terminology.
Produces explainable scores in [0.0, 1.0] for:
  - balance_sheet (Bilan)
  - income_statement (Compte de résultat)
  - cash_flow (Tableau des flux de trésorerie)
  - notes (Annexes / Notes aux états financiers)

NO AI / LLM is used; all scoring is strictly deterministic, explainable, and reproducible.
"""
import re
import unicodedata

from scraping.parsing.models import PageAnalysis

# Keyword dictionaries with weights:
# Weight 2.5+: Strong distinctive statement title or unique line item
# Weight 1.0+: Supporting financial line item
KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "balance_sheet": [
        # Distinctive titles / totals
        ("bilan", 3.0),
        ("total actif", 2.5),
        ("total passif", 2.5),
        ("total de l'actif", 2.5),
        ("total du passif", 2.5),
        ("actif immobilise", 2.0),
        ("actif circulant", 2.0),
        ("capitaux propres", 2.0),
        ("creances sur la clientele", 2.0),
        ("creances sur les etablissements de credit", 2.0),
        ("dettes envers la clientele", 2.0),
        ("depots de la clientele", 2.0),
        ("provisions pour risques et charges", 1.5),
        # Supporting terms
        ("actif", 1.0),
        ("passif", 1.0),
        ("creances", 1.0),
        ("dettes", 1.0),
        ("depots", 1.0),
        ("fonds propres", 1.5),
    ],
    "income_statement": [
        # Distinctive titles / totals
        ("compte de resultat", 3.0),
        ("produit net bancaire", 3.0),
        ("resultat d'exploitation", 2.5),
        ("resultat net", 2.5),
        ("resultat avant impot", 2.5),
        ("charges generales d'exploitation", 2.0),
        ("charges d'exploitation", 2.0),
        ("cout du risque", 2.0),
        ("dotations aux amortissements", 2.0),
        ("produits d'exploitation bancaire", 2.0),
        ("charges d'exploitation bancaire", 2.0),
        # Supporting terms
        ("produits d'interets", 1.5),
        ("charges d'interets", 1.5),
        ("commissions percues", 1.5),
        ("frais de personnel", 1.5),
        ("interets et charges assimilees", 1.5),
        ("interets et produits assimiles", 1.5),
    ],
    "cash_flow": [
        # Distinctive titles / totals
        ("tableau des flux de tresorerie", 3.5),
        ("flux de tresorerie", 3.0),
        ("activites d'exploitation", 2.0),
        ("activites d'investissement", 2.0),
        ("activites de financement", 2.0),
        ("variation nette de la tresorerie", 2.5),
        ("tresorerie a l'ouverture", 2.0),
        ("tresorerie a la cloture", 2.0),
        ("flux net de tresorerie", 2.5),
        # Supporting terms
        ("tresorerie nette", 1.5),
        ("decaissements", 1.0),
        ("encaissements", 1.0),
    ],
    "notes": [
        # Distinctive titles
        ("notes aux etats financiers", 3.0),
        ("notes annexes", 3.0),
        ("annexes aux etats financiers", 3.0),
        ("informations complementaires", 2.5),
        ("principes et methodes comptables", 2.5),
        ("regles et methodes comptables", 2.5),
        ("note 1", 1.5),
        ("note 2", 1.5),
        ("note 3", 1.5),
        # Supporting terms
        ("annexes", 1.0),
        ("referentiel comptable", 1.5),
        ("engagements hors bilan", 1.5),
    ],
}


def normalize_for_matching(text: str) -> str:
    """Normalize text for accent-insensitive, punctuation-tolerant keyword lookup."""
    # Remove accents using NFKD decomposition
    normalized = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    # Lowercase and replace non-alphanumeric chars (except spaces/apostrophes) with spaces
    normalized = re.sub(r"[^\w\s']", " ", normalized.lower())
    # Collapse multiple whitespaces
    return " ".join(normalized.split())


class PageAnalyzer:
    """Analyzes page content and computes candidate scores for financial statement types."""

    def __init__(self, threshold_candidate: float = 0.35) -> None:
        self.threshold_candidate = threshold_candidate

    def analyze_page(self, page_number: int, text: str) -> PageAnalysis:
        """
        Analyze a single page and produce category scores and matched terms.

        Args:
            page_number: 1-indexed page number.
            text: Normalized text content of the page.

        Returns:
            PageAnalysis with scores for each category.
        """
        if not text or not text.strip():
            return PageAnalysis(
                page_number=page_number,
                categories={cat: 0.0 for cat in KEYWORDS},
                matched_terms=[],
                is_financial_statement_candidate=False,
                detected_statement_type=None,
            )

        norm_text = normalize_for_matching(text)
        categories_scores: dict[str, float] = {}
        all_matched: list[str] = []

        # Check if the title of the page (first ~3 lines) contains statement names
        first_lines = "\n".join(text.split("\n")[:4])
        norm_header = normalize_for_matching(first_lines)

        for category, keyword_list in KEYWORDS.items():
            category_score = 0.0
            cat_matched = []

            for term, weight in keyword_list:
                # Word boundary check for short terms, substring for multi-word phrases
                if " " in term:
                    found = term in norm_text
                else:
                    found = bool(re.search(rf"\b{re.escape(term)}\b", norm_text))

                if found:
                    category_score += weight
                    cat_matched.append(term)
                    # Extra bonus if found in page header / title
                    if term in norm_header:
                        category_score += 1.0

            all_matched.extend(cat_matched)

            # Explainable monotonic normalization: 6.0 raw score points ~ 1.0 max score
            # Score formula: min(1.0, round(raw_score / 6.0, 2))
            norm_score = min(1.0, round(category_score / 6.0, 2))
            categories_scores[category] = norm_score

        # Determine if this page is a financial statement candidate
        best_category: str | None = None
        best_score = 0.0

        for cat, score in categories_scores.items():
            if score > best_score:
                best_score = score
                best_category = cat

        is_candidate = best_score >= self.threshold_candidate

        return PageAnalysis(
            page_number=page_number,
            categories=categories_scores,
            matched_terms=sorted(set(all_matched)),
            is_financial_statement_candidate=is_candidate,
            detected_statement_type=best_category if is_candidate else None,
        )
