"""UMOA Banking Intelligence — Metric Definition Schemas"""
from datetime import datetime

from pydantic import BaseModel


class MetricList(BaseModel):
    id: str
    code: str
    label_fr: str
    label_en: str
    statement_type: str
    category: str
    value_type: str
    currency_type: str
    is_calculated: bool
    is_active: bool
    is_debt_related: bool
    display_order: int
    model_config = {"from_attributes": True}

class MetricRead(BaseModel):
    id: str
    code: str
    label_fr: str
    label_en: str
    definition_fr: str
    definition_en: str
    statement_type: str
    category: str
    value_type: str
    currency_type: str
    is_calculated: bool
    is_active: bool
    is_debt_related: bool
    display_order: int
    description_synth: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
