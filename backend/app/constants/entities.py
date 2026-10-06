"""UMOA Financial Intelligence — Entity Hub & Relationship reference values (Phase 14).

Closed vocabularies guarded by CHECK constraints.
Universal abstraction across banking, insurance, markets, sovereign, microfinance, corporate.
"""

ENTITY_CLASSES = (
    "financial_institution",
    "regulator",
    "market_infrastructure",
    "sovereign_entity",
    "corporate",
    "project_spv",
    "macro_region",
)

ENTITY_TYPES = (
    "commercial_bank",
    "central_bank",
    "insurance_company",
    "reinsurer",
    "development_bank",
    "sfd",
    "fintech",
    "stock_exchange",
    "central_depository",
    "sovereign_state",
    "company",
    "holding_group",
    "project_company",
    "other",
)

ENTITY_STATUSES = (
    "active",
    "inactive",
    "under_resolution",
    "liquidated",
    "merged",
    "unknown",
)

RELATIONSHIP_TYPES = (
    "owns_equity",
    "controls_subsidiary",
    "holding_of",
    "branch_of",
    "finances_project",
    "syndicates_loan",
    "insures_asset",
    "reinsures_portfolio",
    "guarantees_debt",
    "listed_on_exchange",
    "cleared_by_depository",
    "supervises",
    "operates_in",
    "other",
)

OBSERVATION_LEVELS = (
    "entity",
    "group",
    "country",
    "regional",
    "market",
    "project",
    "deal",
)

CONSOLIDATION_SCOPES = (
    "individual",
    "consolidated",
    "not_applicable",
)


def sql_in(values: tuple[str, ...]) -> str:
    """SQL literal list for CHECK constraints (static vocabulary only)."""
    return ", ".join(f"'{v}'" for v in values)
