"""UMOA-Titres auction parsers and deal building — pure functions (no network, no database)."""
from datetime import date
from decimal import Decimal

import pytest

from scraping.deals.duplicates import DealFacts, is_candidate, matched_criteria
from scraping.deals.umoa_titres_auctions import (
    ISSUER_COUNTRIES,
    LayoutError,
    build_auction_deals,
    emission_urls,
    months_from_duration,
    norm,
    parse_amount,
    parse_buyback_page,
    parse_compte_rendu,
    parse_compte_rendu_page,
    parse_emission_page,
    slug_date,
)
from tests.fixtures_umoa_titres import (
    FxTranche,
    compte_rendu_lines,
    compte_rendu_pdf,
    emission_page_html,
)

ENTITIES = {c: (f"ent-{c}", f"Trésor {c}") for c in ("BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG")}
ML = [
    FxTranche("ML0000009917", "BAT", "364 jours", "10/06/2026", "20 010", "9,35%", ref_code="BT1A"),
    FxTranche("ML0000009925", "OAT", "3 ans", "12/06/2028", "10 345", "9,22%", "6,15%"),
    FxTranche("ML0000009933", "OAT", "5 ans", "12/06/2030", "0", "-", "6,35%", ref_code="OT5A"),
]
ML_PAGE = [("BAT", "10/06/2026", "20 010,0000", "9,3523"), ("OAT", "12/06/2028", "10 345,0000", "9,2156"),
           ("OAT", "12/06/2030", "--", "--")]


def _text(lines: list[str]) -> str:
    return "\n".join(lines)


def _build(reports, page_results=ML_PAGE, operation="11/06/2025", value="12/06/2025"):
    page = parse_emission_page(emission_page_html(operation=operation, value=value, compte_rendu_url="cr.pdf",
                                                  results=page_results))
    return build_auction_deals(reports=reports, page=page, sovereign_entities=ENTITIES, pdf_document_id="doc-pdf",
                               page_document_id="doc-page", source_id="src", emission_url="https://e/x/",
                               compte_rendu_url="https://e/cr.pdf")


def _ml_report():
    return parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)), 1)


def test_values_are_read_as_printed():
    assert parse_amount("13 199,54") == Decimal("13199.54")
    assert parse_amount("--") is None and parse_amount("-") is None and parse_amount("") is None
    assert parse_amount("0") == Decimal("0")
    assert months_from_duration("3 ans") == 36 and months_from_duration("12 mois") == 12
    assert months_from_duration("361 jours") is None  # days are never turned into months
    assert slug_date("https://x/fr/emission/emission-simultanee-du-mali-du-11-06-2025/") == date(2025, 6, 11)
    assert slug_date("https://x/fr/emission/foo-du-04-03-2022-2/") == date(2022, 3, 4)
    assert slug_date("https://x/fr/emission/24592/") is None


def test_index_lists_emission_pages():
    html = ("<a href='https://www.umoatitres.org/fr/emission/a-du-01-02-2025/'>a</a>"
            "<a href=\"https://www.umoatitres.org/fr/emission/a-du-01-02-2025/\">a</a>"
            "<a href='https://www.umoatitres.org/fr/emissions/'>index</a>")
    assert emission_urls(html) == ["https://www.umoatitres.org/fr/emission/a-du-01-02-2025/"]


def test_multi_security_compte_rendu():
    r = _ml_report()
    assert r.issuer_label == "ETAT DU MALI"
    assert (r.auction_date, r.value_date) == (date(2025, 6, 11), date(2025, 6, 12))
    oat3, oat5 = r.tranches[1], r.tranches[2]
    assert (oat3.isin, oat3.instrument_type, oat3.auction_reference) == (
        "ML0000009925", "OAT", "ML0000009925".join(["ADJ-", "-OT3A-2025"]))
    assert (oat3.retained, oat3.coupon, oat3.yield_rate, oat3.maturity_date) == (
        Decimal("10345"), Decimal("6.15"), Decimal("9.22"), date(2028, 6, 12))
    assert oat5.retained == Decimal("0") and oat5.yield_rate is None  # "-" is a placeholder, never 0 %
    assert r.flags == []


