"""UMOA Banking Intelligence — Ingestion Schemas"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IngestionRunRead(BaseModel):
    """Public read schema for an ingestion run."""

    id: str
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    target_years: str | None = None
    sources_checked: int = 0
    documents_found: int = 0
    documents_new: int = 0
    documents_downloaded: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    data_points_extracted: int = 0
    data_points_needing_review: int = 0
    duration_seconds: float | None = None
    errors: list[dict[str, Any]] | None = None
    summary_text: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionTriggerResponse(BaseModel):
    """Response returned when triggering a manual or test ingestion run."""

    message: str
    run_id: str | None = None
    status: str
