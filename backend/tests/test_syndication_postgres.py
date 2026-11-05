"""
Syndication tracker (migration 0022) against a REAL PostgreSQL database (scratch databases only).

Synthetic workbook only (tests/fixtures_syndication.py). Covers: migration round trip and downgrade
refusal; preview writes nothing but the preview; apply (mandates, events, contacts, directory links by
exact name / alias only); the same file twice is refused; a modified file adds events and keeps the
history; the 3-way merge (platform edit vs Excel change = conflict, a decision is required); a manual
event newer than the last import vs the Excel = conflict; the internal guard (401 without the token);
the upload API; the "TOMASTEED relationship" criterion of the targeting view.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.mandate import InstitutionContact, Mandate, MandateCounterparty, SyndicationImport
from tests.fixtures_syndication import DEAL_CI, DEAL_SN, DEAL_TG, build_workbook, suivi_rows
from tests.test_migration_postgres_phase2 import _dsn, _fetchval
from tests.test_phase15_discovery_postgres import _alembic, _drop, _fresh_db, _session

BACKEND = Path(__file__).resolve().parents[1]
SY = "/api/v1/syndication"


async def _exec(dsn: str, sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def test_migration_0022_round_trip_and_downgrade_refusal() -> None:
    params, name = _fresh_db("syndication_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0022_syndication")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns WHERE "
                                          "table_name='mandate_counterparties' AND column_name IN "
                                          "('lender_type','appetite','rate_text','nda_sent_on','origin')")) == 5
        _alembic("0021_press_source", "downgrade")
        assert asyncio.run(_fetchval(dsn, "SELECT to_regclass('public.institution_contacts') IS NULL"))
        _alembic("0022_syndication")
        asyncio.run(_exec(dsn, "INSERT INTO institution_contacts (id, contact_key, institution_name, recorded_by, "
                               "origin, dataroom_access, created_at, updated_at) VALUES ('c', 'k', 'X', 'a', 'manual', "
                               "false, now(), now())"))
        with pytest.raises(RuntimeError, match="downgrade of 0022 refused"):
            _alembic("0021_press_source", "downgrade")
        asyncio.run(_exec(dsn, "DELETE FROM institution_contacts"))
        _alembic("head")
    finally:
        _drop(params, name)


@pytest.fixture(scope="module")
def pg():
    params, name = _fresh_db("syndication_pytest")
    _alembic("head")
    url = _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    asyncio.run(_seed(url))
    yield {"url": url}
    _drop(params, name)


async def _seed(url: str) -> None:
    from app.directory.seed import seed

    engine, maker = await _session(url)
    entries = json.loads((BACKEND / "reference" / "financing_institutions.json").read_text(encoding="utf-8"))
    async with maker() as db:
        await seed(db, entries["institutions"])  # BOAD, BID (alias of "ISDB"), ...
    await engine.dispose()


@pytest_asyncio.fixture
async def maker(pg):
    engine, mk = await _session(pg["url"])
    yield mk
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-Authenticated-User": "analyst-1"}) as client:
        yield client


MAPPING = {"Projet Beta (1)": DEAL_TG}
FILE_V1 = build_workbook()  # built once: openpyxl stamps the creation time, the SHA-256 must not move


async def preview(api, content: bytes, mapping: dict | None = MAPPING):
    return await api.post(f"{SY}/imports/preview", files={"file": ("suivi.xlsx", content)},
                          data={"sheet_mapping": json.dumps(mapping)} if mapping else {})


@pytest.mark.asyncio
async def test_1_preview_then_apply(api, maker):
    r = await preview(api, FILE_V1)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["status"] == "preview" and plan["counts"]["mandates"]["create"] == 5
    assert plan["counts"]["events"]["create"] == 6 and plan["conflicts"] == []
    assert "Banque X" in plan["unresolved_names"] and "ISDB" not in plan["unresolved_names"]  # alias -> BID
    async with maker() as db:
        assert (await db.execute(select(func.count()).select_from(Mandate))).scalar_one() == 0  # preview only
    r = await api.post(f"{SY}/imports/{plan['id']}/apply", json={})
    assert r.status_code == 200, r.text and r.json()["status"] == "applied"
    async with maker() as db:
        mandates = {m.title: m for m in (await db.execute(select(Mandate))).scalars()}
        assert len(mandates) == 5 and mandates[DEAL_SN].status == "closed_won"
        assert mandates[DEAL_SN].origin == "excel_import" and mandates[DEAL_SN].excel_snapshot["title"] == DEAL_SN
        events = (await db.execute(select(MandateCounterparty))).scalars().all()
        isdb = next(e for e in events if e.counterparty_name == "ISDB")
        assert isdb.entity_id is not None and isdb.stage == "declined"  # linked by alias, exact
        bank_x = next(e for e in events if e.counterparty_name == "Banque X")
        assert bank_x.institution_id is None and bank_x.entity_id is None  # unknown name: never guessed
        assert (str(bank_x.amount), bank_x.currency, bank_x.rate_text) == ("27800000000.000000", "XOF", "7 % HT")
        contacts = (await db.execute(select(InstitutionContact))).scalars().all()
        assert {c.email for c in contacts} >= {"awa@boad.example", "fred@boad.example", "hugo@tomasteed.example"}
        assert next(c for c in contacts if c.email == "fred@boad.example").dataroom_access is True


@pytest.mark.asyncio
async def test_2_same_file_twice_is_refused(api):
    r = await preview(api, FILE_V1)
    assert r.status_code == 409 and "already imported" in r.text


@pytest.mark.asyncio
async def test_3_modified_file_adds_events_and_keeps_history(api, maker):
    content = build_workbook(rows=suivi_rows(bank_x_amount="30 Md FCFA", bank_x_rate="6,5 % HT"))
    plan = (await preview(api, content)).json()
    assert plan["counts"]["events"] == {"create": 1, "unchanged": 5, "conflict": 0}
    assert (await api.post(f"{SY}/imports/{plan['id']}/apply", json={})).status_code == 200
    deals = (await api.get(f"{SY}/deals")).json()
    sn = next(d for d in deals if d["title"] == DEAL_SN)
    detail = (await api.get(f"{SY}/deals/{sn['id']}")).json()
    bank_x = next(s for s in detail["counterparty_states"] if s["counterparty_name"] == "Banque X")
    assert bank_x["rate_text"] == "6,5 % HT" and len(bank_x["history"]) == 2  # history kept
    assert {c["email"] for c in detail["contacts"]} >= {"awa@boad.example", "carl@bankx.example"}


@pytest.mark.asyncio
async def test_4_platform_edit_vs_excel_change_is_a_conflict(api, maker):
    deals = (await api.get(f"{SY}/deals")).json()
    ci = next(d for d in deals if d["title"] == DEAL_CI)
    r = await api.patch(f"{SY}/deals/{ci['id']}", json={"title": "Alpha — titre corrigé dans la plateforme"})
    assert r.status_code == 200 and r.json()["manually_edited_at"]
    # The Excel changes the status of the same deal (stage "Mandat exécuté") while the platform set it to
    # "on_hold": both sides changed the field since the last import -> conflict.
    rows = suivi_rows()
    rows[2][2] = "0 - Mandat exécuté"
    rows[2][6] = "350 M€"  # the ISDB line changes too: a new event (no manual event, no conflict)
    content = build_workbook(rows=rows, date_maj=datetime(2026, 9, 21))
    await api.patch(f"{SY}/deals/{ci['id']}", json={"status": "on_hold"})
    plan = (await preview(api, content)).json()
    ids = [c["id"] for c in plan["conflicts"]]
    assert any(i.endswith(":status") for i in ids), plan["conflicts"]
    r = await api.post(f"{SY}/imports/{plan['id']}/apply", json={})
    assert r.status_code == 409 and "decision is required" in r.text
    decisions = {i: "platform" for i in ids}
    assert (await api.post(f"{SY}/imports/{plan['id']}/apply", json={"decisions": decisions})).status_code == 200
    async with maker() as db:
        m = await db.get(Mandate, ci["id"])
        assert m.status == "on_hold" and m.title == "Alpha — titre corrigé dans la plateforme"
        assert m.excel_snapshot["status"] == "closed_won"  # the snapshot follows the Excel


@pytest.mark.asyncio
async def test_5_manual_event_newer_than_the_import_is_a_conflict(api):
    deals = (await api.get(f"{SY}/deals")).json()
    sn = next(d for d in deals if d["title"] == DEAL_SN)
    r = await api.post(f"{SY}/deals/{sn['id']}/counterparties",
                       json={"counterparty_name": "BOAD", "stage": "committed", "amount_text": "250 M€ (oral)"})
    assert r.status_code == 200 and r.json()["origin"] == "manual"
    rows = suivi_rows()
    rows[0][6] = "Jusqu'à 280 M€"
    plan = (await preview(api, build_workbook(rows=rows, date_maj=datetime(2026, 9, 30)))).json()
    event_conflicts = [c for c in plan["conflicts"] if c["kind"] == "event"]
    assert len(event_conflicts) == 1 and event_conflicts[0]["platform"]["stage"] == "committed"
    decisions = {c["id"]: ("excel" if c["kind"] == "event" else "platform") for c in plan["conflicts"]}
    assert (await api.post(f"{SY}/imports/{plan['id']}/apply", json={"decisions": decisions})).status_code == 200
    detail = (await api.get(f"{SY}/deals/{sn['id']}")).json()
    boad = next(s for s in detail["counterparty_states"] if s["counterparty_name"] == "BOAD")
    assert {h["origin"] for h in boad["history"]} == {"excel_import", "manual"} and len(boad["history"]) == 3


@pytest.mark.asyncio
async def test_6_views_contacts_and_targeting(api):
    lenders = (await api.get(f"{SY}/lenders")).json()
    assert any(x["name"] == "BOAD" and "dfi" in x["lender_types"] for x in lenders)
    terms = (await api.get(f"{SY}/terms")).json()
    assert any(t["institution"] == "BGFIBank Gabon" and t["rate_text"] == "8,75 % p.a." for t in terms)
    r = await api.post(f"{SY}/contacts", json={"institution_name": "Banque X", "full_name": "Iris FICTIVE",
                                               "email": "iris@bankx.example"})
    assert r.status_code == 200 and r.json()["origin"] == "manual"
    assert (await api.post(f"{SY}/contacts", json={"institution_name": "Banque X",
                                                   "email": "iris@bankx.example"})).status_code == 409
    assert (await api.delete(f"{SY}/contacts/{r.json()['id']}")).status_code == 204
    history = (await api.get(f"{SY}/imports")).json()
    assert [h["status"] for h in history].count("applied") == 4
    # The internal mandates feed the "TOMASTEED relationship" criterion of the targeting view.
    t = (await api.get("/api/v1/targeting", params={"kind": "institutions", "limit": 200})).json()
    boad = next(i for i in t["items"] if i["name"] == "Banque Ouest Africaine de Développement")
    assert boad["criteria"]["relationship"]["status"] == "met"


@pytest.mark.asyncio
async def test_7_internal_routes_require_the_token(api, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "internal_api_token", "s3cret")
    assert (await api.get(f"{SY}/deals")).status_code == 401
    assert (await api.get("/api/v1/mandates")).status_code == 401
    assert (await api.get(f"{SY}/deals", headers={"X-Internal-Token": "wrong"})).status_code == 401
    assert (await api.get(f"{SY}/deals", headers={"X-Internal-Token": "s3cret"})).status_code == 200
    assert (await api.get("/api/v1/deals")).status_code == 200  # public deals stay public
    monkeypatch.setattr(get_settings(), "internal_api_token", None)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    assert (await api.get(f"{SY}/deals")).status_code == 503


@pytest.mark.asyncio
async def test_8_upload_guards(api):
    r = await api.post(f"{SY}/imports/preview", files={"file": ("notes.txt", b"x")})
    assert r.status_code == 422
    r = await api.post(f"{SY}/imports/preview", files={"file": ("bad.xlsx", b"not a workbook")})
    assert r.status_code == 422 and "not a readable" in r.text
    async with AsyncClient(transport=api._transport, base_url="http://test") as anonymous:
        r = await anonymous.post(f"{SY}/imports/preview", files={"file": ("s.xlsx", build_workbook())})
        assert r.status_code == 422 and "actor is required" in r.text
    assert SyndicationImport.__tablename__ == "syndication_imports"
