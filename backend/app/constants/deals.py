"""UMOA Banking Intelligence — Deal Intelligence reference values (Phase 13).

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
    "other",
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
)

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
