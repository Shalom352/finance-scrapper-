"""
Phase 13 — Deal Intelligence, pure unit tests (no database).

Import validation (Pydantic), JSON / CSV parsing, duplicate-candidate criteria.
DATA MISSING > DATA WRONG: an absent field is None, never 0; nothing is inferred.
"""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from scraping.deals.duplicates import DealFacts, is_candidate, matched_criteria, normalize_name
from scraping.deals.importer import (
    DealImportError,
    parse_csv,
    parse_file,
    parse_json,
    validate_records,
)
from scraping.deals.schemas import DealImportRecord

SRC = {"ref": "s1", "document_id": "doc-1", "source_id": "src-1", "page": 4}


def record(**over):
    base = {"title": "Prêt syndiqué", "sources": [{**SRC, "fields": ["title"]}]}
    base.update(over)
    return base


# ---------------------------------------------------------------- Pydantic validation


def test_minimal_record_keeps_every_financial_field_missing():
    r = DealImportRecord.model_validate(record())
    for f in ("amount", "interest_rate", "spread_bps", "maturity_months", "grace_period_months", "fees",
              "guarantees", "announcement_date", "signing_date", "financial_close_date", "closing_date",
              "currency", "deal_type"):
        assert getattr(r, f) is None, f  # never 0, never ""


def test_types_and_dates_are_strict():
    r = DealImportRecord.model_validate(record(
        amount="25000000000", currency="XOF", unit="units", signing_date="2024-03-15", maturity_months=84,
        sources=[{**SRC, "fields": ["title", "amount", "currency", "unit", "signing_date", "maturity_months"]}],
    ))
    assert r.amount == Decimal("25000000000") and r.signing_date == date(2024, 3, 15)
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(signing_date="15/03/2024",
                                               sources=[{**SRC, "fields": ["title", "signing_date"]}]))
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(maturity_months="seven",
                                               sources=[{**SRC, "fields": ["title", "maturity_months"]}]))


@pytest.mark.parametrize("bad", [
    {"amount": 0, "currency": "XOF"},     # an amount is published and positive, or absent
    {"amount": -5, "currency": "XOF"},
    {"maturity_months": 0},
    {"grace_period_months": -1},
])
def test_zero_or_negative_values_are_refused(bad):
    fields = ["title", *bad.keys()]
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(**bad, sources=[{**SRC, "fields": fields}]))


def test_currency_must_be_iso_4217_and_amount_needs_currency():
    with pytest.raises(ValidationError, match="unknown ISO 4217"):
        DealImportRecord.model_validate(record(currency="FCFA", sources=[{**SRC, "fields": ["title", "currency"]}]))
    with pytest.raises(ValidationError, match="currency is required"):
        DealImportRecord.model_validate(record(amount=10, sources=[{**SRC, "fields": ["title", "amount"]}]))


def test_provenance_is_mandatory():
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate({"title": "X", "sources": []})
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate({"title": "X"})
    with pytest.raises(ValidationError, match="fields without source: amount, currency"):
        DealImportRecord.model_validate(record(amount=10, currency="XOF"))
    with pytest.raises(ValidationError, match="attest fields that are empty"):
        DealImportRecord.model_validate(record(sources=[{**SRC, "fields": ["title", "amount"]}]))
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(sources=[{**SRC, "page": 0, "fields": ["title"]}]))


def test_status_and_unknown_columns_are_refused():
    with pytest.raises(ValidationError, match="Extra inputs"):
        DealImportRecord.model_validate(record(status="verified"))
    with pytest.raises(ValidationError, match="Extra inputs"):
        DealImportRecord.model_validate(record(borrower="Banque A"))  # a role is never a free column


