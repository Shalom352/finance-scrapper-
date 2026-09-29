"""
UMOA Banking Intelligence — Document Classifier

Classifies documents into canonical document types:
  - annual_report
  - financial_statements
  - regulatory_report
  - statistical_bulletin
  - other
  - unknown

Follows the conservative principle: if confidence is insufficient, returns "unknown"
rather than inventing a classification.
"""
from scraping.parsing.models import PageAnalysis, ParsedPage
from scraping.parsing.page_analyzer import normalize_for_matching


class DocumentClassifier:
    """Classifies document type based on title, cover pages, and statement distribution."""

    # Keywords for document-level classification
    INDICATORS: dict[str, list[tuple[str, float]]] = {
        "annual_report": [
            ("rapport annuel", 3.5),
            ("rapport d'activite", 3.0),
            ("rapport d'activites", 3.0),
            ("rapport de gestion", 2.5),
            ("annual report", 3.0),
            ("rapport financier annuel", 3.5),
            ("exercice clos le", 1.5),
        ],
        "financial_statements": [
            ("etats financiers", 3.5),
            ("comptes annuels", 3.0),
            ("comptes consolides", 3.0),
            ("comptes individuels", 3.0),
            ("plaquette financiere", 3.0),
            ("bilan et compte de resultat", 3.0),
        ],
        "regulatory_report": [
            ("situation bancaire", 3.5),
            ("commission bancaire", 3.0),
            ("supervision bancaire", 3.0),
            ("circulaire", 3.0),
            ("instruction", 3.0),
            ("politique monetaire", 3.0),
            ("surveillance du systeme", 2.5),
            ("rapport de surveillance", 3.0),
        ],
        "statistical_bulletin": [
            ("bulletin des statistiques", 3.5),
            ("bulletin de statistiques", 3.5),
            ("bulletin mensuel", 3.0),
            ("bulletin trimestriel", 3.0),
            ("statistiques monetaires", 3.0),
            ("series statistiques", 2.5),
            ("indicateurs financiers", 2.0),
        ],
    }

    def classify(
        self,
        pages: list[ParsedPage],
        page_analyses: list[PageAnalysis],
        document_title: str | None = None,
        confidence_threshold: float = 0.40,
    ) -> tuple[str, float]:
        """
        Classify document and return (classification, confidence).

        Args:
            pages: List of parsed pages.
            page_analyses: List of page analyses.
            document_title: Optional title from metadata or filename.
            confidence_threshold: Minimum confidence required (otherwise 'unknown').

        Returns:
            Tuple of (document_classification, confidence_score).
        """
        if not pages:
            return "unknown", 0.0

        # Inspect cover / first 5 pages and title
        first_pages_text = "\n".join(p.text for p in pages[:5])
        combined_text = f"{document_title or ''}\n{first_pages_text}"
        norm_combined = normalize_for_matching(combined_text)

        scores: dict[str, float] = {k: 0.0 for k in self.INDICATORS}

        for cat, keyword_list in self.INDICATORS.items():
            for term, weight in keyword_list:
                if term in norm_combined:
                    scores[cat] += weight

        # Evaluate candidate distribution across all pages
        statement_types_found: set[str] = set()
        for analysis in page_analyses:
            if analysis.is_financial_statement_candidate and analysis.detected_statement_type:
                statement_types_found.add(analysis.detected_statement_type)

        # If both balance sheet and income statement exist
        if "balance_sheet" in statement_types_found and "income_statement" in statement_types_found:
            scores["financial_statements"] += 2.0
            scores["annual_report"] += 1.0

        # Normalize raw scores to confidence in [0.0, 1.0]
        # 5.0 points ~ 1.0 confidence
        confidences = {cat: min(1.0, round(score / 5.0, 2)) for cat, score in scores.items()}

        best_category = "unknown"
        best_confidence = 0.0

        for cat, conf in confidences.items():
            if conf > best_confidence:
                best_confidence = conf
                best_category = cat

        if best_confidence < confidence_threshold:
            return "unknown", 0.0

        return best_category, best_confidence
