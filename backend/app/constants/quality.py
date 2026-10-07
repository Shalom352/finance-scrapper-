"""UMOA Financial Intelligence — scope evidence, document scope and quality flags (Phase 16).

Closed vocabularies guarded by CHECK constraints (migration 0012).

Scope evidence hierarchy (automatic detection NEVER produces reviewed / verified):
  A  scope explicitly stated on the observation's page        → may be ``extracted``
  B  scope explicitly stated by the document title, no contrary
     mention anywhere in the document                          → may be ``extracted``
  C  scope only inferred (documented convention, mention on
     another page)                                             → ``needs_review``
  D  no evidence, contradiction, unreadable document           → ``needs_review``
"""

from app.constants.entities import sql_in

__all__ = ["sql_in"]

SCOPE_EVIDENCE_CLASSES = ("A", "B", "C", "D")
PROMOTABLE_SCOPE_CLASSES = ("A", "B")

SCOPE_REASON_CODES = (
    "scope_explicit_page",
    "scope_explicit_document_title",
    "scope_inferred_from_regulatory_per_entity_reporting_convention",
    "scope_mentioned_elsewhere_only",
    "scope_not_stated",
    "scope_conflicting_mentions",
    "document_not_machine_readable",
    "scope_not_applicable",  # market / sovereign observations (consolidation_scope = not_applicable)
    # Phase 22: an institution document whose value equals the BCEAO fascicle value (same entity,
    # metric, year) carries the fascicle's per-entity scope — class C, never stronger than the fascicle.
    "scope_corroborated_by_regulatory_fascicle",
)

# Documented knowledge (NOT documentary proof): the BCEAO fascicle publishes one balance sheet
# and one income statement per licensed credit institution (branches included). The document
# never states "individuel" / "consolidé": the scope is only inferred → class C.
FASCICLE_CONVENTION_REASON = "scope_inferred_from_regulatory_per_entity_reporting_convention"

DOCUMENT_SCOPES = ("regulatory_aggregate", "institution_specific", "reference_listing", "market", "unknown")

QUALITY_FLAGS = (
    "zero_on_structural_metric",  # e.g. total_actifs = 0, depots_clients = 0 with total_actifs > 0
    "negative_equity",  # informational: plausible for a distressed bank
    "cross_statement_mismatch",  # P&L RESULTAT NET ≠ balance-sheet RESULTAT DE L'EXERCICE
    "cross_edition_mismatch",  # same entity / metric / year differs between two editions
    "unit_or_currency_not_stated",  # the statement does not state its unit / currency: not normalized
    "cross_document_mismatch",  # same entity / metric / year differs between two institution documents
    "unit_corroborated",  # informational: unit / scope established by agreement with the BCEAO fascicle
    "unit_reread",  # informational: unit corrected by a later re-read of the document (before -> after in notes)
)

# Flags that make a qualification uncertain: they block any automatic promotion.
BLOCKING_QUALITY_FLAGS = (
    "zero_on_structural_metric", "cross_statement_mismatch", "cross_edition_mismatch",
    "unit_or_currency_not_stated", "cross_document_mismatch",
)

# Text layer of a document (Phase 17). Only 'machine_readable' pages are ever extracted.
TEXT_LAYER_STATUSES = ("machine_readable", "partially_corrupted", "not_machine_readable", "unknown")
