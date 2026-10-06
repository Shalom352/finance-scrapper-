"""UMOA Banking Intelligence — Deal Intelligence reference values (Phase 13 & 14).

Closed vocabularies guarded by CHECK constraints. Nothing here is inferred at runtime:
a value outside these lists is refused at import, never mapped to a "closest" value.
"""

DEAL_TYPES = (
    "term_loan",
    "syndicated_loan",
    "project_finance",
    "trade_finance",
    "bond",
    "guarantee",
    "equity",
    "ipo",
    "sovereign_bond",
    "corporate_bond",
    "sukuk",
    "blended_finance",
    "m_and_a",
    "other",
    # Phase 19 (audits/ape_amf/07_proposition.md §1): the type comes from the AMF nature and the
    # document, never from the label alone. ``bond``, ``corporate_bond`` and ``equity`` stay valid
    # for existing rows but are frozen for new manual entries in favour of the values below.
    "sovereign_bond_ape",
    "corporate_bond_ape",
    "corporate_bond_private",
    "debt_buyback",
    "debt_exchange",
    "debt_reprofiling",
    "securitisation",
    "capital_increase",
    "share_sale_public",
    "takeover_offer",
)

PARTICIPANT_ROLES = (
    "borrower",
    "lender",
    "arranger",
    "co_arranger",
    "agent",
    "guarantor",
    "sponsor",
    "advisor",
    "investor",
    "insurer",
    "reinsurer",
    "issuer",
    "underwriter",
    "trustee",
    "facility_agent",
    "security_agent",
    # Phase 19 (07_proposition.md §2) — only when NAMED in the source, never deduced.
    # "Arrangeur et chef de file : X" gives two participations (arranger + lead_manager).
    "lead_manager",
    "co_lead_manager",
    "placement_syndicate_member",  # only if the note LISTS members ("toutes les SGI" creates nothing)
    "financial_advisor",
    "anchor_investor",
    "refinanced_lender",
    "selling_shareholder",
    "paying_agent",
)

# Roles through which an institution PROVIDES or ORGANISES financing (used by the targeting view).
FINANCING_ROLES = (
    "lender",
    "arranger",
    "co_arranger",
    "lead_manager",
    "co_lead_manager",
    "underwriter",
    "guarantor",
    "investor",
    "anchor_investor",
    "facility_agent",
    "agent",
    "refinanced_lender",
)

# How a participation was read in the source (07_proposition.md §2). visual_* is always needs_review.
PARTICIPANT_EXTRACTION_METHODS = ("text", "visual_logo", "visual_scan")

# Use of proceeds — closed list, several values allowed (07_proposition.md §3).
USE_OF_PROCEEDS_CATEGORIES = (
    "budget_financing",
    "infrastructure_project",
    "refinancing",
    "working_capital",
    "capital_adequacy",
    "housing_refinancing",
    "sme_financing",
    "green",
    "social",
    "privatisation",
    "other",
)

# Confidence class of a deal source (07_proposition.md §5). NULL = legacy row (before Phase 19).
SOURCE_CLASSES = (
    "primary_regulatory",  # information note with an AMF visa
    "primary_market",  # UMOA-Titres result, BRVM notice, DC/BR sheet
    "issuer_official",  # release on the issuer's / bank's own domain
    "issuer_press_release",  # signed issuer release reproduced in full
    "regulator_index",  # AMF API metadata: never a role (D2)
    "press_reported",  # press article: needs a primary source before verification (D4)
)
# A deal attested ONLY by these classes cannot be verified (409) until a primary source is added.
SECONDARY_SOURCE_CLASSES = ("press_reported", "regulator_index")

# Sectors of intervention (TOMASTEED offer) — closed list used by deals.sector for new entries
# and by the targeting view. Existing free-text sectors are kept as they are.
SECTORS = (
    "infrastructure_public",
    "energy",
    "agriculture",
    "industry",
    "telecom_media_tech",
    "real_estate",
    "financial_services",
    "public_finance",
    "other",
)

