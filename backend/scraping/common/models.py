"""
UMOA Banking Intelligence — Scraping Common Data Models

Dataclasses used across the discovery, download, and storage pipeline.
Decoupled from ORM models to allow running pipeline components in isolation.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DiscoveredDocument:
    """Represents a document discovered by a connector before download."""

    title: str
    url: str
    source_short_name: str
    document_type: str = "annual_report"  # matches ck_documents_document_type
    source_page_url: str = ""
    period_year: int | None = None
    period_type: str | None = "annual"  # annual | semi_annual | quarterly
    language: str = "fr"
    published_at: date | None = None
    institution_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        self.title = self.title.strip()
        if not self.title and self.url:
            self.title = self.url.split("/")[-1]


@dataclass
class DownloadResult:
    """Result of a document download attempt."""

    url: str
    success: bool
    status_code: int | None = None
    content: bytes | None = None
    content_type: str | None = None
    file_size: int = 0
    duration_seconds: float = 0.0
    retry_count: int = 0
    error_message: str | None = None


@dataclass
class StorageResult:
    """Result of storing a downloaded document in content-addressed storage."""

    file_hash: str  # SHA-256 hex digest
    file_size: int
    relative_path: str  # {hash[:2]}/{hash}.{ext}
    absolute_path: str
    is_duplicate: bool = False
    stored_at: datetime = field(default_factory=datetime.utcnow)
