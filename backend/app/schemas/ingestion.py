"""UMOA Banking Intelligence — Ingestion Schemas"""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class IngestionRunRead(BaseModel):
    """Public read schema for an ingestion run."""

    id: str
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    last_progress_at: datetime | None = None
    target_years: str | None = None
    sources_checked: int = 0
    sources_total: int = 0
    current_phase: str | None = None
    current_source: str | None = None
    current_items_done: int = 0
    current_items_total: int = 0
    documents_found: int = 0
    documents_new: int = 0
    documents_downloaded: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    data_points_extracted: int = 0
    data_points_needing_review: int = 0
    duration_seconds: float | None = None
    duration_is_lower_bound: bool = False
    duration_unknown: bool = False
    results_incomplete: bool = False
    errors: list[dict[str, Any]] | None = None
    # Deal collection phase: {source key: report summary} (migration 0020); None when not run.
    deal_summary: dict[str, Any] | None = None
    summary_text: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def expose_unreported_failure(self) -> "IngestionRunRead":
        if self.results_incomplete and not self.errors:
            phase = "timeout" if re.search(r"still 'running' after (\d+) h", self.summary_text or "") else "run"
            self.errors = [{
                "source": "all",
                "phase": phase,
                "error": self.summary_text or "The run ended before final counters were saved; results may be partial.",
            }]
        return self


class IngestionTriggerResponse(BaseModel):
    """Response returned when triggering a manual or test ingestion run."""

    message: str
    run_id: str | None = None
    status: str
