"""
Automated deal collection (migration 0020) — pure functions, no network, no database.

Parsers are exercised on REAL pages captured on 21/10/2026 and trimmed (tests/fixtures/deals/README.md):
BRVM BOC, AMF-UMOA API, IFC SII, BOAD approved projects, Proparco project sheets. Covered rules: a
published value comes with its quotation; an unpublished one stays None (never 0, never an average);
no implicit currency; roles only when named; programme envelopes and DFI shares are flagged; cross-
source duplicate criteria; robots.txt wildcards and crawl delay.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from scraping.deals.collect.amf_umoa import (
    canonical,
    deal_type_of,
    label_country,
    operation_url,
    read_operation,
)
from scraping.deals.collect.amounts import (
    parse_day,
    parse_money,
    parse_number,
    parse_rate,
    umoa_countries,
)
from scraping.deals.collect.base import (
    Candidate,
    Evidence,
    PoliteFetcher,
    RobotsRules,
    assemble,
    in_window,
    is_restricted,
    parse_sitemap,
)
from scraping.deals.collect.boad import list_items, read_project
from scraping.deals.collect.brvm import boc_day, first_listings, read_boc
from scraping.deals.collect.ifc import read_sii
from scraping.deals.collect.proparco import detail_segments, read_sheet
from scraping.deals.duplicates import DealFacts, bond_label, is_candidate, matched_criteria
from scraping.deals.importer import validate_records
from scraping.deals.schemas import DealImportRecord, SourceRef
from scraping.universe.http import FetchResult

FX = Path(__file__).parent / "fixtures" / "deals"


def fx(*parts: str) -> bytes:
    return FX.joinpath(*parts).read_bytes()


def one(reading) -> dict:
    assert reading.build is not None, (reading.outcome, reading.detail)
    records = reading.build("DOC", "SRC")
    assert len(records) == 1
    validate_records(records)  # every produced record passes the import schema
    return records[0]


def excerpts(rec: dict) -> dict[str, str]:
    return {k: v for s in rec["sources"] for k, v in s["field_excerpts"].items()}


# =========================================================================== amounts, dates, countries
@pytest.mark.parametrize(("text", "amount", "currency", "unit"), [
    ("10 Mds FCFA", Decimal("10000000000"), "XOF", "billions"),
    ("5,9 Mds FCFA", Decimal("5900000000"), "XOF", "billions"),
    ("79.29 million (USD)", Decimal("79290000"), "USD", "millions"),
    ("US$40 million", Decimal("40000000"), "USD", "millions"),
    ("Prêt de 20 MUSD", Decimal("20000000"), "USD", "millions"),
    ("Garantie donnée de 19 MEUR", Decimal("19000000"), "EUR", "millions"),
])
def test_money_is_read_only_when_explicit(text, amount, currency, unit):
    m = parse_money(text, allow_cfa=True)
    assert (m.amount, m.currency, m.unit) == (amount, currency, unit)
    # A deal stores the printed figure in its unit (as UMOA-Titres does): figure x scale = absolute amount.
    scale = {"units": 1, "thousands": 10**3, "millions": 10**6, "billions": 10**9}[unit]
    assert m.figure * scale == m.amount


@pytest.mark.parametrize("text", [
    "122 million",  # no currency (IFC free text): never completed
    "Prêt senior de 45,9 MEUR, subvention de 6,6 MEUR",  # two amounts: which one? never chosen
    "1.250 USD",  # thousands or decimals: never guessed
    "10 USD et 12 EUR",
])
def test_ambiguous_money_is_none(text):
    assert parse_money(text, allow_cfa=True) is None


def test_cfa_franc_is_xof_only_for_umoa_publishers():
    assert parse_money("10 Mds FCFA") is None
    assert parse_money("10 Mds FCFA", allow_cfa=True).currency == "XOF"


def test_dates_rates_numbers_and_countries():
    assert parse_day("21 mai 2024") == date(2024, 5, 21)
    assert parse_day("Apr 11, 2025") == date(2025, 4, 11)
    assert parse_day("1er juin 2025") == date(2025, 6, 1)
    assert parse_day("25/06/2025") == date(2025, 6, 25)
    assert parse_day("31/02/2025") is None and parse_day("bientôt") is None
    assert parse_rate("GREEN BOND SWAMI AGRI 7,00 % 2026-2031") == Decimal("7.00")
    assert parse_rate("SWAMI AGRI 2026-2031") is None
    assert parse_number("15 000,50") == Decimal("15000.50") and parse_number("abc") is None
    assert umoa_countries("Afrique du Sud, Nigéria, République Démocratique du Congo") == []  # Nigeria != Niger
    assert umoa_countries("Cote D'Ivoire") == ["CI"]
    assert umoa_countries("Sénégal, Mali et Niger") == ["SN", "ML", "NE"]


# =========================================================================== BRVM — BOC first listings
BOC_14 = "https://www.brvm.org/sites/default/files/boc_20261014_2.pdf"
BOC_13 = "https://www.brvm.org/sites/default/files/boc_20261013_2.pdf"


def test_brvm_boc_first_listing_of_a_bond():
    rec = one(read_boc(BOC_14, fx("brvm", "boc_20261014.pdf")))
    assert rec["title"] == "GREEN BOND SWAMI AGRI 7,00 % 2026-2031 (SWAS.O1)"
    assert rec["interest_rate"] == Decimal("7.00")
    assert rec["announcement_date"] == date(2026, 10, 14)
    assert rec["ingestion_key"] == "brvm:first_listing:SWAS.O1"
    # Not published in a BOC line: never filled.
    for absent in ("amount", "currency", "isin", "maturity_date", "deal_type", "interest_rate_type"):
        assert absent not in rec
    assert rec["participants"] == [{"role": "issuer", "name": "SWAMI AGRI SAU", "source_ref": "boc", "page": 3,
                                    "excerpt": "Emetteur : SWAMI AGRI SAU", "extraction_method": "text"}]
    src = rec["sources"][0]
    assert (src["source_class"], src["page"]) == ("primary_market", 3)
    assert "Première cotation le 17 novembre 2026" in excerpts(rec)["interest_rate"]
    assert excerpts(rec)["announcement_date"] == "date du bulletin : mercredi 14 octobre 2026"
    assert rec["validation_flags"][0]["code"] == "listing_notice_only"


def test_brvm_boc_without_bond_listing_and_share_listing_lines():
    assert read_boc(BOC_13, fx("brvm", "boc_20261013.pdf")).outcome == "not_a_deal"
    section = ["SONATEL", "Première cotation - ACTIONS NOUVELLES SONATEL (SNTS) - Première cotation le 2 mars 2026",
               "PORT AUTONOME DE DAKAR", "Première cotation - PAD 6,60% 2020-2027",
               "(PADS.O3) - Première cotation le 1er octobre 2020"]
    found = first_listings(section)
    assert [(f["issuer"], f["symbol"]) for f in found] == [("PORT AUTONOME DE DAKAR", "PADS.O3")]  # shares ignored
    assert boc_day(BOC_14) == date(2026, 10, 14) and boc_day("https://x/boc.pdf") is None


def test_brvm_bulletin_date_must_match_the_file_name():
    reading = read_boc("https://www.brvm.org/sites/default/files/boc_20261015_2.pdf", fx("brvm", "boc_20261014.pdf"))
    assert reading.outcome == "refused" and "differs" in reading.detail


# =========================================================================== AMF-UMOA — regulator index
def amf_ops() -> dict[int, dict]:
    return {op["id"]: op for op in json.loads(fx("amf", "operations.json"))}


def test_amf_index_attests_only_title_type_country_and_filing_agent():
    op = amf_ops()[263]
    rec = one(read_operation(operation_url(263), canonical(op)))
    assert rec["title"] == "ETAT DU SENEGAL 6,30 % 2015-2025"
    assert (rec["deal_type"], rec["country_code"], rec["filing_agent_raw"]) == (
        "sovereign_bond_ape", "SN", "IMPAXIS Securities")
    # mtDemande, taux, duree, emetteur are published by the API but are NEVER taken from it (D2).
    for absent in ("amount", "interest_rate", "maturity_months", "currency"):
        assert absent not in rec
    assert rec["participants"] == [] and rec["sources"][0]["source_class"] == "regulator_index"


def test_amf_wrong_api_issuer_is_never_used_for_the_country():
    op = amf_ops()[1000003056]  # PETRO IVOIRE, API issuer "Trésor Public de Côte d'Ivoire" (known API defect)
    rec = one(read_operation(operation_url(op["id"]), canonical(op)))
    assert "country_code" not in rec and rec["deal_type"] == "corporate_bond_ape"


def test_amf_nature_and_label_contradiction_leaves_the_type_empty():
    reading = read_operation(operation_url(393), canonical(amf_ops()[393]))  # EOP + "par APE"
    assert "deal_type" not in one(reading) and reading.flags == ["amf_nature_contradicts_label"]
    assert deal_type_of("OPV", "Emission de 2 850 000 actions nouvelles BOA MALI") == ("capital_increase", None)
    assert deal_type_of("EOP", "Placement privé Alios Finances 6,95% 2022-2028") == ("corporate_bond_private", None)
    assert read_operation(operation_url(416), canonical(amf_ops()[416])).outcome == "out_of_scope"  # PE
    assert label_country("TPCI 6% 2019-2029") == "CI" and label_country("ORAGROUP SA 7,15% 2021-2028") is None


# =========================================================================== IFC — SII
IFC = "https://disclosures.ifc.org/project-detail/SII/"


def test_ifc_loan_disclosure_reads_grid_and_board_approved_investment():
    rec = one(read_sii(IFC + "49673/orange-mali-s-a", fx("ifc", "sii_49673_orange_mali.html")))
    assert (rec["title"], rec["country_code"], rec["deal_type"]) == ("IFC 49673 — Orange Mali S.A", "ML", "term_loan")
    assert (rec["amount"], rec["currency"], rec["unit"], rec["amount_original"]) == (
        Decimal("79.29"), "USD", "millions", "79.29 million (USD)")  # amount x scale(unit), as published
    assert (rec["announcement_date"], rec["signing_date"]) == (date(2025, 4, 11), date(2025, 11, 21))
    roles = {(p["role"], p["name"], p.get("commitment_amount")) for p in rec["participants"]}
    assert roles == {("lender", "International Finance Corporation (IFC)", Decimal("79290000.00")),
                     ("borrower", "Orange Mali SA", None)}
    assert [f["code"] for f in rec["validation_flags"]] == ["dfi_own_commitment_only"]
    # "capital expenditure plan of about 122 million" has no currency: never read as an amount.
    assert "122" not in json.dumps(rec, default=str)


def test_ifc_programme_envelope_is_not_the_counterparts_amount():
    rec = one(read_sii(IFC + "47431/gtfp-coris-cote-d-ivoire", fx("ifc", "sii_47431_gtfp_coris_ci.html")))
    assert "amount" not in rec and "currency" not in rec
    assert [p["role"] for p in rec["participants"]] == ["guarantor"]
    assert "commitment_amount" not in rec["participants"][0]
    assert [f["code"] for f in rec["validation_flags"]] == ["program_level_amount"]


def test_ifc_out_of_umoa_disclosure_is_out_of_scope():
    reading = read_sii(IFC + "50440/evolution-mobility", fx("ifc", "sii_50440_brazil.html"))
    assert reading.outcome == "out_of_scope" and "Brazil" in reading.detail


# =========================================================================== BOAD — approved projects
BOAD = "https://www.boad.org/fr/nos-publications/nos-projets-approuves/"


def test_boad_credit_line_with_explicit_amount_currency_and_beneficiary():
    rec = one(read_project(BOAD + "mise-en-place-dune-ligne-de-refinancement-en-faveur-de-afg-bank-mali/",
                           fx("boad", "project_afg_bank_mali.html")))
    assert (rec["amount"], rec["currency"], rec["unit"], rec["amount_original"]) == (
        Decimal("10"), "XOF", "billions", "10 Mds FCFA")
    assert (rec["country_code"], rec["debt_type"], rec["announcement_date"]) == ("ML", "credit_line", date(2025, 6, 25))
    assert "deal_type" not in rec  # a credit line is not forced into a deal type
    assert {(p["role"], p["name"]) for p in rec["participants"]} == {
        ("lender", "Banque Ouest Africaine de Développement (BOAD)"), ("borrower", "AFG Bank Mali")}
    assert excerpts(rec)["amount"] == "montant : 10 Mds FCFA"


def test_boad_without_published_instrument_gives_no_role():
    reading = read_project(BOAD + "construction-de-laeroport-international-de-ouagadougou-donsin-au-burkina-faso/",
                           fx("boad", "project_aeroport_donsin.html"))
    rec = one(reading)
    assert rec["participants"] == [] and reading.flags == ["boad_instrument_not_published"]
    assert (rec["country_code"], rec["sector"], rec["amount"]) == ("BF", "infrastructure_public", Decimal("5.9"))


def test_boad_cms_placeholder_fields_are_never_read():
    page = json.loads(html_lib.unescape(fx("boad", "project_afg_bank_mali.html").decode().split('data-page="')[1]
                                        .split('"')[0]))
    page["props"]["page"]["acf"].update({"beneficiary": "PAM", "location": "BENIN COTONOU", "total_cost": "15000000",
                                         "objet": "Laravel has wonderful, thorough documentation"})
    page["props"]["blocks"][1]["graph"] = [{"financer": "fonds propres", "financed_percent": "6 210 M FCFA, soit 20%"}]
    content = f'<div id="app" data-page="{html_lib.escape(json.dumps(page), quote=True)}"></div>'.encode()
    reading = read_project(BOAD + "x/", content)
    dumped = json.dumps(one(reading), default=str)
    assert "PAM" not in dumped and "BENIN" not in dumped and "Laravel" not in dumped and "6 210" not in dumped
    assert "equity_amount" not in dumped and "boad_graph_ignored" in reading.flags


def test_boad_list_page_pagination():
    items, last = list_items(fx("boad", "projects_page1.html").decode())
    assert last == 3 and len(items) == 6 and all(i["link"].startswith("/fr/nos-publications/") for i in items)


# =========================================================================== Proparco — project sheets
PP = "https://www.proparco.fr/fr/carte-des-projets/"


def test_proparco_senior_loan_with_grant_and_technical_assistance():
    rec = one(read_sheet(PP + "dakar-mobilite", fx("proparco", "dakar-mobilite.html")))
    assert (rec["amount"], rec["currency"], rec["signing_date"]) == (Decimal("52650000"), "EUR", date(2023, 11, 16))
    assert (rec["country_code"], rec["deal_type"], rec["debt_type"]) == ("SN", "term_loan", "senior_loan")
    lender = [p for p in rec["participants"] if p["role"] == "lender"]
    assert len(lender) == 1 and (lender[0]["commitment_amount"], lender[0]["commitment_currency"]) == (
        Decimal("45900000"), "EUR")  # the grant and the TA carry no financing role
    assert {p["role"] for p in rec["participants"]} == {"lender", "borrower"}
    assert rec["ingestion_key"] == "proparco:project:PSN1080"


def test_proparco_guarantee_and_out_of_scope():
    rec = one(read_sheet(PP + "coris-ci-g-trade-finance", fx("proparco", "coris-ci-g-trade-finance.html")))
    assert (rec["deal_type"], rec["country_code"], rec["sector"]) == ("guarantee", "CI", "financial_services")
    assert [p["role"] for p in rec["participants"]] == ["guarantor"]  # the guaranteed bank is not a borrower
    assert read_sheet(PP + "wiocc-2024", fx("proparco", "wiocc-2024.html")).outcome == "out_of_scope"
    assert detail_segments("Prêt senior de 45,9 MEUR, subvention de 6,6 MEUR et 150 KEUR d'Accompagnement") == [
        "Prêt senior de 45,9 MEUR", "subvention de 6,6 MEUR", "150 KEUR d'Accompagnement"]


# =========================================================================== shared machinery
def test_sitemaps_and_windows():
    urls, children = parse_sitemap(fx("ifc", "sitemap.xml").decode())
    assert len(urls) == 5 and urls[0][1] == "2026-06-26" and children == []
    assert parse_sitemap(fx("ifc", "sitemap_index.xml").decode())[1][0].endswith("sitemap-disclosures-1.xml")
    assert in_window(None, date(2026, 1, 1), None)  # unknown date: kept, decided by the parser
    assert not in_window(date(2025, 1, 1), date(2026, 1, 1), None)


def test_robots_wildcards_and_crawl_delay():
    ifc = RobotsRules("User-agent: *\nAllow:*\nDisallow: */apps/*\nDisallow: */misc*\n")
    assert ifc.allowed("https://disclosures.ifc.org/project-detail/SII/1/x")
    assert not ifc.allowed("https://disclosures.ifc.org/etc/apps/x.js")
    brvm = RobotsRules("User-agent: *\nCrawl-delay: 10\nDisallow: /search/\nAllow: /search/ok$\n")
    assert brvm.crawl_delay == 10.0 and not brvm.allowed("https://www.brvm.org/search/x")
    assert brvm.allowed("https://www.brvm.org/search/ok")
    mine = RobotsRules("User-agent: umoa-financial-intelligence\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert not mine.allowed("https://x.org/a")


class _Stub:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self.pages = pages
        self.calls: list[str] = []

    async def get(self, url: str) -> FetchResult:
        self.calls.append(url)
        status, body = self.pages.get(url, (404, b""))
        return FetchResult(url=url, final_url=url, status_code=status, content=body,
                           error=None if status == 200 else f"HTTP {status}")


def test_polite_fetcher_honours_robots_and_crawl_delay():
    stub = _Stub({"https://www.brvm.org/robots.txt": (200, b"User-agent: *\nCrawl-delay: 10\nDisallow: /admin/\n"),
                  "https://www.brvm.org/a": (200, b"A"), "https://www.brvm.org/b": (200, b"B")})
    clock = [0.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    polite = PoliteFetcher(stub, min_delay=1.0, sleep=sleep, clock=lambda: clock[0])

    async def go():
        a = await polite.get("https://www.brvm.org/a")
        b = await polite.get("https://www.brvm.org/b")
        denied = await polite.get("https://www.brvm.org/admin/x")
        return a, b, denied

    a, b, denied = asyncio.run(go())
    assert a.ok and b.ok and denied.error == "robots_disallowed" and is_restricted(denied)
    assert "https://www.brvm.org/admin/x" not in stub.calls  # never requested
    assert max(slept) == pytest.approx(10.0)  # crawl delay, not the configured 1 s
    assert is_restricted(FetchResult(url="u", status_code=403, error="HTTP 403"))
    assert is_restricted(FetchResult(url="https://x.org/doc", final_url="https://x.org/user/login", status_code=200,
                                     content=b"login"))


def test_evidence_and_assemble_refuse_contradictions():
    a, b = Evidence("a", source_class="dfi_official"), Evidence("b", source_class="primary_market")
    a.put("amount", Decimal("10"), "10")
    b.put("amount", Decimal("11"), "11")
    with pytest.raises(ValueError, match="contradiction on amount"):
        assemble([a, b], document_id="d", source_id="s", ingestion_key="k")
    assert Evidence("c", source_class="x").put("amount", None, "q") is None  # unpublished: nothing recorded
    assert Candidate(url="u").hint == {}


# =========================================================================== import schema (migration 0020)
def _src(**kw) -> dict:
    return {"ref": "s", "document_id": "d", "source_id": "x", "page": 1, **kw}


def test_field_excerpts_must_belong_to_attested_fields():
    with pytest.raises(ValidationError, match="field_excerpts for fields this source does not attest"):
        SourceRef.model_validate(_src(fields=["title"], field_excerpts={"amount": "10 Mds"}))


def test_debt_and_equity_require_a_currency_and_are_never_zero():
    base = {"title": "T", "sources": [_src(fields=["title", "debt_amount"])]}
    with pytest.raises(ValidationError, match="currency is required when debt_amount"):
        DealImportRecord.model_validate({**base, "debt_amount": "10"})
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate({**base, "debt_amount": "0", "currency": "XOF"})
    ok = DealImportRecord.model_validate({
        "title": "T", "debt_amount": "70", "equity_amount": "30", "currency": "XOF", "debt_type": "senior_loan",
        "sources": [_src(fields=["title", "debt_amount", "equity_amount", "currency", "debt_type"])]})
    assert (ok.debt_amount, ok.equity_amount) == (Decimal("70"), Decimal("30"))


def test_regulator_index_never_attests_amounts_nor_roles():
    with pytest.raises(ValidationError, match="regulator_index"):
        SourceRef.model_validate(_src(source_class="regulator_index", fields=["amount"]))


def test_debt_equity_ratio_only_from_two_published_amounts():
    from app.services.deal import debt_equity_ratio

    assert debt_equity_ratio(Decimal("70"), Decimal("30")) == Decimal("2.33")
    assert debt_equity_ratio(Decimal("70"), None) is None and debt_equity_ratio(None, Decimal("30")) is None


# =========================================================================== cross-source duplicates
def test_amf_index_and_brvm_listing_of_the_same_bond_are_candidates():
    amf = DealFacts(id="a", title="Emprunt obligataire par APE PAD 6,60% 2020-2027", deal_type="corporate_bond_ape")
    brvm = DealFacts(id="b", title="PAD 6,60% 2020-2027 (PADS.O3)", participants=[("issuer", None, "PAD")])
    criteria = matched_criteria(amf, brvm)
    assert criteria == ["label_issuer", "coupon", "tenor_years"] and is_candidate(criteria)
    other = DealFacts(id="c", title="PAD 6,60% 2021-2028 (PADS.O4)")
    assert not is_candidate(matched_criteria(amf, other))
    assert bond_label("OAT 3 ans — ETAT DU MALI — ML0000009925 — adjudication du 11/06/2025") is None


def test_dfi_borrower_and_bond_issuer_meet_through_the_counterparty_anchor():
    ifc = DealFacts(id="i", participants=[("borrower", None, "Orange Mali SA"), ("lender", None, "IFC")],
                    amount=Decimal("79290000"), currency="USD", signing_date=date(2025, 11, 21))
    bond = DealFacts(id="o", participants=[("issuer", None, "ORANGE MALI SA")], amount=Decimal("80000000"),
                     currency="USD", signing_date=date(2025, 12, 1))
    assert matched_criteria(ifc, bond) == ["currency_amount", "dates", "counterparty"]
    assert is_candidate(matched_criteria(ifc, bond))


def test_amounts_are_compared_on_their_value_whatever_the_unit():
    # UMOA-Titres prints "4 431,25 millions"; a press article "4,43 milliards": the same value.
    umoa = DealFacts(id="u", amount=Decimal("4431.25"), currency="XOF", unit="millions")
    press = DealFacts(id="p", amount=Decimal("4.43"), currency="XOF", unit="billions")
    raw = DealFacts(id="r", amount=Decimal("4431"), currency="XOF", unit="units")  # 4 431 F CFA: not the same
    assert "currency_amount" in matched_criteria(umoa, press)
    assert "currency_amount" not in matched_criteria(umoa, raw)


def test_isin_alone_is_not_an_anchor_and_reopenings_stay_distinct():
    base = dict(deal_type="sovereign_bond", currency="XOF", amount=Decimal("10345"),
                participants=[("issuer", None, "ETAT DU MALI")])
    a = DealFacts(id="a", isin="ML0000009925", value_date=date(2025, 6, 12), **base)
    reopening = DealFacts(id="c", isin="ML0000009925", value_date=date(2025, 9, 1), **base)
    criteria = matched_criteria(a, reopening)
    assert "isin" in criteria and "counterparty" not in criteria and not is_candidate(criteria)


def test_close_project_titles_match():
    a = DealFacts(id="a", project_name="Construction de l'Aéroport International de Ouagadougou-Donsin")
    b = DealFacts(id="b", project_name="Aéroport international de Ouagadougou Donsin")
    c = DealFacts(id="c", project_name="Aéroport de Bobo-Dioulasso")
    assert "project" in matched_criteria(a, b) and "project" not in matched_criteria(a, c)


def test_explicit_us_dollars_and_ifc_xof_are_read_bare_dollars_are_not():
    """Audit 22/10/2026 (M6)."""
    m = parse_money("un prêt de 500 millions de dollars américains")
    assert (m.figure, m.unit, m.currency) == (Decimal("500"), "millions", "USD")
    assert parse_money("12 millions de dollars") is None  # which dollar? never assumed
    m = parse_money("120.5 million (XOF)", allow_cfa=True)
    assert (m.figure, m.unit, m.currency) == (Decimal("120.5"), "millions", "XOF")
