"""Phase 19 — deal sourcing vocabulary and import rules (no database)."""
import pytest
from pydantic import ValidationError

from app.constants.deals import (
    DEAL_TYPES,
    FINANCING_ROLES,
    PARTICIPANT_ROLES,
    PROVENANCE_FIELDS,
    SECONDARY_SOURCE_CLASSES,
    SOURCE_CLASSES,
)
from scraping.deals.schemas import DealImportRecord

NOTE = {"ref": "n", "document_id": "d1", "source_id": "s1", "page": 15, "source_class": "primary_regulatory"}


def record(**over):
    base = {"title": "État du Sénégal APE 2025", "deal_type": "sovereign_bond_ape", "sources": [dict(NOTE)]}
    base["sources"][0]["fields"] = ["title", "deal_type"]
    base.update(over)
    return base


def test_vocabulary_extends_without_removing_existing_values():
    for old in ("sovereign_bond", "bond", "corporate_bond", "equity", "other"):
        assert old in DEAL_TYPES
    for new in ("sovereign_bond_ape", "debt_buyback", "capital_increase", "share_sale_public"):
        assert new in DEAL_TYPES
    assert {"lead_manager", "co_lead_manager", "anchor_investor", "refinanced_lender"} <= set(PARTICIPANT_ROLES)
    assert set(FINANCING_ROLES) <= set(PARTICIPANT_ROLES)
    assert {"use_of_proceeds", "use_of_proceeds_categories", "filing_agent_raw"} <= set(PROVENANCE_FIELDS)
    assert set(SECONDARY_SOURCE_CLASSES) <= set(SOURCE_CLASSES)
    assert all(len(r) <= 40 for r in PARTICIPANT_ROLES)


def test_arranger_and_lead_manager_are_two_participations_with_page_and_excerpt():
    excerpt = "CGF Bourse, arrangeur et chef de file"
    r = DealImportRecord.model_validate(record(participants=[
        {"role": "arranger", "name": "CGF Bourse", "source_ref": "n", "page": 15, "excerpt": excerpt,
         "extraction_method": "text"},
        {"role": "lead_manager", "name": "CGF Bourse", "source_ref": "n", "page": 15, "excerpt": excerpt,
         "extraction_method": "text"},
    ]))
    assert [p.role for p in r.participants] == ["arranger", "lead_manager"]


def test_use_of_proceeds_needs_a_source_and_closed_categories():
    with pytest.raises(ValidationError, match="fields without source: use_of_proceeds"):
        DealImportRecord.model_validate(record(use_of_proceeds="financer le budget 2025"))
    rec = record(use_of_proceeds="financer le budget 2025", use_of_proceeds_categories=["budget_financing"])
    rec["sources"][0]["fields"] += ["use_of_proceeds", "use_of_proceeds_categories"]
    assert DealImportRecord.model_validate(rec).use_of_proceeds_categories == ["budget_financing"]
    rec["use_of_proceeds_categories"] = ["roads"]
    with pytest.raises(ValidationError):
        DealImportRecord.model_validate(rec)
    rec["use_of_proceeds_categories"] = ["green", "green"]
    with pytest.raises(ValidationError, match="must not repeat"):
        DealImportRecord.model_validate(rec)


def test_amf_index_is_never_a_source_of_roles():
    amf = {"ref": "amf", "document_id": "d2", "source_id": "s2", "page": 1, "source_class": "regulator_index",
           "fields": ["filing_agent_raw"]}
    rec = record(filing_agent_raw="ABCO BOURSE")
    rec["sources"].append(amf)
    assert DealImportRecord.model_validate(rec).filing_agent_raw == "ABCO BOURSE"
    rec["participants"] = [{"role": "arranger", "name": "ABCO BOURSE", "source_ref": "amf"}]
    with pytest.raises(ValidationError, match="never a source of roles"):
        DealImportRecord.model_validate(rec)
    rec["participants"] = []
    rec["sources"][1]["fields"] = ["filing_agent_raw", "amount"]
    with pytest.raises(ValidationError, match="regulator_index"):
        DealImportRecord.model_validate(rec)


def test_press_requires_url_and_publisher_and_paywall_gives_metadata_only():
    press = {"ref": "p", "document_id": "d3", "source_id": "s3", "page": 1, "source_class": "press_reported",
             "publisher": "Financial Afrik", "url": "https://www.financialafrik.com/x", "fields": []}
    rec = record()
    rec["sources"].append(dict(press))
    DealImportRecord.model_validate(rec)
    rec["sources"][1] = {**press, "url": None}
    with pytest.raises(ValidationError, match="url and publisher"):
        DealImportRecord.model_validate(rec)
    rec["sources"][1] = {**press, "paywalled": True, "fields": ["title"]}
    with pytest.raises(ValidationError, match="paywalled"):
        DealImportRecord.model_validate(rec)
    rec["sources"][1] = {**press, "paywalled": True}
    rec["participants"] = [{"role": "arranger", "name": "X", "source_ref": "p"}]
    with pytest.raises(ValidationError, match="paywalled article cannot attest a role"):
        DealImportRecord.model_validate(rec)
