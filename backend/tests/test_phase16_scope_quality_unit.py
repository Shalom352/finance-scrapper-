"""
Phase 16 — scope evidence (A/B/C/D), scope guard promotion rules, PNB variants, quality flags.
Unit tests: no database, no network. Fixtures are synthetic ("FIXTURE" names).
"""
from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from app.constants.quality import FASCICLE_CONVENTION_REASON
from app.models.financial_data import FinancialData
from scraping.pipeline import SCOPE_NOT_DETECTED_NOTE, scope_guard
from scraping.quality.checks import (
    cross_statement_flags,
    has_blocking_flag,
    merge_flags,
    value_flags,
)
from scraping.quality.scope import DocumentScopeContext, ScopeAssessment, scopes_in
from scraping.universe.fascicle import FascicleParser
from tests.fixtures_phase15 import build_fascicle_pdf, build_text_pdf

BODY = ["TOTAL DE L'ACTIF 1 000 2 000", "CREANCES SUR LA CLIENTELE 500 600", "RESULTAT NET 10 20",
        "FIXTURE BANK ALPHA", "Millions de francs CFA"]


def ctx(pages: list[list[str]], **kw) -> DocumentScopeContext:
    return DocumentScopeContext.from_pdf_bytes(build_text_pdf(pages), **kw)


# =========================================================================== phrase detection
class TestScopePhrases:
    @pytest.mark.parametrize("text,expected", [
        ("ÉTATS FINANCIERS INDIVIDUELS 2023", {"individual"}),
        ("Comptes sociaux de l'exercice 2024", {"individual"}),
        ("Comptes annuels sociaux", {"individual"}),
        ("Situation établie sur base sociale", {"individual"}),
        ("ÉTATS FINANCIERS CONSOLIDÉS AU 31 DÉCEMBRE 2025", {"consolidated"}),
        ("Comptes consolidés résumés", {"consolidated"}),
        ("Bilan consolidé", {"consolidated"}),
        ("Compte de résultat consolidé", {"consolidated"}),
        ("Données sur base consolidée", {"consolidated"}),
        ("CONSOLIDATED FINANCIAL STATEMENTS", {"consolidated"}),
        ("Separate financial statements", {"individual"}),
        ("STANDALONE FINANCIAL STATEMENTS", {"individual"}),
    ])
    def test_french_and_ifrs_english_statement_phrases(self, text, expected):
        assert scopes_in(text) == expected

    @pytest.mark.parametrize("text", [
        "RESERVES CONSOLIDEES ET REPORT A NOUVEAU",
        "RÉSULTAT CONSOLIDÉ PART DU GROUPE",
        "CAPITAL SOCIAL ET PRIMES LIEES",
        "SIEGE SOCIAL : ABIDJAN",
        "FIXTURE BANK — BILAN 2023",
        "",
    ])
    def test_line_items_and_unrelated_words_are_never_evidence(self, text):
        assert scopes_in(text) == set()


