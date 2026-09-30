"""Deal import records (Phase 13) — strict Pydantic validation, nothing inferred.

A record describes ONE deal exactly as published. Every financial field is optional:
an absent field stays NULL (never 0). Each non-null field and each participant must be
attributed to at least one of the record's sources (field-level provenance).
A status is never accepted from a file: every imported deal starts as ``needs_review``.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.constants.deals import (
    AMOUNT_UNITS,
    DEAL_TYPES,
    INTEREST_RATE_TYPES,
    ISO_4217_CURRENCIES,
    PARTICIPANT_ROLES,
    PROVENANCE_FIELDS,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

DealType = Literal[DEAL_TYPES]  # type: ignore[valid-type]
Role = Literal[PARTICIPANT_ROLES]  # type: ignore[valid-type]
RateType = Literal[INTEREST_RATE_TYPES]  # type: ignore[valid-type]
Unit = Literal[AMOUNT_UNITS]  # type: ignore[valid-type]
ProvenanceField = Literal[PROVENANCE_FIELDS]  # type: ignore[valid-type]


def _currency(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in ISO_4217_CURRENCIES:
        raise ValueError(f"unknown ISO 4217 currency '{value}'")
    return value


class SourceRef(BaseModel):
    """An EXISTING document / source / page (checked against the database at import)."""

    model_config = ConfigDict(extra="forbid")

    ref: Ref
    document_id: Text
    source_id: Text
    page: int = Field(gt=0)
    excerpt: str | None = None
    # Deal fields this source attests (field-level provenance).
    fields: list[ProvenanceField] = Field(default_factory=list)


class ParticipantImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    # Must exist in `institutions` when given; a name alone keeps institution_id NULL.
    institution_id: str | None = None
    commitment_amount: Decimal | None = Field(default=None, gt=0)
    commitment_currency: str | None = None
    source_ref: Ref

    @field_validator("commitment_currency")
    @classmethod
    def iso_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @model_validator(mode="after")
    def commitment_currency_required(self) -> "ParticipantImport":
        if self.commitment_amount is not None and self.commitment_currency is None:
            raise ValueError("commitment_currency is required when commitment_amount is given")
        return self


class DealImportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Text
    deal_type: DealType | None = None
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] | None = None
    sector: str | None = None
    project_name: str | None = None
    amount_original: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    unit: Unit | None = None
    interest_rate: Decimal | None = None
    interest_rate_type: RateType | None = None
    benchmark: str | None = None
    spread_bps: Decimal | None = None
    maturity_months: int | None = Field(default=None, gt=0)
    grace_period_months: int | None = Field(default=None, ge=0)
    fees: str | None = None
    guarantees: str | None = None
    announcement_date: date | None = None
    signing_date: date | None = None
    financial_close_date: date | None = None
    closing_date: date | None = None
    participants: list[ParticipantImport] = Field(default_factory=list)
    sources: list[SourceRef] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @field_validator(
        "sector", "project_name", "amount_original", "benchmark", "fees", "guarantees", mode="before"
    )
    @classmethod
    def blank_is_missing(cls, value: object) -> object:
        # An empty cell means "not published" -> NULL, never an empty string.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def provenance_is_complete(self) -> "DealImportRecord":
        refs = [s.ref for s in self.sources]
        if len(set(refs)) != len(refs):
            raise ValueError("source refs must be unique within a deal")
        if self.amount is not None and self.currency is None:
            raise ValueError("currency is required when amount is given (no implicit currency)")
        attested = {f for s in self.sources for f in s.fields}
        missing = [f for f in PROVENANCE_FIELDS if getattr(self, f) is not None and f not in attested]
        if missing:
            raise ValueError(f"fields without source: {', '.join(missing)}")
        empty = sorted(f for f in attested if getattr(self, f) is None)
        if empty:
            raise ValueError(f"sources attest fields that are empty: {', '.join(empty)}")
        unknown = sorted({p.source_ref for p in self.participants} - set(refs))
        if unknown:
            raise ValueError(f"participants reference unknown source refs: {', '.join(unknown)}")
        return self