def test_pdf_fixture_round_trip():
    pdf = compte_rendu_pdf("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
    reports = parse_compte_rendu(pdf)
    assert len(reports) == 1 and reports[0].page_number == 1 and len(reports[0].tranches) == 3
    assert reports[0].flags == []
    assert [t.yield_rate for t in reports[0].tranches] == [Decimal("9.35"), Decimal("9.22"), None]


def test_one_deal_per_issued_oat_tranche():
    res = _build([_ml_report()])
    assert res.issue is None
    assert [r["isin"] for r in res.records] == ["ML0000009925"]
    assert sorted((s.isin, s.reason) for s in res.skipped) == [
        ("ML0000009917", "not_oat"), ("ML0000009933", "no_retained_amount")]
    rec = res.records[0]
    assert rec["deal_type"] == "sovereign_bond" and rec["instrument_type"] == "OAT"
    assert (rec["amount"], rec["currency"], rec["unit"]) == (Decimal("10345"), "XOF", "millions")
    assert rec["amount_original"] == "10 345 millions de F CFA"
    assert (rec["interest_rate"], rec["interest_rate_type"], rec["yield_rate"]) == (
        Decimal("6.15"), "fixed", Decimal("9.22"))
    assert (rec["value_date"], rec["auction_date"], rec["maturity_date"], rec["maturity_months"]) == (
        date(2025, 6, 12), date(2025, 6, 11), date(2028, 6, 12), 36)
    assert rec["country_code"] == "ML"
    assert rec["participants"] == [{"role": "issuer", "name": "ETAT DU MALI", "entity_id": "ent-ML",
                                    "source_ref": "compte_rendu"}]
    assert rec["ingestion_key"] == "umoa_titres:ML:ADJ-ML0000009925-OT3A-2025:ML0000009925:2025-06-12"
    refs = {s["ref"]: s for s in rec["sources"]}
    assert refs["compte_rendu"]["page"] == 1 and refs["compte_rendu"]["document_id"] == "doc-pdf"
    assert {"isin", "amount", "yield_rate", "value_date", "maturity_date", "auction_reference"} <= set(
        refs["compte_rendu"]["fields"])
    assert refs["emission_page"]["document_id"] == "doc-page"
    assert {"amount", "yield_rate", "value_date", "maturity_date"} <= set(refs["emission_page"]["fields"])
    assert refs["compte_rendu"]["excerpt"].startswith("pdf_text")


def test_no_tranche_issued_means_no_deal():
    tranches = [FxTranche("ML0000009925", "OAT", "3 ans", "12/06/2028", "0", "-", "6,15%")]
    report = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025",
                                                                tranches)), 1)
    res = _build([report], page_results=[("OAT", "12/06/2028", "--", "--")])
    assert res.issue is None and res.records == []
    assert [s.reason for s in res.skipped] == ["no_retained_amount"]


def test_ambiguous_coupon_stays_null_and_is_flagged():
    # The real CI compte rendu prints "0,057" (no % sign) for one coupon: never interpreted.
    lines = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML, coupon_tokens=["0,057", "6,35%"])
    report = parse_compte_rendu_page(_text(lines), 1)
    assert "coupon_count_mismatch" in report.flags
    rec = _build([report]).records[0]
    assert "interest_rate" not in rec and "interest_rate_type" not in rec  # NULL, never 0


def test_contradiction_with_the_page_refuses_the_auction():
    page = [ML_PAGE[0], ("OAT", "12/06/2028", "10 000,0000", "9,2156"), ML_PAGE[2]]
    res = _build([_ml_report()], page_results=page)
    assert res.records == [] and res.issue == "retained_amount_differs_ML0000009925"
    res = _build([_ml_report()], value="13/06/2025")
    assert res.records == [] and res.issue == "value_date_differs"


def test_page_order_is_paired_on_type_and_maturity():
    res = _build([_ml_report()], page_results=[ML_PAGE[2], ML_PAGE[0], ML_PAGE[1]])
    assert res.issue is None and [r["isin"] for r in res.records] == ["ML0000009925"]


def test_issuer_must_be_explicit_and_consistent():
    lines = compte_rendu_lines("TRESOR REGIONAL", "11/06/2025", "12/06/2025", ML)
    assert _build([parse_compte_rendu_page(_text(lines), 1)]).issue == "issuer_not_recognised: TRESOR REGIONAL"
    lines = compte_rendu_lines("ETAT DU NIGER", "11/06/2025", "12/06/2025", ML)
    assert _build([parse_compte_rendu_page(_text(lines), 1)]).issue == "issuer_and_isin_country_differ"
    assert ISSUER_COUNTRIES[norm("ÉTAT DE CÔTE D'IVOIRE")] == "CI"


