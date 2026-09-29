"""
UMOA Banking Intelligence — Reconciliation Confidence Scorer

Defines confidence bands and ambiguity detection rules.
Enforces the strict rule: NO CROSS-BORDER FALSE MATCHES.
"""
from scraping.reconciliation.models import MatchCandidate


class ConfidenceScorer:
    """Evaluates candidates and assigns explainable confidence levels."""

    HIGH_THRESHOLD: float = 0.85
    MEDIUM_THRESHOLD: float = 0.65
    AMBIGUITY_DELTA: float = 0.08

    def evaluate(
        self,
        candidates: list[MatchCandidate],
        expected_country_code: str | None = None,
    ) -> tuple[MatchCandidate | None, str, str, str]:
        """
        Evaluate candidates and return (best_candidate, confidence_level, status, notes).

        Returns:
            Tuple of (
                best_candidate or None,
                confidence_level: 'high_confidence' | 'medium_confidence' | 'low_confidence' | 'no_match',
                status: 'matched' | 'ambiguous' | 'no_match',
                notes: explanation string
            )
        """
        if not candidates:
            return None, "no_match", "no_match", "No candidates found"

        # Filter out candidates with conflicting country if country is expected
        valid_candidates: list[MatchCandidate] = []
        for c in candidates:
            if expected_country_code and c.country_code != expected_country_code:
                # Discard cross-border candidate: NEVER attribute to the wrong country
                continue
            valid_candidates.append(c)

        if not valid_candidates:
            return None, "no_match", "no_match", f"All candidates rejected due to country mismatch (expected {expected_country_code})"

        # Sort candidates by descending score
        valid_candidates.sort(key=lambda c: c.score, reverse=True)
        top = valid_candidates[0]

        # Check for ambiguity among top candidates
        if len(valid_candidates) > 1:
            second = valid_candidates[1]
            if second.institution_id != top.institution_id:
                score_diff = top.score - second.score
                if score_diff < self.AMBIGUITY_DELTA and second.score >= self.MEDIUM_THRESHOLD:
                    # Multiple close matches across different institutions
                    notes = (
                        f"Ambiguous match between '{top.name_official}' ({top.country_code}, score={top.score:.2f}) "
                        f"and '{second.name_official}' ({second.country_code}, score={second.score:.2f})"
                    )
                    return top, "low_confidence", "ambiguous", notes

        # Single or clearly dominating candidate
        if top.score >= self.HIGH_THRESHOLD:
            return top, "high_confidence", "matched", f"High confidence match ({top.match_type}, score={top.score:.2f})"
        elif top.score >= self.MEDIUM_THRESHOLD:
            return top, "medium_confidence", "matched", f"Medium confidence match ({top.match_type}, score={top.score:.2f})"
        else:
            return top, "low_confidence", "no_match", f"Score {top.score:.2f} below acceptance threshold {self.MEDIUM_THRESHOLD}"