# =========================================================================== classes
class TestScopeClasses:
    def test_a_individual_on_the_observation_page(self):
        a = ctx([["FIXTURE BANK ALPHA", "Rapport annuel 2023"],
                 ["ETATS FINANCIERS INDIVIDUELS 2023", *BODY]]).assess(2)
        assert (a.evidence_class, a.scope, a.reason_code) == ("A", "individual", "scope_explicit_page")
        assert a.promotable and "p.2" in a.evidence

    def test_a_consolidated_ifrs_english(self):
        a = ctx([["FIXTURE GROUP"], ["CONSOLIDATED FINANCIAL STATEMENTS 2025", *BODY]]).assess(2)
        assert (a.evidence_class, a.scope) == ("A", "consolidated")

    def test_page_level_separation_of_both_scopes_is_a(self):
        c = ctx([["FIXTURE BANK ALPHA RAPPORT ANNUEL"],
                 ["COMPTES SOCIAUX 2024", *BODY],
                 ["COMPTES CONSOLIDES 2024", *BODY]])
        assert (c.assess(2).evidence_class, c.assess(2).scope) == ("A", "individual")
        assert (c.assess(3).evidence_class, c.assess(3).scope) == ("A", "consolidated")

    def test_b_from_the_title_without_contradiction(self):
        b = ctx([["FIXTURE BANK ALPHA", "COMPTES SOCIAUX DE L'EXERCICE 2024"], ["BILAN 2024", *BODY]]).assess(2)
        assert (b.evidence_class, b.scope, b.reason_code) == ("B", "individual", "scope_explicit_document_title")

    def test_title_contradicted_by_another_page_is_d(self):
        d = ctx([["FIXTURE BANK ALPHA", "COMPTES SOCIAUX 2024"], ["BILAN 2024", *BODY],
                 ["Note: les COMPTES CONSOLIDES du groupe sont publies separement", "x" * 50]]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "scope_conflicting_mentions") and not d.promotable

    def test_page_header_contradicting_the_title_is_d(self):
        d = ctx([["FIXTURE BANK ALPHA", "ETATS FINANCIERS CONSOLIDES 2024"],
                 ["COMPTES SOCIAUX 2024", *BODY]]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "scope_conflicting_mentions")

    def test_both_scopes_on_the_observation_page_is_d(self):
        d = ctx([["FIXTURE"], ["COMPTES SOCIAUX ET COMPTES CONSOLIDES 2024", *BODY]]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "scope_conflicting_mentions")

    def test_scope_stated_on_another_page_only_is_c(self):
        c = ctx([["FIXTURE BANK ALPHA RAPPORT ANNUEL 2024"], ["BILAN 2024", *BODY],
                 ["ETATS FINANCIERS CONSOLIDES - ANNEXES", "x" * 50]]).assess(2)
        assert (c.evidence_class, c.reason_code) == ("C", "scope_mentioned_elsewhere_only")
        assert not c.promotable

    def test_line_item_only_gives_no_evidence(self):
        d = ctx([["FIXTURE HOLDING ETATS FINANCIERS 2025"],
                 ["BILAN 2025", "RESERVES CONSOLIDEES ET REPORT A NOUVEAU -17 925", *BODY]]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "scope_not_stated")

    def test_unreadable_document_is_d_and_never_guessed(self):
        d = ctx([[], []]).assess(1)
        assert (d.evidence_class, d.reason_code, d.scope) == ("D", "document_not_machine_readable", None)

    def test_unreadable_observation_page_is_d(self):
        d = ctx([["FIXTURE BANK ALPHA", "COMPTES SOCIAUX 2024"], []]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "document_not_machine_readable")

    def test_nothing_is_d(self):
        d = ctx([["FIXTURE BANK ALPHA ETATS FINANCIERS 2023"], ["BILAN 2023", *BODY]]).assess(2)
        assert (d.evidence_class, d.reason_code) == ("D", "scope_not_stated")

    def test_fascicle_convention_is_c_including_branches(self):
        pdf = build_fascicle_pdf([
            {"country": "BENIN", "code": "FXB", "kind": "Bilans", "label": "FIXTURE BANK ALPHA BENIN",
             "rows": {"TOTAL DE L'ACTIF": ["1 000", "2 000", "3 000"]}},
            {"country": "BENIN", "code": "FXS", "kind": "Bilans",
             "label": "FIXTURE PARENT BANK, SUCCURSALE DU BENIN",
             "rows": {"TOTAL DE L'ACTIF": ["10", "20", "30"]}},
        ])
        c = DocumentScopeContext.from_pdf_bytes(pdf, convention_reason=FASCICLE_CONVENTION_REASON,
                                                convention_evidence="fixture")
        for page in (1, 2):  # subsidiary page and branch page alike
            a = c.assess(page)
            assert (a.evidence_class, a.reason_code, a.promotable) == ("C", FASCICLE_CONVENTION_REASON, False)


# =========================================================================== promotion rules
A = ScopeAssessment("A", "scope_explicit_page", "individual", "p.2")
B = ScopeAssessment("B", "scope_explicit_document_title", "consolidated", "title")
C = ScopeAssessment("C", FASCICLE_CONVENTION_REASON)
D = ScopeAssessment("D", "scope_not_stated")
D_CONFLICT = ScopeAssessment("D", "scope_conflicting_mentions")
D_UNREADABLE = ScopeAssessment("D", "document_not_machine_readable")


class TestScopeGuardPromotion:
    def test_legacy_behaviour_without_assessment_is_unchanged(self):
        assert scope_guard("extracted", None) == ("needs_review", SCOPE_NOT_DETECTED_NOTE)
        assert scope_guard("verified", "x") == ("needs_review", f"x | {SCOPE_NOT_DETECTED_NOTE}")

    @pytest.mark.parametrize("assessment", [A, B])
    def test_a_and_b_promote_to_extracted_only(self, assessment):
        status, notes = scope_guard("extracted", "fixture", assessment)
        assert status == "extracted" and assessment.reason_code in notes

    @pytest.mark.parametrize("assessment", [C, D, D_CONFLICT, D_UNREADABLE])
    def test_c_and_d_stay_needs_review(self, assessment):
        status, notes = scope_guard("extracted", "fixture", assessment)
        assert status == "needs_review"
        assert (SCOPE_NOT_DETECTED_NOTE if assessment.reason_code == "scope_not_stated"
                else assessment.reason_code) in notes

    def test_extractor_doubt_is_never_overridden_by_scope(self):
        assert scope_guard("needs_review", "ambiguous value", A)[0] == "needs_review"

    def test_blocking_flag_prevents_promotion(self):
        flags = [{"code": "zero_on_structural_metric", "detail": "total_actifs = 0"}]
        status, notes = scope_guard("extracted", None, A, flags)
        assert status == "needs_review" and "blocking quality flag" in notes

    def test_informative_flag_does_not_block(self):
        assert scope_guard("extracted", None, A, [{"code": "negative_equity", "detail": "x"}])[0] == "extracted"

    def test_never_reviewed_or_verified(self):
        for proposed, assessment, flags in itertools.product(
            ("extracted", "needs_review", "reviewed", "verified", "rejected", None),
            (None, A, B, C, D, D_CONFLICT, D_UNREADABLE),
            (None, [{"code": "cross_statement_mismatch"}]),
        ):
            assert scope_guard(proposed, None, assessment, flags)[0] in ("extracted", "needs_review")

    def test_idempotent_notes(self):
        _, once = scope_guard("extracted", "n", C)
        _, twice = scope_guard("extracted", once, C)
        assert once == twice