def test_layout_errors_extract_nothing():
    lines = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML, total="99 999,00")
    with pytest.raises(LayoutError, match="do not add up"):
        parse_compte_rendu_page(_text(lines), 1)
    lines = [ln for ln in compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
             if not ln.startswith(("ADJ-", ": ADJ-"))]
    with pytest.raises(LayoutError, match="auction references"):
        parse_compte_rendu_page(_text(lines), 1)


def test_buyback_page_is_never_an_issuance():
    lines = ["COMPTE RENDU D'ADJUDICATION RACHAT DE BONS DU TRESOR", "Code ISIN", ": TG0000002625"]
    assert parse_compte_rendu_page(_text(lines), 2) is None


def test_single_security_layout():
    lines = ["COMPTE RENDU D'ADJUDICATION D'OBLIGATIONS DU TRESOR", "Code ISIN", ": NE0000009990",
             "Emetteur : ETAT DU NIGER", "Dénomination de l'émission", ": NE0000009990-OAT-08-2030",
             "Adjudication N°", ": ADJ-NE0000009990-OAT5A-2025", "du : 18/08/2025", "Date de valeur",
             ": 19/08/2025", "Date d'échéance : 19/08/2030", "Durée", ": 5 ans", "Soumissions retenues",
             ": 15 000", "millions de FCFA, dont en ONC", "Rendement moyen pondéré", ": 8,07%"]
    r = parse_compte_rendu_page(_text(lines), 1)
    t = r.tranches[0]
    assert (r.auction_date, r.value_date, t.retained, t.yield_rate, t.maturity_date, t.coupon) == (
        date(2025, 8, 18), date(2025, 8, 19), Decimal("15000"), Decimal("8.07"), date(2030, 8, 19), None)


def test_instrument_anchor_flags_only_the_same_issue():
    base = dict(deal_type="sovereign_bond", currency="XOF", amount=Decimal("10345"),
                issuer_entities=frozenset({"ent-ML"}))
    a = DealFacts(id="a", isin="ML0000009925", value_date=date(2025, 6, 12), **base)
    same = DealFacts(id="b", isin="ML0000009925", value_date=date(2025, 6, 12), **base)
    reopening = DealFacts(id="c", isin="ML0000009925", value_date=date(2025, 9, 1), **base)
    other_tranche = DealFacts(id="d", isin="ML0000009933", value_date=date(2025, 6, 12), **base)
    assert is_candidate(matched_criteria(a, same)) and "instrument" in matched_criteria(a, same)
    assert not is_candidate(matched_criteria(a, reopening))  # a re-opening of an ISIN is another deal
    assert not is_candidate(matched_criteria(a, other_tranche))  # another tranche of the same auction


# --------------------------------------------------------------------------- formats EC, totals, issuer labels


def _buyback_page() -> str:
    """'EC' documents: page 2 is a buyback (RA- references, title printed at the bottom)."""
    return _text(["Emetteur :", "ETAT DU MALI", "Date d'adjudication", ":", "11/06/2025", "Date de valeur", ":",
                  "12/06/2025", "Code ISIN", ": ML0000001112", "Dénomination de l'émission",
                  ": ML0000001112-OAT-06-2025", "Adjudication n°", ": RA-ML0000001112-14-2025", "Durée", ": 4 jours",
                  "Date d'échéance", ": 16/06/2025", "Soumissions retenues", "5 500,00 millions de F CFA, dont ONC :0",
                  "COMPTE RENDU DE RACHAT DE BONS ET D'OBLIGATIONS"])


def test_ec_document_ignores_the_buyback_page():
    assert parse_compte_rendu_page(_buyback_page(), 2) is None
    # A page whose references are ADJ- is never taken for a buyback, whatever its footer says.
    issuance = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML) + ["COMPTE RENDU DE RACHAT"]
    assert parse_compte_rendu_page(_text(issuance), 1) is not None


