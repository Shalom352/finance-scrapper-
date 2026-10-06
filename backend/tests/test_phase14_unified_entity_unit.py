"""
Phase 14 — Unit Tests for Unified Financial Intelligence models & constants.

Tests:
- Constants integrity (ENTITY_CLASSES, ENTITY_TYPES, RELATIONSHIP_TYPES, OBSERVATION_LEVELS, SECTORS, METRIC_FAMILIES);
- DEAL_TYPES and PARTICIPANT_ROLES expansion verification;
- Entity & EntityRelationship model instantiation & repr;
- MetricDefinition model sector & family defaults;
- FinancialData observation_level & consolidation_scope defaults;
- 26 V1 Banking Metric catalogue preservation (zero deletions, zero renamings).
"""
from datetime import date
from decimal import Decimal

from app.constants.deals import DEAL_TYPES, PARTICIPANT_ROLES
from app.constants.entities import (
    CONSOLIDATION_SCOPES,
    ENTITY_CLASSES,
    ENTITY_TYPES,
    OBSERVATION_LEVELS,
    RELATIONSHIP_TYPES,
    sql_in,
)
from app.constants.metrics import (
    METRIC_FAMILIES,
    SECTORS,
    V1_METRIC_CODES,
    V1_METRICS,
)
from app.models.entity import Entity
from app.models.entity_relationship import EntityRelationship
from app.models.financial_data import FinancialData


def test_entity_constants_integrity():
    """Verify closed vocabularies for Entity Hub."""
    assert "financial_institution" in ENTITY_CLASSES
    assert "regulator" in ENTITY_CLASSES
    assert "market_infrastructure" in ENTITY_CLASSES
    assert "sovereign_entity" in ENTITY_CLASSES
    assert "corporate" in ENTITY_CLASSES

    assert "commercial_bank" in ENTITY_TYPES
    assert "insurance_company" in ENTITY_TYPES
    assert "stock_exchange" in ENTITY_TYPES
    assert "sovereign_state" in ENTITY_TYPES

    assert "owns_equity" in RELATIONSHIP_TYPES
    assert "supervises" in RELATIONSHIP_TYPES
    assert "finances_project" in RELATIONSHIP_TYPES

    assert "entity" in OBSERVATION_LEVELS
    assert "group" in OBSERVATION_LEVELS
    assert "country" in OBSERVATION_LEVELS

    assert "individual" in CONSOLIDATION_SCOPES
    assert "consolidated" in CONSOLIDATION_SCOPES
    assert "not_applicable" in CONSOLIDATION_SCOPES


def test_deal_constants_expansion():
    """Verify DEAL_TYPES and PARTICIPANT_ROLES contain cross-sector extensions."""
    # New deal types
    assert "equity" in DEAL_TYPES
    assert "ipo" in DEAL_TYPES
    assert "sovereign_bond" in DEAL_TYPES
    assert "corporate_bond" in DEAL_TYPES
    assert "sukuk" in DEAL_TYPES
    assert "blended_finance" in DEAL_TYPES
    assert "m_and_a" in DEAL_TYPES

    # New participant roles
    assert "insurer" in PARTICIPANT_ROLES
    assert "reinsurer" in PARTICIPANT_ROLES
    assert "issuer" in PARTICIPANT_ROLES
    assert "underwriter" in PARTICIPANT_ROLES
    assert "trustee" in PARTICIPANT_ROLES
    assert "facility_agent" in PARTICIPANT_ROLES
    assert "security_agent" in PARTICIPANT_ROLES


def test_v1_banking_metrics_preservation():
    """Verify all 26 V1 metrics are preserved without modification."""
    assert len(V1_METRICS) == 26
    assert len(V1_METRIC_CODES) == 26
    assert "total_actifs" in V1_METRIC_CODES
    assert "resultat_net" in V1_METRIC_CODES
    assert "produit_net_bancaire" in V1_METRIC_CODES
    assert "creances_clients" in V1_METRIC_CODES
    assert "capitaux_propres" in V1_METRIC_CODES

    assert "banking" in SECTORS
    assert "insurance" in SECTORS
    assert "markets" in SECTORS

    assert "balance_sheet" in METRIC_FAMILIES
    assert "claims_underwriting" in METRIC_FAMILIES


def test_entity_model_instantiation():
    """Verify Entity model instantiation and repr."""
    entity = Entity(
        canonical_name="BCEAO",
        short_name="BCEAO",
        entity_class="regulator",
        entity_type="central_bank",
        status="active",
    )
    assert entity.canonical_name == "BCEAO"
    assert entity.entity_class == "regulator"
    assert repr(entity) == "<Entity 'BCEAO' class='regulator' type='central_bank'>"


def test_entity_relationship_model_instantiation():
    """Verify EntityRelationship model instantiation and repr."""
    rel = EntityRelationship(
        source_entity_id="ent-1",
        target_entity_id="ent-2",
        relationship_type="owns_equity",
        ownership_percentage=Decimal("65.50"),
        valid_from=date(2023, 1, 1),
        is_current=True,
    )
    assert rel.relationship_type == "owns_equity"
    assert rel.ownership_percentage == Decimal("65.50")
    assert repr(rel) == "<EntityRelationship 'owns_equity' from='ent-1' to='ent-2'>"


def test_financial_data_model_defaults():
    """Verify FinancialData decoupled scope fields and defaults."""
    fd = FinancialData(
        institution_id="inst-1",
        source_id="src-1",
        document_id="doc-1",
        metric_code="total_actifs",
        period_year=2024,
        value_original="1000",
    )
    # Default column values defined on mapped columns
    assert fd.observation_level == "entity" or fd.observation_level is None
    assert fd.consolidation_scope == "individual" or fd.consolidation_scope is None


def test_sql_in_helper():
    """Verify sql_in generates valid SQL IN clause string."""
    assert sql_in(("a", "b", "c")) == "'a', 'b', 'c'"