# =========================================================================== PNB variants
class TestPnbVariants:
    def _page(self, label: str):
        pdf = build_fascicle_pdf([{
            "country": "BURKINA FASO", "code": "FXB", "kind": "Comptes de résultat", "label": "FIXTURE BANK",
            "rows": {label: ["71 746", "78 444", "93 988"], "RESULTAT NET": ["1", "2", "3"]},
        }])
        return FascicleParser().parse_bytes(pdf).pages[0]

    @pytest.mark.parametrize("label", ["PRODUIT NET BANCAIRE", "PRODUITS NET BANCAIRE",
                                       "PRODUIT NET BANCAIRES (1 à 9)"])
    def test_explicit_variants_map_to_the_existing_metric(self, label):
        got = {(v.metric_code, v.year): v.value_millions for v in self._page(label).values}
        assert got[("produit_net_bancaire", 2023)] == Decimal(93988)

    @pytest.mark.parametrize("label", ["PRODUIT NET BANCAIRE AJUSTE", "PRODUITS NETS BANCAIRES DIVERS",
                                       "PRODUIT BANCAIRE"])
    def test_near_misses_are_not_mapped(self, label):
        assert "produit_net_bancaire" not in {v.metric_code for v in self._page(label).values}

    def test_balance_sheet_result_is_read_for_checks_only(self):
        pdf = build_fascicle_pdf([{
            "country": "BENIN", "code": "FXB", "kind": "Bilans", "label": "FIXTURE BANK",
            "rows": {"TOTAL DE L'ACTIF": ["1", "2", "3"], "RESULTAT DE L'EXERCICE (+/-)": ["4", "5", "6"]},
        }])
        page = FascicleParser().parse_bytes(pdf).pages[0]
        assert page.check_values[("balance_sheet_result", 2023)] == Decimal(6)
        assert {v.metric_code for v in page.values} == {"total_actifs"}


# =========================================================================== quality flags
def _row(rid, metric, year, value, original=None) -> FinancialData:
    r = FinancialData(metric_code=metric, period_year=year, period_type="annual",
                      value_original=original if original is not None else str(value),
                      value_normalized=None if value is None else Decimal(value))
    r.id = rid
    return r


class TestQualityFlags:
    def test_structural_zero_and_negative_equity(self):
        rows = [_row("t21", "total_actifs", 2021, 0), _row("t22", "total_actifs", 2022, 5_000_000),
                _row("d22", "depots_clients", 2022, 0), _row("e22", "capitaux_propres", 2022, -1)]
        flags = value_flags(rows)
        assert flags["t21"][0]["code"] == "zero_on_structural_metric"
        assert flags["d22"][0]["code"] == "zero_on_structural_metric"
        assert flags["e22"][0]["code"] == "negative_equity"
        assert "t22" not in flags
        assert [r.value_normalized for r in rows] == [0, 5_000_000, 0, -1]  # values never modified

    def test_cross_statement_mismatch(self):
        rows = [_row("r23", "resultat_net", 2023, 2_908_000_000, "2 908"),
                _row("r22", "resultat_net", 2022, 3_595_000_000, "3 595")]
        flags = cross_statement_flags(rows, {2023: Decimal(2908), 2022: Decimal(3600)})
        assert "r23" not in flags and flags["r22"][0]["code"] == "cross_statement_mismatch"

    def test_merge_is_idempotent_and_blocking_set(self):
        f = [{"code": "negative_equity", "detail": "x"}]
        assert merge_flags(merge_flags(None, f), f) == f
        assert not has_blocking_flag(f)
        assert has_blocking_flag([{"code": "cross_edition_mismatch", "detail": "y"}])