def test_rounded_global_total_is_accepted_only_when_integer_and_equal_to_the_rounded_sum():
    two = [FxTranche("ML0000009925", "OAT", "3 ans", "12/06/2028", "34 658,17", "7,9%", "6,15%"),
           FxTranche("ML0000009933", "OAT", "5 ans", "12/06/2030", "4 070,50", "8,1%", "6,35%", ref_code="OT5A")]
    ok = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", two,
                                                          total="38 729")), 1)
    assert ok.flags == ["global_total_rounded"]
    assert [t.retained for t in ok.tranches] == [Decimal("34658.17"), Decimal("4070.50")]  # kept as printed
    for total in ("38 729,00", "38 730", "38 728"):  # decimals printed, or not the rounded sum
        with pytest.raises(LayoutError, match="do not add up"):
            parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", two,
                                                             total=total)), 1)
    page = [("OAT", "12/06/2028", "34 658,1700", "7,9000"), ("OAT", "12/06/2030", "4 070,5000", "8,1000")]
    recs = _build([ok], page_results=page).records
    assert [r["validation_flags"][0]["code"] for r in recs] == ["global_total_rounded"] * 2


def test_global_total_printed_with_its_unit_on_the_same_line():
    lines = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
    i = lines.index("Soumissions retenues")
    lines[i + 2:i + 4] = [f"{lines[i + 2]} millions de FCFA, dont ONC :"]
    assert parse_compte_rendu_page(_text(lines), 1).flags == []


def test_stray_space_and_truncated_reference_are_kept_as_printed():
    lines = [ln.replace("ML0000009925-OAT-", "ML0000009925 -OAT-").replace("-OT3A-2025", "-OT3A-202")
             for ln in compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)]
    t = parse_compte_rendu_page(_text(lines), 1).tranches[1]
    assert (t.isin, t.instrument_type, t.auction_reference) == ("ML0000009925", "OAT", "ADJ-ML0000009925-OT3A-202")


def test_two_amounts_merged_on_one_line_stay_refused():
    lines = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
    i = len(lines) - 1 - lines[::-1].index("Soumissions retenues")
    lines[i + 2:i + 4] = [lines[i + 2] + " " + lines[i + 3]]  # "10 345 millions ... ONC :0 0 millions ..."
    with pytest.raises(LayoutError, match="retained amounts per security"):
        parse_compte_rendu_page(_text(lines), 1)


GW = [FxTranche("GW0000001523", "OAT", "3 ans", "14/01/2029", "8 335,21", "7,10%", "6,25%")]
GW_PAGE = [("OAT", "14/01/2029", "8 335,2100", "7,1000")]


def test_truncated_guinea_bissau_label_needs_the_gw_isin_prefix():
    report = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DE GUINÉE-BISSA", "11/06/2025", "12/06/2025",
                                                                GW)), 1)
    entities = dict(ENTITIES)
    res = build_auction_deals(reports=[report], page=parse_emission_page(emission_page_html(
        operation="11/06/2025", value="12/06/2025", compte_rendu_url="cr.pdf", results=GW_PAGE)),
        sovereign_entities=entities, pdf_document_id="p", page_document_id="h", source_id="s",
        emission_url="u", compte_rendu_url="c")
    rec = res.records[0]
    assert rec["country_code"] == "GW" and rec["participants"][0]["entity_id"] == "ent-GW"
    assert rec["participants"][0]["name"] == "ETAT DE GUINÉE-BISSA"  # printed label kept
    assert rec["validation_flags"][0]["code"] == "issuer_label_truncated"
    assert "truncated_label_confirmed_by_isin_prefix_GW" in rec["sources"][0]["excerpt"]
    # Same truncated label with a Malian ISIN: refused, never attached by guess.
    report = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DE GUINÉE-BISSA", "11/06/2025", "12/06/2025",
                                                                ML)), 1)
    assert _build([report]).issue == "issuer_and_isin_country_differ"


def test_full_guinea_bissau_label_is_an_exact_match_without_flag():
    report = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DE GUINÉE-BISSAU", "11/06/2025", "12/06/2025",
                                                                GW)), 1)
    res = build_auction_deals(reports=[report], page=parse_emission_page(emission_page_html(
        operation="11/06/2025", value="12/06/2025", compte_rendu_url="cr.pdf", results=GW_PAGE)),
        sovereign_entities=ENTITIES, pdf_document_id="p", page_document_id="h", source_id="s",
        emission_url="u", compte_rendu_url="c")
    assert "validation_flags" not in res.records[0]
    assert "(règle exact_label)" in res.records[0]["sources"][0]["excerpt"]


