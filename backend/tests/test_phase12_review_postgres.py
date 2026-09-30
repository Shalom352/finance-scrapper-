"""
Phase 12 — Data Quality & Review Center against a REAL PostgreSQL database.

Same scratch-database mechanism as Phases 8C–11 (never the dev database).
Tests run in file order: read-only checks first, then human decisions whose
effects are verified on the existing consumers (rankings, comparisons,
institution profile, financial-data explorer).

Seed (individual annual 2024 unless stated):
  Banque A (CI)  capitaux_propres 100 (p.12) vs 130 (p.30), both extracted      -> conflict
                 capitaux_propres consolidated 900                              -> other scope
                 total_actifs 1000 needs_review                                 -> needs_review
  Banque B (SN)  total_actifs 700 reviewed · depots_clients 500 verified · resultat_net 50 rejected
  Banque C (CI)  depots_clients 300 XOF vs 0.5 EUR (divergent, other currency)  -> conflict
                 creances_clients: no normalized value (extracted)
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

DQ = "/api/v1/data-quality"


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase12_pytest"
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
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()
        source = (await db.execute(select(Source))).scalars().first()
        insts = {
            "A": Institution(name_official="Banque A", institution_type="bank", country_id=ci.id, status="active"),
            "B": Institution(name_official="Banque B", institution_type="bank", country_id=sn.id, status="active"),
            "C": Institution(name_official="Banque C", institution_type="bank", country_id=ci.id, status="active"),
        }
        db.add_all(insts.values())
        await db.flush()
        docs = {}
        for k, inst in insts.items():
            docs[k] = Document(title=f"Rapport annuel {k}", document_type="annual_report", source_id=source.id,
                               institution_id=inst.id, download_status="downloaded", extraction_status="extracted")
            db.add(docs[k])
        await db.flush()

        rows: dict[str, FinancialData] = {}

        def fd(name, k, metric, value, *, scope="individual", status="extracted", page=12, currency="XOF"):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "seed"} if status == "verified" else {}
            rows[name] = FinancialData(
                institution_id=insts[k].id, source_id=source.id, document_id=docs[k].id, metric_code=metric,
                scope=scope, period_type="annual", period_year=2024, value_original=str(value),
                unit_original="unit", currency_original=currency,
                value_normalized=None if value is None else Decimal(str(value)),
                unit_normalized="unit", currency_normalized=currency, extraction_method="pdf_table",
                status=status, page_number=page, **extra,
            )
            db.add(rows[name])

        fd("a_cp_100", "A", "capitaux_propres", 100)
        fd("a_cp_130", "A", "capitaux_propres", 130, page=30)
        fd("a_cp_cons", "A", "capitaux_propres", 900, scope="consolidated")
        fd("a_ta_nr", "A", "total_actifs", 1000, status="needs_review")
        fd("b_ta_rev", "B", "total_actifs", 700, status="reviewed")
        fd("b_dc_ver", "B", "depots_clients", 500, status="verified")
        fd("b_rn_rej", "B", "resultat_net", 50, status="rejected")
        fd("c_dc_xof", "C", "depots_clients", 300)
        fd("c_dc_eur", "C", "depots_clients", "0.5", currency="EUR")
        fd("c_cc_missing", "C", "creances_clients", None)
        await db.commit()
        ids = {k: i.id for k, i in insts.items()} | {k: r.id for k, r in rows.items()}
    await engine.dispose()
    return ids


@pytest.fixture
async def api(pg_db: dict) -> AsyncGenerator[AsyncClient, None]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.session import get_db_session
    from app.main import create_app

    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

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
    await engine.dispose()


async def ids_of(api, **params) -> set[str]:
    r = await api.get(DQ, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}


async def decide(api, data_id, action, *, actor="analyst-1", reason="Checked against p.12", **extra):
    return await api.post(f"{DQ}/{data_id}/{action}", json={"actor": actor, "reason": reason, **extra})


async def events(api, data_id):
    r = await api.get(f"{DQ}/{data_id}/history")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- read side

@pytest.mark.asyncio
async def test_queue_defaults_to_needs_review_and_conflicts(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    assert await ids_of(api) == {i["a_cp_100"], i["a_cp_130"], i["a_ta_nr"], i["c_dc_xof"], i["c_dc_eur"]}


@pytest.mark.asyncio
async def test_queue_filters_and_explicit_statuses(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    assert await ids_of(api, country_code="CI", metric_code="depots_clients") == {i["c_dc_xof"], i["c_dc_eur"]}
    assert await ids_of(api, currency_normalized="EUR") == {i["c_dc_eur"]}
    assert await ids_of(api, scope="consolidated") == set()  # 900 alone: nothing to decide
    assert await ids_of(api, country_code="SN") == set()
    assert await ids_of(api, status="verified") == {i["b_dc_ver"]}
    assert await ids_of(api, status="rejected") == {i["b_rn_rej"]}
    r = (await api.get(DQ, params={"page_size": 2, "page": 3, "sort": "institution"})).json()
    assert r["total"] == 5 and len(r["items"]) == 1 and r["has_prev"] and not r["has_next"]


@pytest.mark.asyncio
async def test_summary_counters_only(api: AsyncClient):
    s = (await api.get(f"{DQ}/summary")).json()
    assert s == {"total": 10, "extracted": 6, "needs_review": 1, "reviewed": 1, "verified": 1, "rejected": 1,
                 "conflict_keys": 2, "conflict_observations": 4, "unresolved": 5}


@pytest.mark.asyncio
async def test_detail_conflict_competing_and_other_scope(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['a_cp_100']}")).json()
    assert d["qualification"] == "conflict" and d["country_code"] == "CI"
    assert d["allowed_actions"] == ["review", "reject"]
    comp = {c["id"]: c for c in d["competing"]}
    assert set(comp) == {i["a_cp_100"], i["a_cp_130"]}
    assert Decimal(comp[i["a_cp_130"]]["difference"]) == Decimal("30")
    assert comp[i["a_cp_100"]]["difference_reason"] == "same_observation"
    assert [(c["id"], c["scope"], c["difference"]) for c in d["not_comparable"]] == [
        (i["a_cp_cons"], "consolidated", None)]
    # Provenance of the observation itself.
    obs = d["observation"]
    assert obs["document"]["title"] == "Rapport annuel A" and obs["page_number"] == 12
    assert obs["source"]["name"] and obs["extraction_method"] == "pdf_table"


@pytest.mark.asyncio
async def test_detail_other_currency_is_never_compared(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['c_dc_xof']}")).json()
    eur = next(c for c in d["competing"] if c["id"] == i["c_dc_eur"])
    assert eur["difference"] is None and eur["difference_reason"] == "currency_mismatch"
    assert eur["currency_normalized"] == "EUR"


@pytest.mark.asyncio
async def test_detail_missing_value_and_allowed_actions(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['c_cc_missing']}")).json()
    assert d["observation"]["value_normalized"] is None and d["qualification"] == "missing_value"
    assert d["allowed_actions"] == ["reject"]  # cannot be reviewed without a value
    assert (await api.get(f"{DQ}/{i['b_ta_rev']}")).json()["allowed_actions"] == ["review", "verify", "reject"]
    assert (await api.get(f"{DQ}/{i['b_rn_rej']}")).json()["allowed_actions"] == []


@pytest.mark.asyncio
async def test_unknown_observation_404(api: AsyncClient):
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await api.get(f"{DQ}/{missing}")).status_code == 404
    assert (await api.get(f"{DQ}/{missing}/history")).status_code == 404
    assert (await decide(api, missing, "reject")).status_code == 404


# ---------------------------------------------------------------- decisions

@pytest.mark.asyncio
async def test_invalid_transitions_are_422_and_leave_no_trace(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    for data_id, action in [
        (i["a_cp_100"], "verify"),       # extracted -> verified: direct jump forbidden
        (i["b_rn_rej"], "review"),       # rejected stays rejected
        (i["b_rn_rej"], "reject"),       # already rejected
        (i["c_cc_missing"], "review"),   # no value to review
    ]:
        r = await decide(api, data_id, action)
        assert r.status_code == 422, (action, r.text)
        assert r.json()["error"]["code"]
        assert await events(api, data_id) == []
    blank = await api.post(f"{DQ}/{i['a_cp_100']}/reject", json={"actor": "a", "reason": "   "})
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_stale_state_is_409_and_nothing_is_overwritten(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['b_ta_rev']}")).json()["observation"]
    r = await decide(api, i["b_ta_rev"], "verify", expected_status="extracted")
    assert r.status_code == 409
    r = await decide(api, i["b_ta_rev"], "verify", expected_status="reviewed",
                     expected_updated_at="2000-01-01T00:00:00+00:00")
    assert r.status_code == 409
    after = (await api.get(f"{DQ}/{i['b_ta_rev']}")).json()["observation"]
    assert after["status"] == "reviewed" and after["updated_at"] == d["updated_at"]
    assert await events(api, i["b_ta_rev"]) == []


@pytest.mark.asyncio
async def test_verify_reviewed_with_expected_state_persists_with_audit(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['b_ta_rev']}")).json()["observation"]
    r = await decide(api, i["b_ta_rev"], "verify", actor="analyst-2", reason="Matches audited statements",
                     expected_status=d["status"], expected_updated_at=d["updated_at"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified" and r.json()["verified_by"] == "analyst-2"
    # A second reviewer holding the old view is refused.
    r2 = await decide(api, i["b_ta_rev"], "reject", expected_status="reviewed", expected_updated_at=d["updated_at"])
    assert r2.status_code == 409
    (e,) = await events(api, i["b_ta_rev"])
    assert (e["action"], e["previous_status"], e["new_status"], e["actor"], e["reason"]) == (
        "verify", "reviewed", "verified", "analyst-2", "Matches audited statements")
    assert Decimal(e["value_before"]) == Decimal(e["value_after"]) == Decimal("700")


@pytest.mark.asyncio
async def test_resolve_conflict_with_existing_transitions(api: AsyncClient, pg_db: dict):
    i, a = pg_db["ids"], pg_db["ids"]["A"]
    # Before: divergent values -> no certified value anywhere.
    ranking = (await api.get("/api/v1/rankings", params={"metric_code": "capitaux_propres", "country_code": "CI"})).json()
    assert a not in {r["institution_id"] for r in ranking["items"]}
    comp = (await api.get("/api/v1/comparisons", params={"institution_ids": f"{a},{i['B']}",
                                                         "metric_code": "capitaux_propres"})).json()
    assert {r["institution_id"]: r["reason"] for r in comp["rows"]}[a] == "conflict"

    # Review + verify 100, then reject 130 — three separate, audited human decisions.
    assert (await decide(api, i["a_cp_100"], "review", reason="Value read on p.12")).status_code == 200
    mid = (await api.get(f"{DQ}/{i['a_cp_100']}")).json()
    assert mid["qualification"] == "conflict"  # reviewed alone does not resolve divergent values
    assert (await decide(api, i["a_cp_100"], "verify", reason="Matches audited statements")).status_code == 200
    assert (await decide(api, i["a_cp_130"], "reject", reason="Value belongs to 2023 column")).status_code == 200

    assert [e["action"] for e in await events(api, i["a_cp_100"])] == ["review", "verify"]
    assert [e["new_status"] for e in await events(api, i["a_cp_130"])] == ["rejected"]
    assert i["a_cp_100"] not in await ids_of(api) and i["a_cp_130"] not in await ids_of(api)

    # After: consumers use the verified value, the rejected one is never valid data.
    ranking = (await api.get("/api/v1/rankings", params={"metric_code": "capitaux_propres", "country_code": "CI"})).json()
    assert [(r["institution_id"], Decimal(r["value"])) for r in ranking["items"]] == [(a, Decimal("100"))]
    comp = (await api.get("/api/v1/comparisons", params={"institution_ids": f"{a},{i['B']}",
                                                         "metric_code": "capitaux_propres"})).json()
    assert Decimal({r["institution_id"]: r["value"] for r in comp["rows"]}[a]) == Decimal("100")
    prof = (await api.get(f"/api/v1/institutions/{a}/financials")).json()
    cp = next(v for v in prof["values"] if v["metric_code"] == "capitaux_propres")
    assert Decimal(cp["value_normalized"]) == Decimal("100") and cp["status"] == "verified"
    explorer = (await api.get("/api/v1/financial-data", params={"institution_ids": a, "metric_code": "capitaux_propres",
                                                               "scope": "individual", "status": "rejected"})).json()
    assert [(x["id"], x["qualification"]) for x in explorer["items"]] == [(i["a_cp_130"], "rejected")]


@pytest.mark.asyncio
async def test_reject_needs_review_is_excluded_everywhere(api: AsyncClient, pg_db: dict):
    i, a = pg_db["ids"], pg_db["ids"]["A"]
    comp = (await api.get("/api/v1/comparisons", params={"institution_ids": f"{a},{i['B']}",
                                                         "metric_code": "total_actifs"})).json()
    assert {r["institution_id"]: r["reason"] for r in comp["rows"]}[a] == "needs_review"
    assert (await decide(api, i["a_ta_nr"], "reject", reason="Scan unreadable")).status_code == 200
    comp = (await api.get("/api/v1/comparisons", params={"institution_ids": f"{a},{i['B']}",
                                                         "metric_code": "total_actifs"})).json()
    rows = {r["institution_id"]: r for r in comp["rows"]}
    assert rows[a]["value"] is None and rows[a]["reason"] == "rejected_only"
    assert Decimal(rows[i["B"]]["value"]) == Decimal("700")  # verified earlier through the Review Center
    s = (await api.get(f"{DQ}/summary")).json()
    assert (s["needs_review"], s["rejected"], s["verified"], s["conflict_keys"], s["unresolved"]) == (0, 3, 3, 1, 2)


@pytest.mark.asyncio
async def test_legacy_routes_keep_http_400_and_are_audited(api: AsyncClient, pg_db: dict):
    i = pg_db["ids"]
    r = await api.post(f"/api/v1/financial-data/{i['c_dc_eur']}/verify", json={"verified_by": "x"})
    assert r.status_code == 400  # unchanged contract of the pre-existing route
    r = await api.post(f"/api/v1/financial-data/{i['c_dc_eur']}/reject", json={"reason": "Wrong currency column"})
    assert r.status_code == 200
    (e,) = await events(api, i["c_dc_eur"])
    assert (e["action"], e["previous_status"], e["actor"]) == ("reject", "extracted", None)


@pytest.mark.asyncio
async def test_two_reviewers_at_the_same_time(api: AsyncClient, pg_db: dict):
    """Both load the same state and decide simultaneously: the row lock serializes them and
    the second one sees the state has changed -> 409, never a silent overwrite."""
    i = pg_db["ids"]
    d = (await api.get(f"{DQ}/{i['c_dc_xof']}")).json()["observation"]
    seen = {"expected_status": d["status"], "expected_updated_at": d["updated_at"]}
    r1, r2 = await asyncio.gather(
        decide(api, i["c_dc_xof"], "review", actor="analyst-1", reason="Read on p.12", **seen),
        decide(api, i["c_dc_xof"], "reject", actor="analyst-2", reason="Wrong column", **seen),
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    assert len(await events(api, i["c_dc_xof"])) == 1


@pytest.mark.asyncio
async def test_decisions_persist_in_a_fresh_session(pg_db: dict):
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.financial_data import FinancialData
    from app.models.review_event import FinancialDataReviewEvent

    engine = create_async_engine(pg_db["url"])
    async with async_sessionmaker(engine)() as db:
        statuses = dict((await db.execute(select(FinancialData.id, FinancialData.status))).all())
        n_events = (await db.execute(select(func.count()).select_from(FinancialDataReviewEvent))).scalar_one()
    await engine.dispose()
    i = pg_db["ids"]
    assert statuses[i["a_cp_100"]] == "verified" and statuses[i["a_cp_130"]] == "rejected"
    assert statuses[i["b_ta_rev"]] == "verified" and statuses[i["a_ta_nr"]] == "rejected"
    # verify B, review+verify A100, reject A130, reject A1000, reject C-EUR, one concurrent decision
    assert n_events == 7
