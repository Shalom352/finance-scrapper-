"""
UMOA Financial Intelligence — Entity & Source Discovery Engine models (Phase 15).

Tables (migration 0011):
  - reference_universes         : dated official reference snapshot (expected counts)
  - reference_universe_members  : one row per line of the official list
  - entity_identifiers          : regulatory identifiers (strong resolution keys)
  - entity_names                : append-only name history (official / acronym / former ...)
  - entity_sources              : per-entity source coverage facts with lifecycle status
  - document_entities           : many-to-many document <-> entity (sector-wide PDFs)
  - discovery_runs / rounds     : search loop journal with stop condition
  - discovery_gaps              : source gap queue

Rules:
  - expected_count is NULL when the official document does not state it (UNKNOWN).
  - Nothing here is ever physically deleted by the application.
  - An ambiguous resolution never links an entity (DATA MISSING > DATA WRONG).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.discovery import (
    DISCOVERY_RUN_STATUSES,
    DISCOVERY_TRIGGER_TYPES,
    DOCUMENT_LINK_TYPES,
    GAP_PRIORITIES,
    GAP_STATUSES,
    GAP_TYPES,
    IDENTIFIER_TYPES,
    LINK_ROLES,
    MEMBER_CATEGORIES,
    MEMBER_FORMS,
    NAME_TYPES,
    RESOLUTION_STATUSES,
    REVIEW_DECISIONS,
    SOURCE_LIFECYCLE_STATUSES,
    STOP_CONDITIONS,
    UNIVERSE_STATUSES,
    sql_in,
)
from app.db.base import Base


class ReferenceUniverse(Base):
    """Dated official reference snapshot for one jurisdiction (country, or UMOA when NULL)."""

    __tablename__ = "reference_universes"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(UNIVERSE_STATUSES)})", name="ck_reference_universes_status"),
        CheckConstraint("expected_count IS NULL OR expected_count >= 0", name="ck_reference_universes_expected"),
        CheckConstraint(
            "coverage_ratio IS NULL OR (coverage_ratio >= 0 AND coverage_ratio <= 1)",
            name="ck_reference_universes_ratio",
        ),
        Index("ix_reference_universes_code_current", "universe_code", "is_current"),
        Index("ix_reference_universes_document", "reference_document_id"),
        Index(
            "uq_reference_universes_snapshot",
            "universe_code",
            "reference_document_id",
            text("COALESCE(country_id, 'UMOA')"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    universe_code: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_class: Mapped[str] = mapped_column(String(50), nullable=False, default="financial_institution", server_default="financial_institution")
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, default="commercial_bank", server_default="commercial_bank")
    # NULL = supranational (UMOA total)
    country_id: Mapped[str | None] = mapped_column(ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True)
    reference_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=True
    )
    reference_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # NULL = not stated by the official document → coverage UNKNOWN (never guessed)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_count_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    coverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Self-check issues, history events (new licences, radiations, renames) found in the document
    self_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    history_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)


class ReferenceUniverseMember(Base):
    """One line of an official list, with its resolution to the Entity Hub."""

    __tablename__ = "reference_universe_members"
    __table_args__ = (
        CheckConstraint(f"category IN ({sql_in(MEMBER_CATEGORIES)})", name="ck_universe_members_category"),
        CheckConstraint(f"member_form IN ({sql_in(MEMBER_FORMS)})", name="ck_universe_members_form"),
        CheckConstraint(
            f"resolution_status IN ({sql_in(RESOLUTION_STATUSES)})", name="ck_universe_members_resolution"
        ),
        CheckConstraint(
            f"review_decision IS NULL OR review_decision IN ({sql_in(REVIEW_DECISIONS)})",
            name="ck_universe_members_review_decision",
        ),
        CheckConstraint(
            "resolution_status NOT IN ('matched', 'created') OR entity_id IS NOT NULL",
            name="ck_universe_members_resolved_has_entity",
        ),
        CheckConstraint("resolution_status != 'ambiguous' OR entity_id IS NULL", name="ck_universe_members_ambiguous"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_universe_members_page"),
        Index("ix_universe_members_universe", "universe_id"),
        Index("ix_universe_members_entity", "entity_id"),
        Index("ix_universe_members_registration", "registration_number"),
        Index(
            "uq_universe_members_line",
            "universe_id",
            "category",
            text("COALESCE(registration_number, normalized_name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    universe_id: Mapped[str] = mapped_column(ForeignKey("reference_universes.id", ondelete="RESTRICT"), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    member_form: Mapped[str] = mapped_column(String(20), nullable=False, default="unspecified", server_default="unspecified")
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    official_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    acronym: Mapped[str | None] = mapped_column(String(100), nullable=True)
    former_names: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    parent_name_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unresolved", server_default="unresolved")
    resolution_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    candidate_entity_ids: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EntityIdentifier(Base):
    """Regulatory identifier of an entity. Never invented: only read from an official document."""

    __tablename__ = "entity_identifiers"
    __table_args__ = (
        CheckConstraint(f"id_type IN ({sql_in(IDENTIFIER_TYPES)})", name="ck_entity_identifiers_type"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_entity_identifiers_page"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_entity_identifiers_dates"
        ),
        Index("ix_entity_identifiers_entity", "entity_id"),
        Index(
            "uq_entity_identifiers_value",
            "id_type",
            "value",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    id_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    authority_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    authority_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EntityName(Base):
    """Append-only name history. A rename closes the previous name (valid_to), never deletes it."""

    __tablename__ = "entity_names"
    __table_args__ = (
        CheckConstraint(f"name_type IN ({sql_in(NAME_TYPES)})", name="ck_entity_names_type"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_entity_names_page"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_entity_names_dates"),
        Index("ix_entity_names_entity", "entity_id"),
        Index("ix_entity_names_normalized", "normalized_name"),
        Index(
            "uq_entity_names_entry",
            "entity_id",
            "name_type",
            "normalized_name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_type: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EntitySource(Base):
    """A source found for one entity, with its explicit lifecycle (HTTP 200 ≠ operational)."""

    __tablename__ = "entity_sources"
    __table_args__ = (
        CheckConstraint(f"link_role IN ({sql_in(LINK_ROLES)})", name="ck_entity_sources_role"),
        CheckConstraint(
            f"lifecycle_status IN ({sql_in(SOURCE_LIFECYCLE_STATUSES)})", name="ck_entity_sources_lifecycle"
        ),
        CheckConstraint("priority >= 1 AND priority <= 7", name="ck_entity_sources_priority"),
        Index("ix_entity_sources_entity", "entity_id"),
        Index("ix_entity_sources_role_status", "link_role", "lifecycle_status"),
        Index(
            "uq_entity_sources_link",
            "entity_id",
            "link_role",
            text("COALESCE(source_id, '')"),
            text("COALESCE(url, '')"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    link_role: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="CANDIDATE", server_default="CANDIDATE")
    discovery_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    discovery_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    evidence_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    evidence_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentEntity(Base):
    """Links a document to an entity it covers (one sector-wide PDF → many banks)."""

    __tablename__ = "document_entities"
    __table_args__ = (
        CheckConstraint(f"link_type IN ({sql_in(DOCUMENT_LINK_TYPES)})", name="ck_document_entities_type"),
        CheckConstraint("page_from IS NULL OR page_from > 0", name="ck_document_entities_page_from"),
        CheckConstraint(
            "page_to IS NULL OR page_from IS NULL OR page_to >= page_from", name="ck_document_entities_pages"
        ),
        Index("ix_document_entities_entity", "entity_id"),
        Index("ix_document_entities_document", "document_id"),
        Index(
            "uq_document_entities_link",
            "document_id",
            "entity_id",
            "link_type",
            text("COALESCE(page_from, 0)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(30), nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_in_document: Mapped[str | None] = mapped_column(String(500), nullable=True)
    method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryRun(Base):
    """One execution of the discovery loop."""

    __tablename__ = "discovery_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(DISCOVERY_RUN_STATUSES)})", name="ck_discovery_runs_status"),
        CheckConstraint(f"trigger_type IN ({sql_in(DISCOVERY_TRIGGER_TYPES)})", name="ck_discovery_runs_trigger"),
        CheckConstraint(
            f"stop_condition IS NULL OR stop_condition IN ({sql_in(STOP_CONDITIONS)})",
            name="ck_discovery_runs_stop_condition",
        ),
        Index("ix_discovery_runs_started", "started_at"),
    )

    universe_code: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="cli", server_default="cli")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", server_default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)


class DiscoveryRound(Base):
    """One strategy executed inside a run, with coverage before / after."""

    __tablename__ = "discovery_rounds"
    __table_args__ = (
        CheckConstraint("round_number >= 1", name="ck_discovery_rounds_number"),
        Index("ix_discovery_rounds_run", "run_id", "round_number"),
    )

    run_id: Mapped[str] = mapped_column(ForeignKey("discovery_runs.id", ondelete="RESTRICT"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_code: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    targets_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sources_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    new_entities: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    new_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    new_document_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    new_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    coverage_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)


class DiscoveryGap(Base):
    """Source gap queue entry: what is missing for an entity, why, and when it was last searched."""

    __tablename__ = "discovery_gaps"
    __table_args__ = (
        CheckConstraint(f"gap_type IN ({sql_in(GAP_TYPES)})", name="ck_discovery_gaps_type"),
        CheckConstraint(f"priority IN ({sql_in(GAP_PRIORITIES)})", name="ck_discovery_gaps_priority"),
        CheckConstraint(f"status IN ({sql_in(GAP_STATUSES)})", name="ck_discovery_gaps_status"),
        CheckConstraint("attempts >= 0", name="ck_discovery_gaps_attempts"),
        Index("ix_discovery_gaps_status", "status", "gap_type"),
        Index("ix_discovery_gaps_entity", "entity_id"),
        Index(
            "uq_discovery_gaps_open",
            text("COALESCE(entity_id, '')"),
            text("COALESCE(member_id, '')"),
            "gap_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status != 'RESOLVED'"),
        ),
    )

    universe_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_universes.id", ondelete="SET NULL"), nullable=True
    )
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True)
    member_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_universe_members.id", ondelete="SET NULL"), nullable=True
    )
    country_id: Mapped[str | None] = mapped_column(ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True)
    gap_type: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="MEDIUM", server_default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    strategies_tried: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 17: evidence behind the gap (label, document, page...) and last strategy that tried it
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_strategy: Mapped[str | None] = mapped_column(String(80), nullable=True)
