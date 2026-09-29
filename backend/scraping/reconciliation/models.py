"""
UMOA Banking Intelligence — Reconciliation Models

Dataclasses capturing institution candidates, match scoring, and final resolution results.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MatchCandidate:
    """A potential institution match with scoring and evidence."""

    institution_id: str
    name_official: str
    country_code: str  # ISO 3166-1 alpha-2 (e.g. CI, SN, TG)
    score: float  # 0.0 to 1.0
    match_type: str  # exact_official, exact_commercial, alias, token_overlap, etc.
    name_commercial: str | None = None
    evidence: str = ""


@dataclass
class ResolutionResult:
    """Final output of resolving an extracted name against the institution registry."""

    raw_input: str
    normalized_input: str
    institution_id: str | None = None
    institution_name: str | None = None
    country_code: str | None = None
    confidence_score: float = 0.0
    confidence_level: str = "no_match"  # high_confidence | medium_confidence | low_confidence | no_match
    status: str = "no_match"  # matched | ambiguous | no_match
    matched_by: str | None = None
    notes: str | None = None
    candidates: list[MatchCandidate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstitutionEntity:
    """Registry entry for an institution used by the reconciliation index."""

    id: str
    name_official: str
    country_code: str  # ISO 3166-1 alpha-2
    name_commercial: str | None = None
    aliases: list[str] = field(default_factory=list)
    institution_type: str = "bank"
    banking_group_id: str | None = None
