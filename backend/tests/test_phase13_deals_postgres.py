"""
Phase 13 — Deal Intelligence against a REAL PostgreSQL database.

Same scratch-database mechanism as Phases 8C–12 (never the dev database).
Tests run in file order: imports first, then human decisions in the Review Center.

Seed: Banque A (CI), Banque B (SN); two sources; documents
  doc_a (source 1, 40 pages), doc_b (source 1, page count unknown), doc_c (source 2, 10 pages).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

DQ = "/api/v1/data-quality"
DEALS = "/api/v1/deals"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase13_deals_pytest"
    asyncio.run(
        _exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"')
    )
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    ids = asyncio.run(_seed(_async_dsn(params, test_db)))
    yield {"url": _async_dsn(params, test_db), "ids": ids}

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.document import Document
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()
        s1, s2 = (await db.execute(select(Source).order_by(Source.name).limit(2))).scalars().all()
        a = Institution(name_official="Banque A", institution_type="bank", country_id=ci.id, status="active")
        b = Institution(name_official="Banque B", institution_type="bank", country_id=sn.id, status="active")
        db.add_all([a, b])
        await db.flush()
        docs = {
            "doc_a": Document(title="Communiqué A", document_type="press_release", source_id=s1.id, page_count=40,
                              download_status="downloaded", extraction_status="skipped"),
            "doc_b": Document(title="Rapport B", document_type="annual_report", source_id=s1.id,
                              download_status="downloaded", extraction_status="skipped"),
            "doc_c": Document(title="Note C", document_type="other", source_id=s2.id, page_count=10,
                              download_status="downloaded", extraction_status="skipped"),
        }
        db.add_all(docs.values())
        await db.commit()
        ids = {"A": a.id, "B": b.id, "s1": s1.id, "s2": s2.id} | {k: d.id for k, d in docs.items()}
    await engine.dispose()
    return ids


@pytest_asyncio.fixture
async def maker(pg_db: dict):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(pg_db["url"])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def api(maker) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db_session
    from app.main import create_app

    async def override() -> AsyncGenerator:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def do_import(maker, records: list[dict], *, name: str = "deals.json", actor: str = "analyst-1"):
    from scraping.deals.importer import import_file

    async with maker() as db:
        return await import_file(db, name, json.dumps(records, default=str), actor=actor)


async def deal_count(maker) -> int:
    from sqlalchemy import func, select

    from app.models.deal import Deal

    async with maker() as db:
        return (await db.execute(select(func.count(Deal.id)))).scalar_one()


def src(i, key="doc_a", source="s1", page=3, fields=("title",), ref="s1", **kw):
    return {"ref": ref, "document_id": i[key], "source_id": i[source], "page": page, "fields": list(fields), **kw}


def full_deal(i, **over):
    deal = {
        "title": "Prêt syndiqué Autoroute du Nord",
        "deal_type": "syndicated_loan", "country_code": "SN", "sector": "infrastructure",
        "project_name": "Autoroute du Nord", "amount_original": "25 milliards FCFA", "amount": "25000000000",
        "currency": "XOF", "unit": "units", "signing_date": "2024-03-15",
        "participants": [
            {"role": "borrower", "name": "État du Sénégal", "source_ref": "s1"},
            {"role": "arranger", "name": "Banque A", "institution_id": i["A"], "source_ref": "s1"},
            {"role": "lender", "name": "Banque B", "institution_id": i["B"], "source_ref": "s2",
             "commitment_amount": "5000000000", "commitment_currency": "XOF"},
        ],
        "sources": [
            src(i, fields=("title", "deal_type", "country_code", "sector", "project_name", "amount_original",
                           "amount", "currency", "unit"), excerpt="Tableau des financements"),
            src(i, key="doc_c", source="s2", page=7, ref="s2", fields=("title", "signing_date")),
        ],
    }
    deal.update(over)
    return deal


# ------------------------------------------------------------------ import


@pytest.mark.asyncio
async def test_json_import_creates_needs_review_deal_with_field_provenance(api, maker, pg_db):
    i = pg_db["ids"]
    report = await do_import(maker, [full_deal(i)])
    (deal_id,) = report.created_ids
    pg_db["ids"]["deal1"] = deal_id
    d = (await api.get(f"{DEALS}/{deal_id}")).json()
    assert d["status"] == "needs_review" and d["verified_at"] is None
    assert Decimal(d["amount"]) == Decimal("25000000000") and d["currency"] == "XOF"
    # Unpublished terms stay NULL: never 0.
    for f in ("interest_rate", "interest_rate_type", "benchmark", "spread_bps", "maturity_months",
              "grace_period_months", "fees", "guarantees", "announcement_date", "financial_close_date",
              "closing_date"):
        assert d[f] is None, f
    # Multi-source, field-level provenance.
    by_id = {s["id"]: s for s in d["sources"]}
    assert {by_id[x]["document_id"] for x in d["field_provenance"]["title"]} == {i["doc_a"], i["doc_c"]}
    assert [by_id[x]["document_id"] for x in d["field_provenance"]["signing_date"]] == [i["doc_c"]]
    assert [by_id[x]["page_number"] for x in d["field_provenance"]["amount"]] == [3]
    # Participants: roles exactly as imported, never deduced; institution links only when given.
    roles = {(p["role"], p["participant_name"], p["institution_id"]) for p in d["participants"]}
    assert roles == {("borrower", "État du Sénégal", None), ("arranger", "Banque A", i["A"]),
                     ("lender", "Banque B", i["B"])}
    assert d["borrowers"] == ["État du Sénégal"] and d["arrangers"] == ["Banque A"]
    (event,) = (await api.get(f"{DEALS}/{deal_id}/history")).json()
    assert (event["action"], event["previous_status"], event["new_status"], event["actor"]) == (
        "import", "none", "needs_review", "analyst-1")
    assert event["deal_id"] == deal_id and event["financial_data_id"] is None


@pytest.mark.asyncio
async def test_csv_import_and_missing_values_stay_missing(api, maker, pg_db):
    from scraping.deals.importer import import_file

    i = pg_db["ids"]
    text = (
        "title,deal_type,country_code,sources,participants\n"
        f'Ligne de crédit commerce,trade_finance,CI,"s1|{i["doc_b"]}|{i["s1"]}|120|title,deal_type,country_code",'
        f'borrower|Société X||s1\n'
    )
    async with maker() as db:
        report = await import_file(db, "deals.csv", text, actor="analyst-2")
    d = (await api.get(f"{DEALS}/{report.created_ids[0]}")).json()
    pg_db["ids"]["deal_csv"] = d["id"]
    assert d["status"] == "needs_review" and d["country_code"] == "CI"
    assert d["amount"] is None and d["currency"] is None and d["interest_rate"] is None
    (p,) = d["participants"]
    assert (p["role"], p["institution_id"]) == ("borrower", None)  # name only: no institution invented


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate, code", [
    (lambda i, r: r["sources"][0].update(document_id="missing-doc"), "document_not_found"),
    (lambda i, r: r["sources"][0].update(source_id="missing-src"), "source_not_found"),
    (lambda i, r: r["sources"][0].update(source_id=i["s2"]), "source_mismatch"),
    (lambda i, r: r["sources"][0].update(page=41), "page_out_of_range"),
    (lambda i, r: r["participants"][1].update(institution_id="missing-inst"), "institution_not_found"),
    (lambda i, r: r.update(country_code="ZZ"), "country_not_found"),
])
async def test_invalid_reference_refuses_the_whole_file(maker, pg_db, mutate, code):
    from scraping.deals.importer import DealImportError

    i = pg_db["ids"]
    before = await deal_count(maker)
    bad = full_deal(i, title="Bad")
    mutate(i, bad)
    with pytest.raises(DealImportError) as err:
        await do_import(maker, [full_deal(i, title="Valid one", project_name="Autre"), bad])
    assert code in {x.code for x in err.value.issues}
    assert {x.row for x in err.value.issues if x.code == code} == {2}
    assert await deal_count(maker) == before  # all or nothing


@pytest.mark.asyncio
async def test_status_in_the_file_is_never_honoured(maker, pg_db):
    from scraping.deals.importer import DealImportError

    with pytest.raises(DealImportError):
        await do_import(maker, [full_deal(pg_db["ids"], status="verified")])


@pytest.mark.asyncio
async def test_cli_dry_run_and_refusal(pg_db, tmp_path):
    i = pg_db["ids"]
    env = {**os.environ, "DATABASE_URL": pg_db["url"]}
    good = tmp_path / "good.json"
    good.write_text(json.dumps([full_deal(i, title="Dry run deal", project_name="Dry")]), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    run = [sys.executable, "-m", "scraping", "import-deals", "--actor", "cli-tester", "--file"]
    ok = subprocess.run([*run, str(good), "--dry-run"], cwd=BACKEND, env=env, capture_output=True, text=True,
                        encoding="utf-8", timeout=120)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "dry run, nothing written" in ok.stdout
    ko = subprocess.run([*run, str(bad)], cwd=BACKEND, env=env, capture_output=True, text=True,
                        encoding="utf-8", timeout=120)
    assert ko.returncode == 2 and "invalid_json" in ko.stdout


# ------------------------------------------------------------------ duplicate candidates


@pytest.mark.asyncio
async def test_similar_deal_becomes_a_candidate_never_a_merge(api, maker, pg_db):
    i = pg_db["ids"]
    report = await do_import(maker, [full_deal(
        i, title="Financement de l'autoroute du Nord (Sénégal)", amount="24500000000", signing_date="2024-04-02",
        sources=[src(i, key="doc_b", page=12, fields=("title", "deal_type", "country_code", "sector", "project_name",
                                                         "amount_original", "amount", "currency", "unit",
                                                         "signing_date")),
                 src(i, key="doc_c", source="s2", page=8, ref="s2", fields=("title",))],
    )], name="deals-2.json")
    (new_id,) = report.created_ids
    pg_db["ids"]["deal2"] = new_id
    ((a, b, criteria),) = report.duplicate_candidates
    assert {a, b} == {new_id, i["deal1"]}
    assert {"borrower", "project", "currency_amount", "dates"} <= set(criteria)
    d1 = (await api.get(f"{DEALS}/{i['deal1']}")).json()
    d2 = (await api.get(f"{DEALS}/{new_id}")).json()
    (cand,) = d1["duplicates"]
    assert cand["state"] == "duplicate_candidate" and cand["other_deal_id"] == new_id
    assert d1["merged_into_deal_id"] is None and d2["merged_into_deal_id"] is None
    assert d2["status"] == "needs_review" and d1["duplicate_candidates"] == 1
    pg_db["ids"]["candidate"] = cand["id"]
    listed = (await api.get(f"{DQ}/deal-duplicates")).json()
    assert [c["id"] for c in listed["items"]] == [cand["id"]]


# ------------------------------------------------------------------ Review Center


@pytest.mark.asyncio
async def test_deals_enter_the_existing_review_center(api, pg_db):
    q = (await api.get(f"{DQ}/deals")).json()
    assert {pg_db["ids"]["deal1"], pg_db["ids"]["deal2"], pg_db["ids"]["deal_csv"]} <= {d["id"] for d in q["items"]}
    s = (await api.get(f"{DQ}/summary")).json()
    assert s["deals_needs_review"] == 3 and s["deals_duplicate_candidates"] == 1 and s["deals_verified"] == 0


async def act(api, deal_id, action, **payload):
    body = {"actor": "analyst-1", "reason": "Checked against the document", **payload}
    return await api.post(f"{DQ}/deals/{deal_id}/{action}", json=body)


@pytest.mark.asyncio
async def test_verify_only_through_human_review_and_after_duplicate_decision(api, pg_db):
    i = pg_db["ids"]
    r = await act(api, i["deal1"], "verify")
    assert r.status_code == 422  # never a direct jump needs_review -> verified
    d = (await api.get(f"{DQ}/deals/{i['deal1']}")).json()
    stale = await act(api, i["deal1"], "review", expected_status="reviewed")
    assert stale.status_code == 409
    r = await act(api, i["deal1"], "review", expected_status=d["status"], expected_updated_at=d["updated_at"])
    assert r.status_code == 200 and r.json()["status"] == "reviewed"
    assert "verify" not in r.json()["allowed_actions"]  # open duplicate candidate
    r = await act(api, i["deal1"], "verify")
    assert r.status_code == 409 and "unresolved_duplicate_candidate" in r.json()["error"]["message"]
    assert (await act(api, "no-such-deal", "review")).status_code == 404
    assert (await act(api, i["deal1"], "reject", reason="   ")).status_code == 422
    assert (await act(api, i["deal1"], "review", actor="x" * 256)).status_code == 422


@pytest.mark.asyncio
async def test_same_deal_decision_keeps_every_source_and_is_audited(api, pg_db):
    i = pg_db["ids"]
    url = f"{DQ}/deal-duplicates/{i['candidate']}/decide"
    bad = await api.post(url, json={"decision": "same_deal", "actor": "a", "reason": "r", "primary_deal_id": "x"})
    assert bad.status_code == 422
    r = await api.post(url, json={"decision": "same_deal", "primary_deal_id": i["deal1"], "actor": "analyst-3",
                                  "reason": "Same signing, two press sources"})
    assert r.status_code == 200 and r.json()["state"] == "same_deal"
    again = await api.post(url, json={"decision": "distinct_deals", "actor": "analyst-4", "reason": "no"})
    assert again.status_code == 409  # already decided: never overwritten silently

    d1 = (await api.get(f"{DEALS}/{i['deal1']}")).json()
    d2 = (await api.get(f"{DEALS}/{i['deal2']}")).json()
    assert d2["merged_into_deal_id"] == i["deal1"] and d2["status"] == "needs_review"  # nothing deleted
    (merged,) = d1["merged_deals"]
    assert merged["id"] == i["deal2"] and {s["document_id"] for s in merged["sources"]} == {i["doc_b"], i["doc_c"]}
    assert d1["sources"] and len(d1["sources"]) == 2  # the primary keeps its own sources untouched
    assert d1["duplicates"][0]["decided_by"] == "analyst-3"
    for deal_id in (i["deal1"], i["deal2"]):
        actions = [e["action"] for e in (await api.get(f"{DEALS}/{deal_id}/history")).json()]
        assert actions[-1] == "mark_same_deal"
    # The attached deal leaves the explorer by default, never the database.
    listed = {d["id"] for d in (await api.get(DEALS)).json()["items"]}
    assert i["deal2"] not in listed and i["deal1"] in listed
    assert i["deal2"] in {d["id"] for d in (await api.get(DEALS, params={"include_merged": True})).json()["items"]}

    r = await act(api, i["deal1"], "verify")
    assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["verified_by"] == "analyst-1"
    history = [(e["action"], e["previous_status"], e["new_status"])
               for e in (await api.get(f"{DEALS}/{i['deal1']}/history")).json()]
    assert history == [("import", "none", "needs_review"), ("review", "needs_review", "reviewed"),
                       ("mark_same_deal", "reviewed", "reviewed"), ("verify", "reviewed", "verified")]


@pytest.mark.asyncio
async def test_reject_is_final_and_traced(api, pg_db):
    i = pg_db["ids"]
    r = await act(api, i["deal_csv"], "reject", reason="Not a financing transaction")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert (await act(api, i["deal_csv"], "reject")).status_code == 422
    assert (await act(api, i["deal_csv"], "review")).status_code == 422


# ------------------------------------------------------------------ explorer, analytics, links


@pytest.mark.asyncio
async def test_multi_currency_amounts_are_never_summed_together(api, maker, pg_db):
    i = pg_db["ids"]
    report = await do_import(maker, [
        full_deal(i, title="Emprunt obligataire EUR", deal_type="bond", project_name="Programme EUR",
                  amount="10000000", currency="EUR", signing_date="2023-06-01",
                  participants=[{"role": "borrower", "name": "Société Y", "source_ref": "s1"},
                                {"role": "arranger", "name": "Banque B", "institution_id": i["B"], "source_ref": "s1"}]),
    ], name="deals-3.json")
    (eur_id,) = report.created_ids
    for action in ("review", "verify"):
        assert (await act(api, eur_id, action)).status_code == 200
    rows = {r["key"]: r for r in (await api.get(f"{DEALS}/analytics", params={"dimension": "country"})).json()["rows"]}
    amounts = {(a["currency"], a["unit"]): Decimal(a["total"]) for a in rows["SN"]["amounts"]}
    assert amounts == {("XOF", "units"): Decimal("25000000000"), ("EUR", "units"): Decimal("10000000")}
    assert rows["SN"]["deals"] == 2  # rejected and attached deals are not counted
    by_type = {r["key"]: r for r in (await api.get(f"{DEALS}/analytics", params={"dimension": "type"})).json()["rows"]}
    assert set(by_type) == {"syndicated_loan", "bond"}
    inst = {r["key"]: r["label"] for r in (await api.get(f"{DEALS}/analytics",
                                                         params={"dimension": "institution"})).json()["rows"]}
    assert inst == {i["A"]: "Banque A", i["B"]: "Banque B"}
    assert (await api.get(f"{DEALS}/analytics", params={"dimension": "best"})).status_code == 422


@pytest.mark.asyncio
async def test_explorer_filters_and_institution_links(api, pg_db):
    i = pg_db["ids"]

    async def ids(**params):
        r = await api.get(DEALS, params=params)
        assert r.status_code == 200, r.text
        return {d["id"] for d in r.json()["items"]}

    all_ids = await ids()
    eur = next(d for d in (await api.get(DEALS, params={"currency": "EUR"})).json()["items"])
    assert await ids(bank=i["B"]) == {i["deal1"], eur["id"]}           # Institution -> Deals
    assert await ids(bank=i["A"]) == {i["deal1"]}
    assert await ids(bank=i["B"], participant_role="arranger") == {eur["id"]}
    assert await ids(participant_role="lender") == {i["deal1"]}
    assert await ids(arranger=i["A"]) == {i["deal1"]}
    assert await ids(arranger="banque b") == {eur["id"]}
    assert await ids(borrower="Sénégal") == {i["deal1"]}
    assert await ids(year=2023) == {eur["id"]}
    assert await ids(country="CI") == {i["deal_csv"]}
    assert await ids(status="verified") == {i["deal1"], eur["id"]}
    assert await ids(deal_type="bond", sector="infrastructure") == {eur["id"]}
    assert i["deal_csv"] in all_ids  # rejected deals stay listed with their status
    assert (await api.get(DEALS, params={"currency": "fcfa"})).status_code == 422
    assert (await api.get(DEALS, params={"page_size": 101})).status_code == 422
    # Deal -> Institution: participants carry the institution id and its name.
    d = (await api.get(f"{DEALS}/{i['deal1']}")).json()
    assert {p["institution_name"] for p in d["participants"] if p["institution_id"]} == {"Banque A", "Banque B"}
    assert (await api.get(f"{DEALS}/missing")).status_code == 404


# ------------------------------------------------------------------ audit journal integrity


@pytest.mark.asyncio
async def test_audit_journal_single_target_is_enforced_by_the_database(maker, pg_db):
    from sqlalchemy.exc import IntegrityError

    from app.models.review_event import FinancialDataReviewEvent

    async with maker() as db:
        db.add(FinancialDataReviewEvent(action="review", previous_status="a", new_status="b"))
        with pytest.raises(IntegrityError):
            await db.commit()
    async with maker() as db:
        db.add(FinancialDataReviewEvent(action="best", previous_status="a", new_status="b",
                                        deal_id=pg_db["ids"]["deal1"]))
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_no_code_path_updates_or_deletes_audit_events():
    """Append-only by construction: no UPDATE / DELETE on the journal anywhere in the code."""
    import re

    pattern = re.compile(r"(update|delete)\(\s*FinancialDataReviewEvent|FinancialDataReviewEvent\)\.(update|delete)")
    offenders = [
        p for root in ("app", "scraping") for p in (BACKEND / root).rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
