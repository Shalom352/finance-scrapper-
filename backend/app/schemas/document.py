"""UMOA Banking Intelligence — Document Schemas"""
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.institution import InstitutionList
from app.schemas.source import SourceList


class DocumentList(BaseModel):
    id: str
    title: str
    document_type: str
    institution_id: str | None = None
    source_id: str
    url: str | None = None
    period_year: int | None = None
    period_type: str | None = None
    language: str | None = None
    download_status: str
    extraction_status: str
    model_config = {"from_attributes": True}

class DocumentRead(BaseModel):
    id: str
    title: str
    document_type: str
    institution_id: str | None = None
    source_id: str
    url: str | None = None
    file_hash: str | None = None
    file_size: int | None = None
    storage_path: str | None = None
    download_status: str
    page_count: int | None = None
    extraction_status: str
    extracted_at: datetime | None = None
    published_at: date | None = None
    period_year: int | None = None
    period_type: str | None = None
    language: str | None = None
    collected_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    source: SourceList
    institution: InstitutionList | None = None

    model_config = {"from_attributes": True}
