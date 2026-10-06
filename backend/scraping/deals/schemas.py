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
    DEAL_VALIDATION_FLAGS,
    INSTRUMENT_TYPES,
    INTEREST_RATE_TYPES,
    ISO_4217_CURRENCIES,
    PARTICIPANT_EXTRACTION_METHODS,
    PARTICIPANT_ROLES,
    PROVENANCE_FIELDS,
    SOURCE_CLASSES,
    USE_OF_PROCEEDS_CATEGORIES,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

DealType = Literal[DEAL_TYPES]  # type: ignore[valid-type]
Role = Literal[PARTICIPANT_ROLES]  # type: ignore[valid-type]
RateType = Literal[INTEREST_RATE_TYPES]  # type: ignore[valid-type]
Unit = Literal[AMOUNT_UNITS]  # type: ignore[valid-type]
ProvenanceField = Literal[PROVENANCE_FIELDS]  # type: ignore[valid-type]
InstrumentType = Literal[INSTRUMENT_TYPES]  # type: ignore[valid-type]
SourceClass = Literal[SOURCE_CLASSES]  # type: ignore[valid-type]
ExtractionMethod = Literal[PARTICIPANT_EXTRACTION_METHODS]  # type: ignore[valid-type]
ProceedsCategory = Literal[USE_OF_PROCEEDS_CATEGORIES]  # type: ignore[valid-type]
Isin = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")]


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
    # Phase 19 — confidence class and press / release metadata (an article body is never stored).
    source_class: SourceClass | None = None
    publisher: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    title: str | None = None
    url: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^https?://")] | None = None
    published_at: date | None = None
    paywalled: bool | None = None

    @model_validator(mode="after")
    def press_rules(self) -> "SourceRef":
        if self.source_class == "press_reported" and (self.url is None or self.publisher is None):
            raise ValueError("a press_reported source requires url and publisher")
        if self.paywalled and self.fields:
            raise ValueError("a paywalled article gives title, date and URL only: it cannot attest fields")
        if self.source_class == "regulator_index" and set(self.fields) - {"filing_agent_raw", "title",
                                                                           "deal_type", "country_code"}:
            raise ValueError("a regulator_index source (AMF API) only attests title, type, country and filing agent")
        return self


class ValidationFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[DEAL_VALIDATION_FLAGS]  # type: ignore[valid-type]
    detail: Text


class ParticipantImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    # Must exist in `institutions` when given; a name alone keeps institution_id NULL.
    institution_id: str | None = None
    # Must exist in `entities` when given (e.g. a sovereign_state issuer).
    entity_id: str | None = None
    commitment_amount: Decimal | None = Field(default=None, gt=0)
    commitment_currency: str | None = None
    source_ref: Ref
    # Where the role is NAMED in the source (Phase 19).
    page: int | None = Field(default=None, gt=0)
    excerpt: str | None = None
    extraction_method: ExtractionMethod | None = None

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
    # Public-debt instrument (all optional, NULL when not published).
    instrument_type: InstrumentType | None = None
    isin: Isin | None = None
    auction_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    auction_date: date | None = None
    value_date: date | None = None
    maturity_date: date | None = None
    yield_rate: Decimal | None = None
    # Deterministic idempotence key of an automated ingestion (not a published field).
    ingestion_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    validation_flags: list[ValidationFlag] = Field(default_factory=list)
    # Sourcing (Phase 19): quoted use of proceeds, closed categories, raw AMF filing agent (never a role).
    use_of_proceeds: str | None = None
    use_of_proceeds_categories: list[ProceedsCategory] | None = None
    filing_agent_raw: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    participants: list[ParticipantImport] = Field(default_factory=list)
    sources: list[SourceRef] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @field_validator(
        "sector", "project_name", "amount_original", "benchmark", "fees", "guarantees", "use_of_proceeds",
        mode="before",
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
        if self.maturity_date and self.value_date and self.maturity_date <= self.value_date:
            raise ValueError("maturity_date must be after value_date")
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
        if self.use_of_proceeds_categories is not None:
            if not self.use_of_proceeds_categories:
                raise ValueError("use_of_proceeds_categories must be omitted, not empty")
            if len(set(self.use_of_proceeds_categories)) != len(self.use_of_proceeds_categories):
                raise ValueError("use_of_proceeds_categories must not repeat a value")
        by_ref = {s.ref: s for s in self.sources}
        for p in self.participants:
            src = by_ref[p.source_ref]
            if src.paywalled:
                raise ValueError(f"participant '{p.name}': a paywalled article cannot attest a role")
            if src.source_class == "regulator_index":
                raise ValueError(f"participant '{p.name}': the AMF API index is never a source of roles (D2)")
        return self
