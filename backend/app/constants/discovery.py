"""UMOA Financial Intelligence — Entity & Source Discovery Engine vocabularies (Phase 15).

Closed vocabularies guarded by CHECK constraints (migration 0011).

Core rule: the expected universe comes from an official reference document. A count that
cannot be read from an official document stays NULL (coverage UNKNOWN), never guessed.
"""

from app.constants.entities import sql_in

__all__ = ["sql_in"]

# ---------------------------------------------------------------------------
# Reference universes
# ---------------------------------------------------------------------------
UNIVERSE_BANKING = "UMOA.BANKING"

UNIVERSE_STATUSES = (
    "COMPLETE",  # every expected member is resolved to an entity
    "INCOMPLETE",  # self-check passed but some members are unresolved / ambiguous
    "UNKNOWN",  # expected count not stated by the reference document
    "SOURCE_UNAVAILABLE",  # the reference document could not be fetched / read
    "AMBIGUOUS",  # the reference document is internally inconsistent (self-check failed)
)

# Category of a licensed credit institution in the BCEAO / CB-UMOA lists.
MEMBER_CATEGORIES = ("bank", "financial_establishment")

MEMBER_FORMS = ("subsidiary", "branch", "unspecified")

RESOLUTION_STATUSES = (
    "matched",  # resolved to a pre-existing entity
    "created",  # a new entity was created from this official line
    "ambiguous",  # several candidates: human review required, nothing linked
    "unresolved",  # not processed / failed
)

REVIEW_DECISIONS = ("confirmed", "rejected")

# ---------------------------------------------------------------------------
# Entity identifiers & names
# ---------------------------------------------------------------------------
IDENTIFIER_TYPES = ("bceao_registration_number",)

NAME_TYPES = (
    "official",
    "acronym",
    "former",
    "alias",
    "commercial",
    "regulatory_label",  # label used for the entity in a regulatory publication
)

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
SOURCE_LIFECYCLE_STATUSES = ("CANDIDATE", "VERIFIED", "ACTIVE", "BLOCKED", "RETIRED")

# Source discovery priority order (1 = highest). A lower-priority link never replaces
# a higher-priority one; both are kept with their own lifecycle status.
LINK_ROLE_PRIORITY: dict[str, int] = {
    "regulatory_listing": 1,
    "official_website": 2,
    "official_publications": 3,
    "market_infrastructure": 4,
    "public_body": 5,
    "professional_federation": 6,
    "secondary": 7,
}
LINK_ROLES = tuple(LINK_ROLE_PRIORITY)

# Roles that count as an institution-owned official source (website / own publications).
OFFICIAL_OWN_ROLES = ("official_website", "official_publications")

DOCUMENT_LINK_TYPES = (
    "reference_listing",  # the entity is listed in an official licensing list
    "financial_statement",  # per-entity balance sheet / income statement pages
    "annual_report",
    "regulatory_mention",
    "other",
)

# Link types that make a document a *financial* document for coverage purposes.
FINANCIAL_DOCUMENT_LINK_TYPES = ("financial_statement", "annual_report")

# ---------------------------------------------------------------------------
# Discovery runs, rounds, stop conditions
# ---------------------------------------------------------------------------
DISCOVERY_RUN_STATUSES = ("running", "completed", "failed")

DISCOVERY_TRIGGER_TYPES = ("cli", "scheduled", "manual", "test")

STOP_CONDITIONS = (
    "A_UNIVERSE_COVERED",  # no discoverable gap left
    "B_STRATEGIES_EXHAUSTED",  # every applicable strategy tried, no further progress
    "C_REFERENCE_UNAVAILABLE",  # official reference missing / ambiguous → COVERAGE INCOMPLETE
    "SAFETY_CAP_REACHED",  # technical round cap hit → never reported as complete
)

