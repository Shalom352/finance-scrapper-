"""
UMOA Banking Intelligence — Ingestion Run Model

Tracks every automated or manual ingestion execution for transparency,
auditability, and monitoring.

Guarantees:
  - Immutable execution history.
  - Granular error logging per source.
  - Document & data point counters.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

INGESTION_RUN_STATUSES = (
    "running",
    "completed",
    "partial_failure",
    "failed",
    "skipped_concurrent",
)


class IngestionRun(Base):
    """
    Journal of ingestion pipeline runs.

    Records both scheduled and manual runs, tracking discovered documents,
    extractions, status transitions, and source-level errors.
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'partial_failure', 'failed', 'skipped_concurrent')",
            name="ck_ingestion_runs_status",
        ),
        CheckConstraint(
            "trigger_type IN ('scheduled', 'manual', 'cli')",
            name="ck_ingestion_runs_trigger_type",
        ),
    )

    # Execution lifecycle
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", server_default="scheduled")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True, server_default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Target years covered during this run
    target_years: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metrics & counters
    sources_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    documents_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    documents_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    documents_downloaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    documents_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    documents_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    data_points_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    data_points_needing_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Error details per source / phase (stored as structured JSON)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds(), 2)
        return None

    def __repr__(self) -> str:
        return f"<IngestionRun {self.id} [{self.status}] started={self.started_at}>"
