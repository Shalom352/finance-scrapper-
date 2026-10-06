"""
Target-database guard for deal ingestion runners.

Checked on the real connection BEFORE any HTTP request or write:
  - the historical base (umoa_banking) is always refused;
  - --expect-db, when given, must equal current_database();
  - without DATABASE_URL in the process environment (fallback on .env / POSTGRES_* values),
    only the working base is accepted;
  - the schema must be at least at the required Alembic revision;
  - when a runner name is expected, the connection must announce it (application_name).
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FORBIDDEN_DATABASES = frozenset({"umoa_banking"})
WORKING_DATABASE = "umoa_discovery_e2e"
MIN_ALEMBIC_REVISION = 15  # 0015_deal_validation_flags
URL_FROM_ENVIRONMENT = "environment:DATABASE_URL"
RUNNER_APPLICATION_NAME = "umoa_titres_run"


class TargetDatabaseError(RuntimeError):
    """The connected database is not an acceptable target: the run must stop."""


@dataclass(frozen=True)
class VerifiedDatabase:
    name: str
    alembic_version: str

    def message(self) -> str:
        return f"Base vérifiée: {self.name} (alembic {self.alembic_version})"


def revision_number(version: str | None) -> int | None:
    """Leading number of an Alembic revision id ("0015_deal_validation_flags" -> 15)."""
    if not version:
        return None
    head = version.split("_", 1)[0]
    return int(head) if head.isdigit() else None


def check_target(
    actual: str,
    alembic_version: str | None,
    *,
    expect_db: str | None,
    url_source: str,
    application_name: str | None = None,
    expect_application_name: str | None = None,
) -> VerifiedDatabase:
    if actual in FORBIDDEN_DATABASES:
        raise TargetDatabaseError(f"ABANDON: connecté à {actual!r}, base historique interdite pour ce runner.")
    if expect_db is not None and actual != expect_db:
        raise TargetDatabaseError(f"ABANDON: connecté à {actual!r}, attendu {expect_db!r} (--expect-db).")
    if url_source != URL_FROM_ENVIRONMENT and actual != WORKING_DATABASE:
        raise TargetDatabaseError(
            f"ABANDON: DATABASE_URL absent de l'environnement (repli sur {url_source}) "
            f"et la base connectée {actual!r} n'est pas {WORKING_DATABASE!r}."
        )
    number = revision_number(alembic_version)
    if number is None or number < MIN_ALEMBIC_REVISION:
        raise TargetDatabaseError(
            f"ABANDON: {actual!r} est en alembic {alembic_version!r}, "
            f"révision {MIN_ALEMBIC_REVISION:04d} minimum requise."
        )
    if expect_application_name is not None and application_name != expect_application_name:
        raise TargetDatabaseError(
            f"ABANDON: la connexion s'annonce {application_name!r} au lieu de {expect_application_name!r} "
            "(application_name)."
        )
    return VerifiedDatabase(name=actual, alembic_version=alembic_version)


async def verify_target_database(
    db: AsyncSession,
    *,
    expect_db: str | None,
    url_source: str,
    expect_application_name: str | None = None,
) -> VerifiedDatabase:
    """Read current_database(), application_name and alembic_version (read only), then check."""
    actual = (await db.execute(text("SELECT current_database()"))).scalar_one()
    application_name = (await db.execute(text("SELECT current_setting('application_name')"))).scalar_one()
    exists = (await db.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))).scalar_one()
    version = None
    if exists:
        version = (await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()
    await db.rollback()
    return check_target(
        actual,
        version,
        expect_db=expect_db,
        url_source=url_source,
        application_name=application_name,
        expect_application_name=expect_application_name,
    )