# ---------------------------------------------------------------------------
# Source gap queue
# ---------------------------------------------------------------------------
GAP_TYPES = (
    "ENTITY_UNRESOLVED",  # official list line not resolved to an entity (ambiguous)
    "REGULATORY_SOURCE",  # no regulatory listing linked to the entity
    "OFFICIAL_WEBSITE",  # legacy (Phase 15) — superseded by the SOURCE_* types, kept for history
    "ANNUAL_REPORT",  # legacy (Phase 15) — superseded by the DOCUMENT_* types, kept for history
    "FINANCIAL_DOCUMENT",  # no financial document at all (regulatory or own)
    "FINANCIAL_DATA",  # no financial observation on a catalogue metric
    "VALIDATION",  # observations exist but none verified (human action only)
    # --- Phase 17: institution-specific taxonomy. NOT_FOUND never means "does not exist":
    # only that the strategies executed so far found nothing relevant.
    "SOURCE_NOT_FOUND",  # no institutional source (own site / publications / market filings) found
    "SOURCE_FOUND_UNVERIFIED",  # a candidate source exists but could not be verified (content / TLS)
    "SOURCE_BLOCKED",  # the only candidate source refuses access (401/403/429, robots.txt)
    "DOCUMENT_NOT_FOUND",  # no institution-specific document found
    "DOCUMENT_FOUND_UNVERIFIED",  # institution-specific document(s) found but not yet analysed
    "DOCUMENT_NOT_MACHINE_READABLE",  # every institution-specific document lacks a reliable text layer
    "ENTITY_AMBIGUOUS",  # a document / issuer label matches several entities (human review)
    "PARENT_SUBSIDIARY_AMBIGUITY",  # a branch's parent named by the official list is not resolved
    "HISTORICAL_NAME_AMBIGUITY",  # a label only matches through a former name and is ambiguous
)

# Phase-15 types no longer generated (open ones are closed as superseded).
LEGACY_GAP_TYPES = ("OFFICIAL_WEBSITE", "ANNUAL_REPORT")

# Gap types no automatic strategy can close (a human decision is required).
HUMAN_ONLY_GAP_TYPES = (
    "ENTITY_UNRESOLVED", "VALIDATION", "ENTITY_AMBIGUOUS", "PARENT_SUBSIDIARY_AMBIGUITY",
    "HISTORICAL_NAME_AMBIGUITY",
)

GAP_PRIORITIES = ("HIGH", "MEDIUM", "LOW")

GAP_STATUSES = ("OPEN", "SEARCHING", "NOT_FOUND", "BLOCKED", "RESOLVED")

GAP_PRIORITY_BY_TYPE: dict[str, str] = {
    "ENTITY_UNRESOLVED": "HIGH",
    "REGULATORY_SOURCE": "HIGH",
    "FINANCIAL_DOCUMENT": "HIGH",
    "OFFICIAL_WEBSITE": "MEDIUM",
    "ANNUAL_REPORT": "MEDIUM",
    "FINANCIAL_DATA": "MEDIUM",
    "VALIDATION": "LOW",
    "SOURCE_NOT_FOUND": "HIGH",
    "SOURCE_FOUND_UNVERIFIED": "HIGH",
    "SOURCE_BLOCKED": "MEDIUM",
    "DOCUMENT_NOT_FOUND": "HIGH",
    "DOCUMENT_FOUND_UNVERIFIED": "HIGH",
    "DOCUMENT_NOT_MACHINE_READABLE": "MEDIUM",
    "ENTITY_AMBIGUOUS": "HIGH",
    "PARENT_SUBSIDIARY_AMBIGUITY": "MEDIUM",
    "HISTORICAL_NAME_AMBIGUITY": "MEDIUM",
}

# Default retry delay for a gap that could not be closed (days).
DEFAULT_GAP_RETRY_DAYS = 7

# The 8 UMOA member states (ISO 3166-1 alpha-2), as seeded by migration 0003.
UMOA_COUNTRY_CODES = ("BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG")
