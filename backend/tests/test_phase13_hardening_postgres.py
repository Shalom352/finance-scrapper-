"""
Phase 13 — production hardening against a REAL PostgreSQL database.

1. Scope guard: the pipeline (real PDF, real parser, real database) never stores an
   undetected scope as usable data: new rows are needs_review + "scope not detected",
   excluded from rankings / aggregations until a human decides in the Review Center.
   Historical rows are never modified; a rejected row is never overwritten.
2. Legacy write routes (/financial-data/{id}/review|verify|reject, /bulk-review) carry
   the Review Center guarantees: actor, 404, 409 on stale state, lock, audit, ≤100 ids.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from decimal import Decimal

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

FD = "/api/v1/financial-data"
DQ = "/api/v1/data-quality"


def _pdf(extra_line: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 40), "Montants en millions de FCFA")
    page.insert_text((50, 70), "Postes")
    page.insert_text((250, 70), "2024")
    page.insert_text((50, 100), "Total Actif")
    page.insert_text((250, 100), "1500")
    page.insert_text((50, 200), extra_line)  # distinct content -> distinct file hash
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="module")
def storage_dir() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture(scope="module")
def pg_db(storage_dir: str) -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase13_hardening_pytest"
    asyncio.run(
        _exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"')
    )
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    ids = asyncio.run(_seed(_async_dsn(params, test_db), storage_dir))
    yield {"url": _async_dsn(params, test_db), "ids": ids}

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str, storage_dir: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source
    from scraping.storage.manager import StorageManager

    storage = StorageManager(storage_dir)
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        source = (await db.execute(select(Source))).scalars().first()
        a = Institution(name_official="Banque A", institution_type="bank", country_id=ci.id, status="active")
        b = Institution(name_official="Banque B", institution_type="bank", country_id=ci.id, status="active")
        db.add_all([a, b])
        await db.flush()

        docs = {}
        for key, inst, line in (("pdf_new", a, "Rapport 1"), ("pdf_rejected", b, "Rapport 2")):
            stored = storage.store_content(_pdf(line), f"{key}.pdf")
            docs[key] = Document(
                title=f"Rapport annuel 2024 {key}", document_type="annual_report", source_id=source.id,
                institution_id=inst.id, download_status="downloaded", extraction_status="extracted",
                file_hash=stored.file_hash, storage_path=stored.relative_path, period_year=2024,
            )
        docs["plain"] = Document(title="Rapport B", document_type="annual_report", source_id=source.id,
                                 institution_id=b.id, download_status="downloaded", extraction_status="skipped")
        db.add_all(docs.values())
        await db.flush()

        rows: dict[str, FinancialData] = {}

        def fd(name, inst, doc, metric, value, *, status="extracted", year=2024, notes=None):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "seed"} if status == "verified" else {}
            rows[name] = FinancialData(
                institution_id=inst.id, source_id=source.id, document_id=docs[doc].id, metric_code=metric,
                scope="individual", period_type="annual", period_year=year, value_original=str(value),
                currency_original="XOF", value_normalized=None if value is None else Decimal(str(value)),
                unit_normalized="unit", currency_normalized="XOF", extraction_method="pdf_table",
                status=status, page_number=1, notes=notes, **extra,
            )
            db.add(rows[name])

        # Historical rows: must never be modified by the Phase 13 guard.
        fd("hist_a", a, "pdf_new", "capitaux_propres", 90, year=2023)
        # A human rejection that a re-extraction must never overwrite.
        fd("rejected_b", b, "pdf_rejected", "total_actifs", 999, status="rejected", notes="Rejection: wrong table")
        # Verified value for B so the ranking has an eligible row.
        fd("b_ta_2024", b, "plain", "total_actifs", 800, status="verified")
        # Legacy-route rows.
        for n in range(1, 8):
            fd(f"L{n}", b, "plain", "depots_clients", 100 + n, year=2010 + n)
        fd("L_rej", b, "plain", "resultat_net", 5, status="rejected")
        fd("L_novalue", b, "plain", "creances_clients", None)
        await db.commit()
        ids = {"A": a.id, "B": b.id} | {k: d.id for k, d in docs.items()} | {k: r.id for k, r in rows.items()}
        ids["hist_a_updated_at"] = rows["hist_a"].updated_at.isoformat()
    await engine.dispose()
    return ids


@pytest.fixture
async def maker(pg_db: dict):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(pg_db["url"])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
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


async def row(maker, data_id):
    from sqlalchemy import select

    from app.models.financial_data import FinancialData

    async with maker() as db:
        return (await db.execute(select(FinancialData).where(FinancialData.id == data_id))).scalar_one()


async def events_of(maker, data_id):
    from sqlalchemy import select

    from app.models.review_event import FinancialDataReviewEvent

    async with maker() as db:
        return (
            await db.execute(
                select(FinancialDataReviewEvent)
                .where(FinancialDataReviewEvent.financial_data_id == data_id)
                .order_by(FinancialDataReviewEvent.created_at)
            )
        ).scalars().all()


# ================================================================== 1. scope guard


@pytest.mark.asyncio
async def test_pipeline_holds_undetected_scope_for_review(maker, pg_db, storage_dir):
    from sqlalchemy import select

    from app.models.financial_data import FinancialData
    from scraping.pipeline import ScrapingPipeline
    from scraping.storage.manager import StorageManager

    i = pg_db["ids"]
    pipeline = ScrapingPipeline(storage_manager=StorageManager(storage_dir))
    for doc in ("pdf_new", "pdf_rejected"):
        async with maker() as db:
            await pipeline.extract_financial_data(db, document_id=i[doc])

    async with maker() as db:
        new = (await db.execute(select(FinancialData).where(
            FinancialData.document_id == i["pdf_new"], FinancialData.metric_code == "total_actifs"))).scalars().all()
    (obs,) = new
    pg_db["ids"]["guarded"] = obs.id
    assert obs.status == "needs_review"                   # 1. never extracted/usable directly
    assert "scope not detected" in obs.notes              # 2. explicit note for the reviewer
    assert obs.scope == "individual"                      # technical value kept, no new scope
    assert obs.verified_at is None and obs.value_normalized is not None

    hist = await row(maker, i["hist_a"])                  # 5. historical rows untouched
    assert (hist.status, hist.notes) == ("extracted", None)
    assert hist.updated_at.isoformat() == i["hist_a_updated_at"]

    rejected = await row(maker, i["rejected_b"])          # a human rejection is never overwritten
    assert (rejected.status, rejected.value_normalized) == ("rejected", Decimal("999"))


@pytest.mark.asyncio
async def test_guarded_row_is_excluded_until_a_human_decides(api, pg_db):
    i = pg_db["ids"]
    params = {"metric_code": "total_actifs", "period_year": 2024, "country_code": "CI"}
    ranked = {e["institution_id"] for e in (await api.get("/api/v1/rankings", params=params)).json()["items"]}
    assert i["A"] not in ranked and i["B"] in ranked      # 3. excluded from rankings
    agg = (await api.get("/api/v1/analytics/aggregations",
                         params={"year": 2024, "metric_code": "total_actifs", "country_code": "CI"})).json()
    assert i["A"] not in agg[0]["contributing_institutions"]
    assert "needs_review" in (agg[0]["notes"] or "")

    queue = {o["id"] for o in (await api.get(DQ, params={"page_size": 100})).json()["items"]}
    assert i["guarded"] in queue                           # 4. visible in the Review Center
    d = (await api.get(f"{DQ}/{i['guarded']}")).json()
    assert "scope not detected" in d["observation"]["notes"]
    body = {"actor": "analyst-1", "reason": "Scope checked: individual statements (p.1)"}
    assert (await api.post(f"{DQ}/{i['guarded']}/review", json=body)).status_code == 200
    assert (await api.post(f"{DQ}/{i['guarded']}/verify", json=body)).status_code == 200
    ranked = {e["institution_id"] for e in (await api.get("/api/v1/rankings", params=params)).json()["items"]}
    assert i["A"] in ranked                                 # usable only after the human decision


# ================================================================== 2. legacy routes


async def legacy(api, data_id, action, **body):
    return await api.post(f"{FD}/{data_id}/{action}", json=body)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"reviewer_notes": "no actor"},
    {"actor": "   ", "reviewer_notes": "blank"},
    {"actor": "x" * 256, "reviewer_notes": "too long"},
])
async def test_legacy_actor_is_mandatory_and_bounded(api, maker, pg_db, body):
    i = pg_db["ids"]
    r = await legacy(api, i["L1"], "review", **body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (await row(maker, i["L1"])).status == "extracted" and await events_of(maker, i["L1"]) == []


@pytest.mark.asyncio
async def test_legacy_stale_state_is_refused(api, maker, pg_db):
    i = pg_db["ids"]
    r = await legacy(api, i["L1"], "review", actor="a", expected_status="needs_review")
    assert r.status_code == 409
    r = await legacy(api, i["L1"], "review", actor="a", expected_updated_at="2000-01-01T00:00:00+00:00")
    assert r.status_code == 409
    assert (await row(maker, i["L1"])).status == "extracted" and await events_of(maker, i["L1"]) == []
    fresh = (await api.get(f"{FD}/{i['L1']}")).json()
    r = await legacy(api, i["L1"], "review", actor="analyst-1", reviewer_notes="ok",
                     expected_status=fresh["status"], expected_updated_at=fresh["updated_at"])
    assert r.status_code == 200 and r.json()["status"] == "reviewed"


@pytest.mark.asyncio
async def test_legacy_missing_observation_is_404(api):
    for action, body in (("review", {"actor": "a"}), ("verify", {"verified_by": "a"}),
                         ("reject", {"actor": "a", "reason": "r"})):
        r = await legacy(api, "missing-id", action, **body)
        assert r.status_code == 404 and r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    r = await api.post(f"{FD}/bulk-review", json={"data_ids": ["missing-id"], "actor": "a"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_legacy_value_override_is_fully_audited(api, maker, pg_db):
    i = pg_db["ids"]
    r = await legacy(api, i["L2"], "review", actor="analyst-2", reviewer_notes="Read 120 on p.4",
                     value_normalized_override="120")
    assert r.status_code == 200
    (e,) = await events_of(maker, i["L2"])
    assert (e.action, e.previous_status, e.new_status, e.actor, e.reason) == (
        "review", "extracted", "reviewed", "analyst-2", "Read 120 on p.4")
    assert (e.value_before, e.value_after) == (Decimal("102"), Decimal("120")) and e.created_at is not None


@pytest.mark.asyncio
async def test_legacy_verify_reject_keep_their_contract(api, maker, pg_db):
    i = pg_db["ids"]
    assert (await legacy(api, i["L3"], "verify", verified_by="analyst-3")).status_code == 400  # not reviewed
    assert (await legacy(api, i["L_rej"], "review", actor="a")).status_code == 400  # rejected stays rejected
    assert (await legacy(api, i["L_novalue"], "review", actor="a")).status_code == 400  # no value
    assert (await legacy(api, i["L3"], "review", actor="analyst-3")).status_code == 200
    r = await legacy(api, i["L3"], "verify", verified_by="analyst-3", verification_notes="Audited")
    assert r.status_code == 200 and r.json()["status"] == "verified"
    r = await legacy(api, i["L4"], "reject", actor="analyst-4", reason="Wrong column")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert [(e.action, e.actor) for e in await events_of(maker, i["L3"])] == [
        ("review", "analyst-3"), ("verify", "analyst-3")]
    assert [(e.action, e.actor) for e in await events_of(maker, i["L4"])] == [("reject", "analyst-4")]


@pytest.mark.asyncio
async def test_bulk_review_is_bounded_locked_and_all_or_nothing(api, maker, pg_db):
    i = pg_db["ids"]
    r = await api.post(f"{FD}/bulk-review", json={"data_ids": [f"id-{n}" for n in range(101)], "actor": "a"})
    assert r.status_code == 422
    assert (await api.post(f"{FD}/bulk-review", json={"data_ids": [i["L5"]]})).status_code == 422  # no actor
    # One non-reviewable row -> nothing is written at all.
    r = await api.post(f"{FD}/bulk-review", json={"data_ids": [i["L5"], i["L_rej"]], "actor": "analyst-5"})
    assert r.status_code == 400
    assert (await row(maker, i["L5"])).status == "extracted" and await events_of(maker, i["L5"]) == []
    # Stale expected state for one id -> 409, nothing written.
    r = await api.post(f"{FD}/bulk-review", json={
        "data_ids": [i["L5"], i["L6"]], "actor": "analyst-5",
        "expected": [{"data_id": i["L6"], "expected_status": "needs_review"}]})
    assert r.status_code == 409 and await events_of(maker, i["L6"]) == []
    r = await api.post(f"{FD}/bulk-review", json={"data_ids": [i["L6"], i["L5"]], "actor": "analyst-5",
                                                   "reviewer_notes": "batch"})
    assert r.status_code == 200 and r.json() == sorted([i["L5"], i["L6"]])
    for d in (i["L5"], i["L6"]):
        (e,) = await events_of(maker, d)
        assert (e.action, e.actor, e.new_status) == ("review", "analyst-5", "reviewed")


@pytest.mark.asyncio
async def test_two_legacy_reviewers_at_the_same_time(api, maker, pg_db):
    i = pg_db["ids"]
    seen = (await api.get(f"{FD}/{i['L7']}")).json()
    state = {"expected_status": seen["status"], "expected_updated_at": seen["updated_at"]}
    r1, r2 = await asyncio.gather(
        legacy(api, i["L7"], "review", actor="analyst-A", **state),
        legacy(api, i["L7"], "reject", actor="analyst-B", reason="Wrong column", **state),
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    assert len(await events_of(maker, i["L7"])) == 1  # never a silent overwrite


@pytest.mark.asyncio
async def test_legacy_routes_cannot_bypass_eligibility(api, pg_db):
    """A legacy decision produces the same statuses as the Review Center: nothing becomes
    eligible without review, and a rejected value never reaches the rankings."""
    i = pg_db["ids"]
    params = {"metric_code": "depots_clients", "period_year": 2014, "country_code": "CI"}
    items = (await api.get("/api/v1/rankings", params=params)).json()["items"]
    assert i["B"] not in {e["institution_id"] for e in items}  # L4 (2014) was rejected