def test_refusals_carry_the_conflicting_values():
    page = [ML_PAGE[0], ("OAT", "12/06/2028", "10 000,0000", "9,2156"), ML_PAGE[2]]
    res = _build([_ml_report()], page_results=page)
    assert res.conflict == {"field": "amount", "isin": "ML0000009925", "html": "10000.0000", "pdf": "10345"}
    res = _build([_ml_report()], page_results=ML_PAGE[:2])
    assert res.issue == "page_and_compte_rendu_list_different_securities" and res.conflict["field"] == "securities"


# --------------------------------------------------------------------------- 'EC' pages listing bought-back securities


def _buyback_text(securities: list[tuple[str, str, str]]) -> str:
    """Buyback page of an 'EC' compte rendu: (isin, type, maturity dd/mm/yyyy)."""
    lines = ["Emetteur :", "ETAT DU MALI", "Date d'adjudication", ":", "11/06/2025", "Date de valeur", ":",
             "12/06/2025", "Code ISIN"]
    lines += [(": " if k == 0 else "") + isin for k, (isin, _, _) in enumerate(securities)]
    lines += ["Dénomination de l'émission"]
    lines += [(": " if k == 0 else "") + f"{isin}-{kind}-{mat[3:5]}-{mat[6:]}"
              for k, (isin, kind, mat) in enumerate(securities)]
    lines += ["Adjudication n°"] + [(": " if k == 0 else "") + f"RA-{isin}-14-2025"
                                   for k, (isin, _, _) in enumerate(securities)]
    lines += ["Durée"] + [(": " if k == 0 else "") + "5 jours" for k in range(len(securities))]
    lines += ["Date d'échéance"] + [(": " if k == 0 else "") + mat for k, (_, _, mat) in enumerate(securities)]
    lines += ["COMPTE RENDU DE RACHAT DE BONS ET D'OBLIGATIONS"]
    return _text(lines)


BUYBACK = [("ML0000001112", "OAT", "16/06/2025"), ("ML0000001120", "BAT", "20/06/2025")]
EC_PAGE = ML_PAGE + [("OAT", "16/06/2025", "--", "--"), ("BAT", "20/06/2025", "--", "--")]


def _build_ec(page_results, buyback=BUYBACK, reports=None):
    page = parse_emission_page(emission_page_html(operation="11/06/2025", value="12/06/2025",
                                                  compte_rendu_url="cr.pdf", results=page_results))
    buybacks = [parse_buyback_page(_buyback_text(buyback), 2)]
    return build_auction_deals(reports=reports or [_ml_report()], page=page, buybacks=buybacks,
                               sovereign_entities=ENTITIES, pdf_document_id="p", page_document_id="h",
                               source_id="s", emission_url="u", compte_rendu_url="c")


def test_buyback_page_lists_its_securities_page_and_references():
    b = parse_buyback_page(_buyback_text(BUYBACK), 2)
    assert (b.page_number, b.references) == (2, ["RA-ML0000001112-14-2025", "RA-ML0000001120-14-2025"])
    assert b.securities == [("OAT", date(2025, 6, 16)), ("BAT", date(2025, 6, 20))]
    assert parse_buyback_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)), 1) is None


def test_ec_page_with_verified_buyback_lines_produces_the_issued_tranche_only():
    res = _build_ec(EC_PAGE)
    assert res.issue is None and res.buyback_rows == 2
    assert [r["isin"] for r in res.records] == ["ML0000009925"]
    flag = next(f for f in res.records[0]["validation_flags"] if f["code"] == "page_lists_buyback_securities")
    assert "2 buyback line(s)" in flag["detail"]
    assert "p.2 (RA-ML0000001112-14-2025, RA-ML0000001120-14-2025)" in flag["detail"]
    # A buyback line never creates a deal.
    bought_back = {isin for isin, _, _ in BUYBACK} | {"ML0000009933"}
    assert not {r["isin"] for r in res.records} & bought_back
    assert not {r["maturity_date"] for r in res.records} & {date(2025, 6, 16), date(2025, 6, 20)}