# SGI -> bank link (07_proposition.md §4, decision D3).
LINK_LEVELS = ("documented_bank", "documented_group_only")
LINK_RELATIONS = ("subsidiary", "shareholder")

INTEREST_RATE_TYPES = ("fixed", "floating")

AMOUNT_UNITS = ("units", "thousands", "millions", "billions")

DEAL_STATUSES = ("extracted", "needs_review", "reviewed", "verified", "rejected")

DUPLICATE_STATES = ("duplicate_candidate", "same_deal", "distinct_deals", "same_deal_multi_source")
DUPLICATE_DECISIONS = ("same_deal", "distinct_deals", "same_deal_multi_source")

# Deal fields whose provenance is tracked field by field (deal_field_sources).
PROVENANCE_FIELDS = (
    "title",
    "deal_type",
    "country_code",
    "sector",
    "project_name",
    "amount",
    "amount_original",
    "currency",
    "unit",
    "interest_rate",
    "interest_rate_type",
    "benchmark",
    "spread_bps",
    "maturity_months",
    "grace_period_months",
    "fees",
    "guarantees",
    "announcement_date",
    "signing_date",
    "financial_close_date",
    "closing_date",
)
# Phase 13 provenance vocabulary, kept for the migration 0014 downgrade.
LEGACY_PROVENANCE_FIELDS = PROVENANCE_FIELDS

# Structured public-debt instrument fields (migration 0014), tracked field by field as well.
INSTRUMENT_PROVENANCE_FIELDS = (
    "instrument_type",
    "isin",
    "auction_reference",
    "auction_date",
    "value_date",
    "maturity_date",
    "yield_rate",
)
PROVENANCE_FIELDS = PROVENANCE_FIELDS + INSTRUMENT_PROVENANCE_FIELDS
# Phase 14-18 vocabulary, kept for the migration 0016 downgrade.
PHASE18_PROVENANCE_FIELDS = PROVENANCE_FIELDS

# Use of proceeds and raw AMF filing agent (migration 0016), tracked field by field as well.
SOURCING_PROVENANCE_FIELDS = ("use_of_proceeds", "use_of_proceeds_categories", "filing_agent_raw")
PROVENANCE_FIELDS = PROVENANCE_FIELDS + SOURCING_PROVENANCE_FIELDS

# Public securities as named by the issuing Treasury / UMOA-Titres. Closed list: never guessed.
#   OAT = Obligation Assimilable du Trésor · BAT = Bon Assimilable du Trésor
INSTRUMENT_TYPES = ("OAT", "BAT")

# Validation rules applied by an automated ingestion, recorded on the deal (closed list).
DEAL_VALIDATION_FLAGS = (
    "global_total_rounded",  # printed global total = integer rounding of the tranche sum
    "issuer_label_truncated",  # issuer printed truncated, country confirmed by the ISIN prefix
    "page_lists_buyback_securities",  # emission page also lists bought-back securities (ignored, verified)
)

# ISO 4217 codes accepted at import. Explicit list: an unknown code is refused,
# never guessed. No conversion between currencies anywhere in the platform.
ISO_4217_CURRENCIES = frozenset(
    {
        "XOF", "XAF", "EUR", "USD", "GBP", "CHF", "JPY", "CNY", "CAD", "AUD",
        "MAD", "TND", "DZD", "EGP", "NGN", "GHS", "KES", "ZAR", "GNF", "MRU",
        "CVE", "GMD", "SLE", "LRD", "CDF", "RWF", "UGX", "TZS", "ETB", "MUR",
        "AED", "SAR", "QAR", "KWD", "INR", "TRY", "BRL", "SEK", "NOK", "DKK",
    }
)


def sql_in(values: tuple[str, ...]) -> str:
    """SQL literal list for CHECK constraints (static vocabulary only)."""
    return ", ".join(f"'{v}'" for v in values)
