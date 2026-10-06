"""
Phase 15 — Entity & Source Discovery Engine: unit tests (no database, no network).

Fixtures are synthetic (tests/fixtures_phase15.py): every name starts with "FIXTURE" and every
registration number with "Z 9", so nothing here can be confused with official data.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.constants.discovery import (
    GAP_TYPES,
    HUMAN_ONLY_GAP_TYPES,
    LINK_ROLE_PRIORITY,
    SOURCE_LIFECYCLE_STATUSES,
    UMOA_COUNTRY_CODES,
)
from scraping.universe.coverage import CountryCoverage, CoverageSnapshot, EntityCoverage, ratio
from scraping.universe.fascicle import FascicleParser, parse_amount
from scraping.universe.gaps import missing_items
from scraping.universe.http import FetchResult
from scraping.universe.names import parse_designation
from scraping.universe.normalize import (
    core_key,
    country_code_for_label,
    country_codes_in,
    name_key,
    normalize_name,
)
from scraping.universe.reference_list import ReferenceListParser, parse_reference_date
from scraping.universe.resolution import EntityResolver, IndexedEntity
from scraping.universe.strategies.base import SearchProvider
from tests.fixtures_phase15 import build_fascicle_pdf, build_reference_list_pdf, fixture_banks

C = UMOA_COUNTRY_CODES


# =========================================================================== normalization
class TestNormalization:
    def test_accents_punctuation_and_case(self):
        assert normalize_name("Société Générale - Côte d’Ivoire") == "SOCIETE GENERALE COTE D IVOIRE"

    def test_branch_marker_is_never_stripped(self):
        assert "SUCCURSALE" in normalize_name("CBAO, GROUPE ATTIJARIWAFA BANK, SUCCURSALE DU BÉNIN")

    def test_name_key_drops_parentheticals_only(self):
        assert name_key("BANK OF AFRICA - BÉNIN (BOA – BÉNIN)") == "BANK OF AFRICA BENIN"

    def test_core_key_drops_country_words(self):
        assert core_key("ECOBANK - CÔTE D'IVOIRE (ECOBANK)") == core_key("Ecobank Cote d'Ivoire") == "ECOBANK"

    @pytest.mark.parametrize("label,code", [
        ("BÉNIN", "BJ"), ("BURKINA ", "BF"), ("CÔTE D'IVOIRE", "CI"), ("GUINEE BISSAU", "GW"),
        ("GUINÉE-BISSAU", "GW"), ("MALI", "ML"), ("NIGER", "NE"), ("SÉNÉGAL", "SN"), ("TOGO", "TG"),
        ("FRANCE", None),
    ])
    def test_country_labels(self, label, code):
        assert country_code_for_label(label) == code

    def test_country_codes_in_text(self):
        assert country_codes_in("CORIS BANK INTERNATIONAL (CBI) BURKINA") == {"BF"}


# =========================================================================== designations
class TestDesignation:
    def test_acronym(self):
        d = parse_designation("BANK OF AFRICA - BÉNIN (BOA – BÉNIN)")
        assert (d.official_name, d.acronym, d.former_names) == ("BANK OF AFRICA - BÉNIN", "BOA – BÉNIN", [])

    def test_former_name(self):
        d = parse_designation("BANGE BANK BÉNIN ex CCEI BANK BÉNIN")
        assert d.official_name == "BANGE BANK BÉNIN" and d.former_names == ["CCEI BANK BÉNIN"]

    def test_former_name_with_acronyms_on_both_sides(self):
        d = parse_designation("AFG BANK MALI (AFG ML) ex BANQUE INTERNATIONALE POUR LE COMMERCE AU MALI (BICI - M)")
        assert d.acronym == "AFG ML"
        assert d.former_names == ["BANQUE INTERNATIONALE POUR LE COMMERCE AU MALI", "BICI - M"]

    def test_former_acronym_inside_parentheses(self):
        d = parse_designation("INTERNATIONAL BUSINESS BANK TOGO (IB BANK TOGO, ex BTCI)")
        assert d.acronym == "IB BANK TOGO" and d.former_names == ["BTCI"]

    def test_uppercase_ex_and_footnote_marker(self):
        d = parse_designation("AFRIKA BANQUE SÉNÉGAL EX BANQUE DE DAKAR*")
        assert d.official_name == "AFRIKA BANQUE SÉNÉGAL" and d.former_names == ["BANQUE DE DAKAR"]
        assert "footnote_marker" in d.flags

    def test_branch_keeps_full_designation_and_parent(self):
        d = parse_designation("SOCIÉTÉ NIGÉRIENNE DE BANK (SONIBANK), SUCCURSALE DU BÉNIN")
        assert d.is_branch_name and d.acronym is None
        assert d.parent_name == "SOCIÉTÉ NIGÉRIENNE DE BANK (SONIBANK)" and d.host_country_text == "BÉNIN"
        assert d.official_name.endswith("SUCCURSALE DU BÉNIN")

    def test_branch_without_comma(self):
        d = parse_designation("BANQUE ATLANTIQUE CÔTE D'IVOIRE SUCCURSALE DE GUINÉE-BISSAU")
        assert d.is_branch_name and d.parent_name == "BANQUE ATLANTIQUE CÔTE D'IVOIRE"

    def test_word_ex_inside_a_word_is_not_a_former_name(self):
        d = parse_designation("FIXTURE EXPORT BANK")
        assert d.official_name == "FIXTURE EXPORT BANK" and d.former_names == []


# =========================================================================== official list parser
class TestReferenceListParser:
    def test_fixture_list_parses_all_countries_and_passes_self_check(self):
        banks = fixture_banks()
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf(banks))
        assert parsed.reference_date == date(2025, 12, 31)
        assert parsed.layout == "bceao_annual_list"
        assert set(parsed.countries) == set(C)
        assert parsed.self_check(C) == []
        for cc in C:
            assert len(parsed.countries[cc].banks()) == len(banks[cc])
            assert parsed.expected_banks(cc)[0] == len(banks[cc])
        total, evidence = parsed.expected_banks_total(C)
        assert total == sum(len(v) for v in banks.values()) and "TOTAL UMOA" in evidence

    def test_registration_numbers_are_read_not_invented(self):
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf())
        regs = {m.registration_number for c in parsed.countries.values() for m in c.members}
        expected = {row["reg"] for rows in fixture_banks().values() for row in rows}
        assert regs == expected

    def test_multi_line_name_former_name_and_acronym(self):
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf())
        m = next(m for m in parsed.countries["CI"].members if m.registration_number == "Z 9202 B")
        assert m.official_name.startswith("FIXTURE BANQUE INTERNATIONALE") and m.official_name.endswith("CÔTE D'IVOIRE")
        assert m.designation.acronym == "FBICD"
        assert m.designation.former_names == ["FIXTURE BANQUE ANCIENNE"]

    def test_branch_form_and_parent(self):
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf())
        m = next(m for m in parsed.countries["ML"].members if m.registration_number == "Z 9402 D")
        assert m.form == "branch" and m.designation.parent_name == "FIXTURE PARENT BANK SÉNÉGAL"

    def test_header_mismatch_is_reported(self):
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf(header_override={"TG": 3}))
        issues = parsed.self_check(C)
        assert any(i.startswith("TG: parsed 1 bank rows but header announces 3") for i in issues)

    def test_summary_mismatch_is_reported(self):
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf(summary_override={"NE": 9}))
        assert any("NE: summary table announces 9 banks" in i for i in parsed.self_check(C))

    def test_missing_country_makes_expected_total_unknown(self):
        banks = fixture_banks()
        del banks["GW"]
        parsed = ReferenceListParser().parse_bytes(build_reference_list_pdf(banks))
        parsed.summary_total = None  # no printed total → only the country headers are usable
        parsed.summary.clear()
        assert parsed.expected_banks("GW") == (None, None)
        assert parsed.expected_banks_total(C) == (None, None)
        assert "GW: country section not found" in parsed.self_check(C)

    def test_rename_history_is_parsed(self):
        pdf = build_reference_list_pdf(history={"SN": [("FIXTURE OLD NAME BANK", "FIXTURE NEW NAME BANK")]})
        parsed = ReferenceListParser().parse_bytes(pdf)
        events = parsed.countries["SN"].history
        assert events and events[0]["type"] == "rename"
        assert events[0]["old_name"] == "FIXTURE OLD NAME BANK" and events[0]["new_name"] == "FIXTURE NEW NAME BANK"

    @pytest.mark.parametrize("text,expected", [
        ("(Mise à jour au 29 juin 2026)", date(2026, 6, 29)),
        ("AGRÉÉS DANS L'UMOA AU 31 DÉCEMBRE 2025", date(2025, 12, 31)),
        ("(Situation à fin décembre 2025)", date(2025, 12, 31)),
        ("aucune date ici", None),
    ])
    def test_reference_date(self, text, expected):
        assert parse_reference_date(text)[0] == expected


# =========================================================================== fascicle parser
class TestFascicle:
    @pytest.mark.parametrize("raw,value", [
        ("150 766", Decimal(150766)), ("-10 548", Decimal(-10548)), ("0", Decimal(0)), ("89", Decimal(89)),
        ("-", None), ("", None), ("n.d.", None), ("12,5", None), ("1.250", None),
    ])
    def test_amount_parsing_is_strict_and_never_turns_missing_into_zero(self, raw, value):
        assert parse_amount(raw) == value

    def test_statement_page_values_and_blank_cells(self):
        pdf = build_fascicle_pdf([{
            "country": "BENIN", "code": "FXB", "kind": "Bilans", "label": "FIXTURE BANK ALPHA BENIN",
            "rows": {
                "CREANCES SUR LA CLIENTELE": ["131 072", "130 602", "150 766"],
                "TOTAL DE L'ACTIF": ["", "269 088", "295 660"],  # blank 2021 cell
                "TOTAL DU PASSIF": ["301 931", "269 088", "295 660"],  # deliberately not mapped
                "IMMOBILISATIONS CORPORELLES": ["17 369", "16 602", "17 458"],  # would need a sum
            },
        }, {
            "country": "BENIN", "code": "Banques", "kind": "Bilans", "label": None,
            "rows": {"TOTAL DE L'ACTIF": ["1 000", "2 000", "3 000"]},
        }])
        result = FascicleParser().parse_bytes(pdf)
        assert result.aggregate_pages == 1 and len(result.pages) == 1
        page = result.pages[0]
        assert (page.country_code, page.kind, page.label) == ("BJ", "balance_sheet", "FIXTURE BANK ALPHA BENIN")
        got = {(v.metric_code, v.year): v.value_millions for v in page.values}
        assert got[("creances_clients", 2023)] == Decimal(150766)
        assert ("total_actifs", 2021) not in got  # blank stays missing (never 0)
        assert got[("total_actifs", 2022)] == Decimal(269088)
        assert {m for m, _ in got} == {"creances_clients", "total_actifs"}


# =========================================================================== resolution
def _resolver() -> EntityResolver:
    def ent(i, cc, name, regs=(), acronym=None, former=(), branch=False):
        e = IndexedEntity(id=i, country_code=cc, canonical_name=name, registration_numbers=set(regs), is_branch=branch)
        e.add_name(name)
        for f in former:
            e.add_name(f)
        e.add_name(acronym, "acronym")
        return e

    return EntityResolver([
        ent("sn-parent", "SN", "FIXTURE PARENT BANK SÉNÉGAL", {"Z 9602 C"}, "FPB"),
        ent("ml-branch", "ML", "FIXTURE PARENT BANK SÉNÉGAL, SUCCURSALE DU MALI", {"Z 9402 D"}, branch=True),
        ent("ci-alpha", "CI", "FIXTURE BANK ALPHA CÔTE D'IVOIRE", {"Z 9201 A"}, "FBA-CI", former=["FIXTURE OLD ALPHA"]),
        ent("bj-alpha", "BJ", "FIXTURE BANK ALPHA BÉNIN", {"Z 9001 A"}, "FBA-BJ"),
        ent("tg-noreg", "TG", "FIXTURE UNION BANK TOGO"),
        ent("tg-twin-1", "TG", "FIXTURE TWIN BANK"),
        ent("tg-twin-2", "TG", "FIXTURE TWIN BANK"),
    ])


class TestResolution:
    def test_registration_number_wins_over_name(self):
        r = _resolver().resolve_member(country_code="CI", official_name="COMPLETELY RENAMED", registration_number="Z 9201 A")
        assert (r.status, r.entity_id, r.method, r.confidence) == ("matched", "ci-alpha", "registration_number", 1.0)

    def test_registration_number_of_another_country_is_ambiguous(self):
        r = _resolver().resolve_member(country_code="BJ", official_name="X", registration_number="Z 9201 A")
        assert r.status == "ambiguous" and r.entity_id is None

    def test_never_matches_across_countries(self):
        r = _resolver().resolve_member(country_code="SN", official_name="FIXTURE BANK ALPHA CÔTE D'IVOIRE",
                                       registration_number=None)
        assert r.status == "no_match"

    def test_entity_with_other_registration_number_is_another_entity(self):
        r = _resolver().resolve_member(country_code="CI", official_name="FIXTURE BANK ALPHA CÔTE D'IVOIRE",
                                       registration_number="Z 9999 Z")
        assert r.status != "matched"

    def test_exact_name_without_registration(self):
        r = _resolver().resolve_member(country_code="TG", official_name="Fixture Union Bank - Togo",
                                       registration_number="Z 9701 A")
        assert (r.status, r.entity_id, r.method) == ("matched", "tg-noreg", "exact_name")

    def test_same_name_twice_is_ambiguous_never_merged(self):
        r = _resolver().resolve_member(country_code="TG", official_name="FIXTURE TWIN BANK", registration_number=None)
        assert r.status == "ambiguous" and r.entity_id is None and len(r.candidates) == 2

    def test_partial_overlap_goes_to_review(self):
        r = _resolver().resolve_member(country_code="TG", official_name="FIXTURE UNION BANK INTERNATIONAL",
                                       registration_number=None)
        assert r.status == "ambiguous" and r.entity_id is None

    def test_branch_is_never_resolved_to_its_parent(self):
        r = _resolver().resolve_member(country_code="SN", official_name="FIXTURE PARENT BANK SÉNÉGAL",
                                       registration_number=None, branch=True)
        assert r.status == "no_match"
        label = _resolver().resolve_label(country_code="ML", label="FIXTURE PARENT BANK SENEGAL")
        assert label.entity_id != "sn-parent" and label.status != "matched"

    def test_label_resolution_by_former_name_and_without_country(self):
        res = _resolver()
        assert res.resolve_label(country_code="CI", label="Fixture Old Alpha").entity_id == "ci-alpha"
        assert res.resolve_label(country_code="BJ", label="FIXTURE BANK ALPHA").entity_id == "bj-alpha"

    def test_parent_resolution_other_country(self):
        r = _resolver().resolve_parent(parent_name="FIXTURE PARENT BANK SÉNÉGAL", host_country_code="ML")
        assert (r.status, r.entity_id) == ("matched", "sn-parent")

    def test_parent_by_name_and_country_word(self):
        r = _resolver().resolve_parent(parent_name="FIXTURE BANK ALPHA (FBA) BENIN", host_country_code="NE")
        assert (r.status, r.entity_id) == ("matched", "bj-alpha")


# =========================================================================== coverage & gaps
class TestCoverageMath:
    def test_unknown_expected_is_never_a_ratio(self):
        assert ratio(5, None) is None and ratio(0, 0) is None
        assert CountryCoverage("BJ", None, None, 3, 3, "UNKNOWN").entity_ratio is None

    def test_matched_above_expected_is_capped(self):
        assert CountryCoverage("BJ", 2, "e", 3, 3, "COMPLETE").entity_ratio == 1.0

    def test_real_ratio(self):
        snap = CoverageSnapshot("U", None, True, expected_total=136, matched_total=129)  # type: ignore[arg-type]
        assert snap.entity_ratio == round(129 / 136, 4)

    def test_rejected_only_is_not_financial_data(self):
        e = EntityCoverage("e", "n", "BJ", None, "subsidiary", observations={"rejected": 4})
        assert not e.has_financial_data and not e.has_verified_data
        e.observations["needs_review"] = 1
        assert e.has_financial_data and not e.has_verified_data

    def test_regulatory_listing_does_not_count_as_website(self):
        e = EntityCoverage("e", "n", "BJ", None, "subsidiary", regulatory_listing=True)
        assert not e.official_own_source
        gaps = missing_items(e)
        # Phase 17 taxonomy: a regulatory listing is not an institutional source
        assert "SOURCE_NOT_FOUND" in gaps and "REGULATORY_SOURCE" not in gaps

    def test_gap_types_for_a_fully_covered_entity(self):
        e = EntityCoverage("e", "n", "BJ", None, "subsidiary", regulatory_listing=True, website_status="ACTIVE",
                           own_annual_report=True, financial_documents=2, observations={"verified": 3},
                           institution_documents=1, machine_readable_documents=1, analysed_documents=1,
                           institution_document_urls=["https://fixture.invalid/fs.pdf"])
        assert missing_items(e) == {}

    def test_validation_gap_is_human_only(self):
        e = EntityCoverage("e", "n", "BJ", None, "subsidiary", observations={"needs_review": 2})
        assert "VALIDATION" in missing_items(e) and "VALIDATION" in HUMAN_ONLY_GAP_TYPES

    def test_vocabularies(self):
        assert SOURCE_LIFECYCLE_STATUSES == ("CANDIDATE", "VERIFIED", "ACTIVE", "BLOCKED", "RETIRED")
        assert list(LINK_ROLE_PRIORITY.values()) == [1, 2, 3, 4, 5, 6, 7]
        assert set(HUMAN_ONLY_GAP_TYPES) <= set(GAP_TYPES)


# =========================================================================== http & extension points
class TestHttpAndExtensionPoints:
    def test_http_200_on_homepage_redirect_is_detected(self):
        r = FetchResult(url="https://www.bceao.int/fr/publications/unknown-page", final_url="https://www.bceao.int/fr",
                        status_code=200, content=b"<html>")
        assert r.ok and r.redirected_to_homepage

    def test_pdf_detection_uses_content_not_status(self):
        assert not FetchResult(url="u", status_code=200, content=b"<html>").is_pdf
        assert FetchResult(url="u", status_code=200, content=b"%PDF-1.7 ...").is_pdf

    def test_search_provider_is_abstract_and_not_implemented(self):
        with pytest.raises(TypeError):
            SearchProvider()  # type: ignore[abstract]
