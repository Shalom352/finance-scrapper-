"""
Phase 11 — Financial data explorer: pure unit tests (no database).

Row qualification delegates to the existing authority rule (qualify_metric →
EligibilityEngine); the CSV export writes values exactly as stored.
"""
import csv
import io
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scraping.consolidation.models import ObservationSummary
from scraping.financial_data.export import (
    CSV_COLUMNS,
    EXPORT_MAX_ROWS,
    ExportTooLargeError,
    build_csv,
)
from scraping.financial_data.qualification import logical_key, qualify_rows


def obs(id_, value="100", *, status="extracted", metric="total_actifs", year=2024,
        period_type="annual", scope="individual", inst="I1", currency="XOF"):
    return ObservationSummary(
        id=id_, institution_id=inst, metric_code=metric, source_id="S", document_id="D",
        period_year=year, period_type=period_type, scope=scope, value_original=str(value),
        value_normalized=None if value is None else Decimal(str(value)),
        currency_normalized=currency, status=status,
    )


# ---------------------------------------------------------------- qualification

def test_single_extracted_row_is_authoritative():
    o = obs("a")
    assert qualify_rows([o], [o]) == {"a": ("authoritative", None)}


def test_verified_wins_and_other_row_is_superseded():
    v, e = obs("v", "1000", status="verified"), obs("e", "990")
    q = qualify_rows([v, e], [v, e])
    assert q["v"] == ("authoritative", None)
    assert q["e"] == ("superseded", "v")


def test_divergent_unverified_values_are_conflict_for_every_row():
    a, b = obs("a", "100"), obs("b", "130")
    assert qualify_rows([a, b], [a, b]) == {"a": ("conflict", None), "b": ("conflict", None)}


def test_needs_review_is_never_authoritative():
    n = obs("n", status="needs_review")
    assert qualify_rows([n], [n]) == {"n": ("needs_review", None)}


def test_rejected_row_is_labelled_rejected_and_does_not_count():
    r, e = obs("r", "55", status="rejected"), obs("e", "60")
    q = qualify_rows([r, e], [r, e])
    assert q["r"] == ("rejected", None)
    assert q["e"] == ("authoritative", None)  # the rejected value never creates a conflict


def test_missing_normalized_value_is_never_zero():
    m = obs("m", None)
    assert qualify_rows([m], [m]) == {"m": ("missing_value", None)}


def test_siblings_outside_the_page_decide_the_row():
    # Only "e" is on the page; the verified sibling on another page still wins.
    v, e = obs("v", "1000", status="verified"), obs("e", "990")
    assert qualify_rows([e], [v, e]) == {"e": ("superseded", "v")}


def test_keys_do_not_mix_scope_period_or_year():
    rows = [
        obs("ind", "100"),
        obs("cons", "900", scope="consolidated"),
        obs("semi", "48", period_type="semi_annual"),
        obs("y23", "80", year=2023),
    ]
    assert len({logical_key(o) for o in rows}) == 4
    assert {k: v[0] for k, v in qualify_rows(rows, rows).items()} == dict.fromkeys(
        ["ind", "cons", "semi", "y23"], "authoritative")


# ---------------------------------------------------------------- export

def item(**kw):
    base = dict(
        institution_name="Banque A", institution_id="I1", country_code="CI", metric_code="total_actifs",
        period_year=2024, period_type="annual", period_label=None, scope="individual",
        value_normalized=Decimal("1000000000.50"), unit_normalized="unit", currency_normalized="XOF",
        value_original="1 000 000", unit_original="millions", currency_original="XOF", status="verified",
        qualification="authoritative", source_name="BCEAO", document_title="Rapport 2024",
        page_number=84, id="d1",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def rows_of(text):
    return list(csv.reader(io.StringIO(text)))


def test_csv_header_and_exact_values():
    r = rows_of(build_csv([item()]))
    assert tuple(r[0]) == CSV_COLUMNS
    row = dict(zip(r[0], r[1], strict=True))
    assert row["value_normalized"] == "1000000000.50"  # no float rounding, no exponent
    assert row["currency"] == "XOF" and row["page"] == "84" and row["data_id"] == "d1"


def test_csv_missing_value_is_empty_not_zero():
    r = rows_of(build_csv([item(value_normalized=None, page_number=None, qualification="missing_value")]))
    row = dict(zip(r[0], r[1], strict=True))
    assert row["value_normalized"] == "" and row["page"] == ""


def test_csv_has_no_total_or_aggregate_row():
    text = build_csv([item(id="a"), item(id="b", currency_normalized="EUR")])
    r = rows_of(text)
    assert len(r) == 3  # header + 2 rows, nothing appended
    assert not re.search(r"(?i)\b(total|sum|average|moyenne)\b", "\n".join(",".join(x[:1]) for x in r[1:]))


def test_csv_empty_selection_is_header_only():
    assert rows_of(build_csv([])) == [list(CSV_COLUMNS)]


def test_export_too_large_error_carries_total():
    err = ExportTooLargeError(EXPORT_MAX_ROWS + 1)
    assert err.total == EXPORT_MAX_ROWS + 1 and isinstance(err, ValueError)


# ---------------------------------------------------------------- router contract

def test_new_routes_are_declared_before_the_id_route():
    from app.main import create_app

    paths = [r.path for r in create_app().routes]
    idx = paths.index("/api/v1/financial-data/{data_id}")
    assert paths.index("/api/v1/financial-data/export") < idx
    assert paths.index("/api/v1/financial-data/facets") < idx


@pytest.mark.parametrize("bad", ["score", "rating", "value;drop"])
def test_unknown_sort_is_rejected(bad):
    from fastapi.testclient import TestClient

    from app.main import create_app

    r = TestClient(create_app()).get("/api/v1/financial-data", params={"sort": bad})
    assert r.status_code == 422


# ---------------------------------------------------------------- vocabulary

FORBIDDEN = re.compile(
    r"(?i)\b(best|worst|strong|weak|leader|winner|loser|excellent|poor|buy|sell|recommend\w*|"
    r"score|rating|meilleur\w*|pire|solide|fragile|recommand\w*)\b"
)


def test_module_has_no_qualitative_vocabulary():
    root = Path(__file__).resolve().parents[1] / "scraping" / "financial_data"
    for f in root.glob("*.py"):
        assert not FORBIDDEN.search(f.read_text(encoding="utf-8")), f.name