def test_extra_page_line_not_on_the_buyback_page_is_refused():
    res = _build_ec(ML_PAGE + [("OAT", "16/06/2025", "--", "--"), ("OAT", "30/06/2025", "--", "--")])
    assert res.records == [] and res.issue == "page_and_compte_rendu_list_different_securities"


def test_extra_page_line_with_an_amount_is_refused():
    res = _build_ec(ML_PAGE + [("OAT", "16/06/2025", "1 000,0000", "5,0000"), ("BAT", "20/06/2025", "--", "--")])
    assert res.records == [] and res.issue == "page_and_compte_rendu_list_different_securities"


def test_pdf_tranche_missing_from_the_page_is_refused():
    page = [ML_PAGE[0], ML_PAGE[2], ("OAT", "16/06/2025", "--", "--"), ("BAT", "20/06/2025", "--", "--")]
    res = _build_ec(page + [("BAT", "21/06/2025", "--", "--")], buyback=BUYBACK + [("ML0000001138", "BAT",
                                                                                     "21/06/2025")])
    assert res.records == [] and res.issue == "page_and_compte_rendu_list_different_securities"


def test_duplicated_keys_are_refused():
    page_dup = EC_PAGE + [("BAT", "20/06/2025", "--", "--")]
    assert _build_ec(page_dup).issue == "page_and_compte_rendu_list_different_securities"
    twin = [ML[0], ML[1], FxTranche("ML0000009941", "OAT", "3 ans", "12/06/2028", "100", "9,00%", "6,15%")]
    report = parse_compte_rendu_page(_text(compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", twin,
                                                                coupon_tokens=["6,15%", "6,15%"])), 1)
    res = _build_ec([ML_PAGE[0], ML_PAGE[1], ("OAT", "12/06/2028", "100,0000", "9,0000"),
                     ("OAT", "16/06/2025", "--", "--")], reports=[report])
    assert res.records == [] and res.issue == "page_and_compte_rendu_list_different_securities"


def test_paired_tranche_with_discordant_amount_or_yield_is_refused():
    page = [ML_PAGE[0], ("OAT", "12/06/2028", "10 000,0000", "9,2156"), ML_PAGE[2]] + EC_PAGE[3:]
    assert _build_ec(page).issue == "retained_amount_differs_ML0000009925"
    page = [ML_PAGE[0], ("OAT", "12/06/2028", "10 345,0000", "8,0000"), ML_PAGE[2]] + EC_PAGE[3:]
    res = _build_ec(page)
    assert res.issue == "yield_differs_ML0000009925" and res.records == []


def test_issuer_value_that_is_another_label_is_a_layout_error():
    lines = compte_rendu_lines("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
    lines[lines.index("ETAT DU MALI")] = "Nature des titres"
    with pytest.raises(LayoutError, match="issuer label not found"):
        parse_compte_rendu_page(_text(lines), 1)


# --------------------------------------------------------------------------- issuer counted once (Lot 0)


def test_issuer_is_counted_by_one_criterion_only():
    issuer = [("issuer", None, "ETAT DU MALI")]
    a = DealFacts(id="a", project_name="Projet X", participants=issuer, issuer_entities=frozenset({"ent-ML"}))
    b = DealFacts(id="b", project_name="Projet X", participants=issuer, issuer_entities=frozenset({"ent-ML"}))
    criteria = matched_criteria(a, b)
    assert "issuer" in criteria and "participants" not in criteria
    # Anchor + the same issuer only = 2 criteria: no longer enough (it was 3 with the double count).
    assert criteria == ["project", "issuer"] and not is_candidate(criteria)


def test_other_participants_still_count_and_name_only_issuers_compare_by_name():
    a = DealFacts(id="a", project_name="P", participants=[("issuer", None, "État du Mali"),
                                                         ("arranger", None, "SGI Mali")])
    b = DealFacts(id="b", project_name="P", participants=[("issuer", None, "ETAT DU MALI"),
                                                         ("arranger", None, "SGI MALI")])
    assert matched_criteria(a, b) == ["project", "participants", "issuer"]
    c = DealFacts(id="c", project_name="P", participants=[("issuer", None, "Etat du Niger")])
    assert "issuer" not in matched_criteria(a, c)
