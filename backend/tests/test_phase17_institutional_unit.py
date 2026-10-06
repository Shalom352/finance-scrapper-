"""
Phase 17 — institution-specific discovery: text-layer gate, institution statements parser, BRVM
profile parsing, BICI/BICICI & Coris resolution, BRVM evidence attribution, gap taxonomy.
Unit tests (no database, no network). Synthetic fixtures only ("FIXTURE" names).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from scraping.quality.text_layer import assess_page, assess_pdf_bytes, assess_texts
from scraping.universe.coverage import EntityCoverage
from scraping.universe.gaps import missing_items
from scraping.universe.institution_statements import InstitutionStatementParser, page_unit
from scraping.universe.resolution import EntityResolver, IndexedEntity
from scraping.universe.strategies.base import DiscoveryContext
from scraping.universe.strategies.institution_documents import BrvmIssuerFilingsStrategy
from scraping.universe.strategies.market_and_web import FINANCIAL_SECTORS, parse_brvm_profile
from tests.fixtures_phase15 import GARBLED_LINES, build_synoptic_pdf, build_text_pdf

LEFT = {"CREANCES SUR LA CLIENTELE": ["206 852 164 275", "192 784 679 264"],
        "TOTAL ACTIF": ["356 377 918 787", "357 508 751 917"],
        "OBLIGATIONS ET AUTRES TITRES": ["3 152 028 821", "777 716 529"]}
RIGHT = {"DETTES A L'EGARD DE LA CLIENTELE": ["234 000 554 049", "245 622 070 815"],
         "CAPITAUX PROPRES ET RESSOURCES ASSIMILEES": ["41 968 602 146", ""],  # blank 2022 cell
         "RESULTAT DE L'EXERCICE (+/-)": ["9 396 542 105", "10 134 089 251"]}


# =========================================================================== text layer
class TestTextLayer:
    def test_clean_page_is_ok(self):
        assert assess_page("\n".join(["CREANCES SUR LA CLIENTELE 206 852 164 275"] * 20), 1).status == "ok"

    def test_garbled_page_is_corrupted(self):
        text = "\n".join(GARBLED_LINES + ["TOTAL ACTIF 357 508 751 917"] * 10)
        q = assess_page(text, 1)
        assert q.status == "corrupted" and q.garbled_lines >= 3

    def test_phone_numbers_and_letter_spacing_are_not_garbled(self):
        text = "\n".join(["Tél. : +221 33 839 05 00", "Télécopie : +221 33 823 93 35",
                          "E T A T S F I N A N C I E R S 2 0 2 1"] + ["TOTAL ACTIF 1 000"] * 10)
        assert assess_page(text, 1).status == "ok"

    def test_scanned_pdf_is_not_machine_readable(self):
        q = assess_pdf_bytes(build_text_pdf([[], []]))
        assert q.status == "not_machine_readable" and q.ok_pages == 0

    def test_partially_corrupted_document(self):
        q = assess_texts(["\n".join(["TOTAL ACTIF 1 000"] * 10), "\n".join(GARBLED_LINES * 3)])
        assert q.status == "partially_corrupted" and q.page_ok(1) and not q.page_ok(2)


# =========================================================================== statements parser
class TestInstitutionStatements:
    def test_side_by_side_tables_and_second_header_row(self):
        pdf = build_synoptic_pdf(LEFT, RIGHT, off_balance_rows={"ENGAGEMENTS DONNES": ["1 000", "2 000"]})
        res = InstitutionStatementParser().parse_bytes(pdf, "FIXTURE Bilan et compte de résultat 2022")
        got = {(v.metric_code, v.year): v.raw for v in res.values}
        assert got[("creances_clients", 2021)] == "206 852 164 275"
        assert got[("total_actifs", 2022)] == "357 508 751 917"  # exact variant "TOTAL ACTIF"
        assert got[("depots_clients", 2022)] == "245 622 070 815"
        assert got[("capitaux_propres", 2021)] == "41 968 602 146"
        assert ("capitaux_propres", 2022) not in got  # blank cell stays missing, never 0
        assert all(m != "obligations_emises" for m, _ in got)  # not a 1:1 catalogue line
        assert res.check_values[("balance_sheet_result", 2022)][0] == Decimal(10134089251)

    def test_unit_not_stated_means_not_normalizable(self):
        res = InstitutionStatementParser().parse_bytes(build_synoptic_pdf(LEFT, RIGHT), "FIXTURE")
        assert {(v.unit, v.currency, v.multiplier) for v in res.values} == {(None, None, None)}

    @pytest.mark.parametrize("line,expected", [
        ("(en F CFA)", ("unit", "XOF", Decimal(1))),
        ("Montants en millions de F CFA", ("millions", "XOF", Decimal(1_000_000))),
        ("Au 31/12/2021, 1 euro = 655,957 F CFA", (None, None, None)),  # exchange note ≠ unit statement
        # BRVM certified statements (Société Générale CI 2021): heading in MXOF.
        ("Données financières en millions (MXOF)", ("millions", "XOF", Decimal(1_000_000))),
        ("(en millions de FCFA)", ("millions", "XOF", Decimal(1_000_000))),
        ("Montants (MXOF)", ("millions", "XOF", Decimal(1_000_000))),
        # A per-share label states the unit of that line only, never of the page.
        ("Dividende brut par action (en F CFA)", (None, None, None)),
        ("Données financières en millions (MXOF)\nDividende brut par action (en F CFA)",
         ("millions", "XOF", Decimal(1_000_000))),
        ("Dividende brut par action (en F CFA)\nTotal bilan (en F CFA)", ("unit", "XOF", Decimal(1))),
    ])
    def test_unit_only_from_explicit_statement(self, line, expected):
        assert page_unit(line) == expected

    def test_stated_unit_is_used(self):
        res = InstitutionStatementParser().parse_bytes(build_synoptic_pdf(LEFT, RIGHT, unit_line="(en F CFA)"), "x")
        assert {v.unit for v in res.values} == {"unit"}

    def test_interim_statements_are_not_read(self):
        res = InstitutionStatementParser().parse_bytes(build_synoptic_pdf(LEFT, RIGHT),
                                                       "Etats financiers 1er semestre 2026")
        assert res.values == [] and "interim" in res.skipped_pages[0]

    def test_corrupted_page_yields_nothing(self):
        pdf = build_text_pdf([GARBLED_LINES * 3 + ["2021", "2022", "TOTAL ACTIF 1 000 2 000"]])
        res = InstitutionStatementParser().parse_bytes(pdf, "x")
        assert res.values == [] and res.skipped_pages[1] == "text layer corrupted"


# =========================================================================== BRVM pages & resolution
def _resolver() -> EntityResolver:
    def ent(i, cc, name, acronym=None, branch=False):
        e = IndexedEntity(id=i, country_code=cc, canonical_name=name, is_branch=branch)
        e.add_name(name)
        e.add_name(acronym, "acronym")
        return e

    return EntityResolver([
        ent("bicici", "CI", "BANQUE INTERNATIONALE POUR LE COMMERCE ET L'INDUSTRIE DE LA CÔTE D'IVOIRE", "BICICI"),
        ent("coris-bf", "BF", "CORIS BANK INTERNATIONAL", "CBI"),
        ent("coris-ci", "CI", "CORIS BANK INTERNATIONAL CÔTE D'IVOIRE", "CBI - CI"),
        ent("boa-ne", "NE", "BANK OF AFRICA - NIGER", "BOA - NIGER"),
        ent("boa-sn", "SN", "BANK OF AFRICA - SÉNÉGAL", "BOA - SÉNÉGAL"),
        ent("orabank-ne", "NE", "ORABANK CÔTE D'IVOIRE, SUCCURSALE DU NIGER", branch=True),
    ])


class TestBrvmAndResolution:
    def test_profile_sector_in_any_case(self):
        html = ("<title>Coris Bank International | BRVM</title><div>Raison sociale : Coris Bank International SA "
                "Secteur d’activités : Banque Date d’introduction à la BRVM : 23 décembre 2011</div>")
        raison, sector, labels = parse_brvm_profile(html)
        assert raison == "Coris Bank International SA" and sector == "BANQUE" and sector in FINANCIAL_SECTORS

    def test_profile_without_block_uses_title(self):
        raison, sector, labels = parse_brvm_profile("<title>NSIA BANQUE CI | BRVM</title><p>cours</p>")
        assert raison is None and sector is None and labels == ["NSIA BANQUE CI"]

    def test_bici_resolves_to_bicici_only_with_country(self):
        r = _resolver()
        assert r.resolve_label(country_code="CI", label="BICI COTE D’IVOIRE").entity_id == "bicici"
        assert r.resolve_label(country_code="CI", label="BICI").status != "matched"  # no country → no rule
        assert r.resolve_label(country_code="SN", label="BICI COTE D’IVOIRE").status == "no_match"

    def test_coris_resolves_per_country_never_across(self):
        r = _resolver()
        assert r.resolve_label(country_code="BF", label="Coris Bank International SA").entity_id == "coris-bf"
        assert r.resolve_label(country_code="CI", label="Coris Bank International SA").entity_id == "coris-ci"

    def _ctx(self):
        return DiscoveryContext(db=None, fetcher=None, registrar=None, resolver=_resolver(), run=None,  # type: ignore
                                universe_code="U", country_codes=("NE", "SN", "CI", "BF"), target_years=[])

    def test_filing_attribution_by_document_text(self):
        s = BrvmIssuerFilingsStrategy()
        eid, ev = s._resolve(self._ctx(), "BANK OF AFRICA NG", "BANK OF AFRICA - NIGER Bilan 2025 Niamey NIGER")
        assert eid == "boa-ne" and "NE" in ev

    def test_filing_never_attributed_on_name_proximity(self):
        s = BrvmIssuerFilingsStrategy()
        assert s._resolve(self._ctx(), "BANK OF AFRICA NG", "")[0] is None  # scanned: no text evidence
        two = "BANK OF AFRICA - NIGER ... BANK OF AFRICA - SÉNÉGAL NIGER SENEGAL"
        eid, reason = s._resolve(self._ctx(), "BOA GROUP", two)
        assert eid is None and "several" in reason

    def test_filing_branch_is_never_attributed(self):
        s = BrvmIssuerFilingsStrategy()
        text = "ORABANK CÔTE D'IVOIRE, SUCCURSALE DU NIGER NIGER"
        assert s._resolve(self._ctx(), "ORAGROUP", text)[0] is None


# =========================================================================== gap taxonomy
def _e(**kw) -> EntityCoverage:
    return EntityCoverage("e", "FIXTURE", "BJ", None, "subsidiary", regulatory_listing=True, **kw)


class TestGapTaxonomy:
    def test_source_not_found_is_not_an_absence(self):
        gaps = missing_items(_e())
        assert "SOURCE_NOT_FOUND" in gaps and "executed so far" in gaps["SOURCE_NOT_FOUND"]
        assert "DOCUMENT_NOT_FOUND" in gaps

    def test_candidate_and_blocked_sources(self):
        assert "SOURCE_FOUND_UNVERIFIED" in missing_items(_e(website_candidates=1))
        assert "SOURCE_BLOCKED" in missing_items(_e(website_blocked=1))

    def test_verified_source_closes_source_gaps(self):
        gaps = missing_items(_e(market_filings=True))
        assert not {"SOURCE_NOT_FOUND", "SOURCE_FOUND_UNVERIFIED", "SOURCE_BLOCKED"} & set(gaps)

    def test_document_states(self):
        urls = ["https://fixture.invalid/a.pdf"]
        assert "DOCUMENT_NOT_MACHINE_READABLE" in missing_items(_e(institution_documents=1,
                                                                   institution_document_urls=urls))
        assert "DOCUMENT_FOUND_UNVERIFIED" in missing_items(_e(institution_documents=1, machine_readable_documents=1,
                                                               institution_document_urls=urls))
        done = missing_items(_e(institution_documents=1, machine_readable_documents=1, analysed_documents=1,
                                institution_document_urls=urls))
        assert not {"DOCUMENT_NOT_FOUND", "DOCUMENT_FOUND_UNVERIFIED", "DOCUMENT_NOT_MACHINE_READABLE"} & set(done)

    def test_ambiguity_types(self):
        gaps = missing_items(_e(ambiguities=[
            {"type": "ENTITY_AMBIGUOUS", "label": "UNITED BANK OF AFRICA", "evidence": "fascicle"},
            {"type": "PARENT_SUBSIDIARY_AMBIGUITY", "label": "FIXTURE PARENT", "evidence": "list"},
            {"type": "HISTORICAL_NAME_AMBIGUITY", "label": "FIXTURE OLD", "evidence": "fascicle"},
        ]))
        assert {"ENTITY_AMBIGUOUS", "PARENT_SUBSIDIARY_AMBIGUITY", "HISTORICAL_NAME_AMBIGUITY"} <= set(gaps)