def test_participants_need_an_explicit_known_role_and_a_source():
    ok = DealImportRecord.model_validate(record(participants=[{"role": "arranger", "name": "B", "source_ref": "s1"}]))
    assert ok.participants[0].role == "arranger" and ok.participants[0].institution_id is None
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(participants=[{"role": "leader", "name": "B", "source_ref": "s1"}]))
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(record(participants=[{"name": "B", "source_ref": "s1"}]))
    with pytest.raises(ValidationError, match="unknown source refs"):
        DealImportRecord.model_validate(record(participants=[{"role": "lender", "name": "B", "source_ref": "s9"}]))
    with pytest.raises(ValidationError, match="commitment_currency is required"):
        DealImportRecord.model_validate(record(participants=[
            {"role": "lender", "name": "B", "source_ref": "s1", "commitment_amount": 5}]))


# ---------------------------------------------------------------- parsing


def test_invalid_json_and_csv_are_refused_with_a_code():
    for text, code in (("{not json", "invalid_json"), ('{"title": "x"}', "invalid_json")):
        with pytest.raises(DealImportError) as err:
            parse_json(text)
        assert err.value.issues[0].code == code
    with pytest.raises(DealImportError) as err:
        parse_csv("title,sources\n")
    assert err.value.issues[0].code == "invalid_csv"
    with pytest.raises(DealImportError) as err:
        parse_file("deals.xlsx", "")
    assert err.value.issues[0].code == "unsupported_format"


def test_csv_encoding_of_sources_and_participants():
    text = (
        "title,amount,currency,sources,participants\n"
        'Prêt A,100,XOF,"s1|doc-1|src-1|3|title,amount,currency|Tableau 2;s2|doc-2|src-1|7|title",'
        '"arranger|Banque B||s1;lender|Banque C|inst-c|s2|40|XOF"\n'
        "Prêt B,,,s1|doc-1|src-1|4|title,\n"
    )
    raw = parse_csv(text)
    recs = validate_records(raw)
    assert recs[0].sources[0].excerpt == "Tableau 2" and recs[0].sources[1].page == 7
    assert [(p.role, p.institution_id) for p in recs[0].participants] == [("arranger", None), ("lender", "inst-c")]
    assert recs[1].amount is None and recs[1].currency is None  # empty cell = not published


def test_validation_reports_every_record_and_writes_nothing():
    with pytest.raises(DealImportError) as err:
        validate_records([record(), record(currency="ZZZ", sources=[{**SRC, "fields": ["title", "currency"]}]),
                          {"title": "no source"}])
    rows = {i.row for i in err.value.issues}
    assert rows == {2, 3}


# ---------------------------------------------------------------- duplicate candidates


def facts(i, **kw):
    base = dict(deal_type="syndicated_loan", project_name="Autoroute du Nord", amount=Decimal("100"),
                currency="XOF", signing_date=date(2024, 3, 1),
                participants=[("borrower", None, "État du Sénégal"), ("arranger", "inst-b", "Banque B")])
    base.update(kw)
    return DealFacts(id=i, **base)


def test_name_normalization_is_technical_only():
    assert normalize_name("  État du SÉNÉGAL. ") == normalize_name("etat du senegal")
    assert normalize_name("") is None


def test_candidate_needs_an_anchor_and_three_explicit_criteria():
    crit = matched_criteria(facts("a"), facts("b", amount=Decimal("104"), signing_date=date(2024, 5, 20)))
    assert crit == ["borrower", "project", "currency_amount", "dates", "deal_type", "participants"]
    assert is_candidate(crit)
    # Same amount/currency/type/dates but no shared borrower nor project: never a candidate.
    other = facts("c", project_name="Port", participants=[("borrower", None, "Autre emprunteur")])
    crit2 = matched_criteria(facts("a"), other)
    assert "borrower" not in crit2 and "project" not in crit2 and not is_candidate(crit2)


def test_amounts_in_other_currencies_or_far_apart_do_not_match():
    assert "currency_amount" not in matched_criteria(facts("a"), facts("b", currency="EUR"))
    assert "currency_amount" not in matched_criteria(facts("a"), facts("b", amount=Decimal("106")))
    assert "currency_amount" not in matched_criteria(facts("a"), facts("b", amount=None))
    assert "dates" not in matched_criteria(facts("a"), facts("b", signing_date=date(2024, 6, 1)))
