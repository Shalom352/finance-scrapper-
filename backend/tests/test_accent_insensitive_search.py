"""Search ignores case and accents: "societe generale" finds "SOCIÉTÉ GÉNÉRALE CÔTE D’IVOIRE"."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import literal, select

from app.db.text_search import _ACCENTED, _PLAIN, fold, fuzzy_contains
from tests.test_migration_postgres_phase2 import _async_dsn, _reachable, _server_params


def test_translate_tables_are_aligned() -> None:
    assert len(_ACCENTED) == len(_PLAIN)


def test_python_fold() -> None:
    assert fold("SOCIÉTÉ GÉNÉRALE CÔTE D’IVOIRE") == "societe generale cote d'ivoire"
    assert fold("Ecobank Bénin") == "ecobank benin"


@pytest.mark.parametrize(
    ("value", "query", "expected"),
    [
        ("SOCIÉTÉ GÉNÉRALE CÔTE D’IVOIRE", "societe generale", True),
        ("SOCIETE GENERALE COTE D'IVOIRE", "Société Générale", True),
        ("SOCIÉTÉ GÉNÉRALE CÔTE D’IVOIRE", "cote d'ivoire", True),
        ("Banque Atlantique", "bénin", False),
        ("Taux 100% garanti", "100%", True),
        ("Taux 1000 garanti", "10%", False),
    ],
)
def test_fuzzy_contains_on_postgres(value: str, query: str, expected: bool) -> None:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    from sqlalchemy.ext.asyncio import create_async_engine

    async def run() -> bool:
        engine = create_async_engine(_async_dsn(params, params["base_db"]))
        async with engine.connect() as conn:
            result = (await conn.execute(select(fuzzy_contains(literal(value), query)))).scalar_one()
        await engine.dispose()
        return bool(result)

    assert asyncio.run(run()) is expected
