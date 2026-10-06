"""
Phase 14 — Unit Tests for Markets & Public Debt Reference Values and Catalogues.

Tests:
- Constants integrity for market compartments, indices, and sovereign debt instrument types;
- Official market sources definition (BRVM, UMOA-Titres, AMF-UMOA, DC/BR);
- Official market metrics catalogue definitions (7 BRVM metrics + 5 UMOA-Titres metrics = 12 metrics);
- Sector tagging ('markets', 'sovereign') and metric families ('market_data', 'debt_service').
"""

from app.constants.markets import (
    MARKET_COMPARTMENTS,
    MARKET_INDICES,
    MARKET_METRIC_CODES,
    MARKET_METRICS,
    MARKET_OFFICIAL_SOURCES,
    PUBLIC_DEBT_INSTRUMENT_TYPES,
)


def test_market_constants_integrity():
    """Verify closed vocabularies for BRVM and UMOA-Titres market structures."""
    # Compartments
    assert "prestige" in MARKET_COMPARTMENTS
    assert "principal" in MARKET_COMPARTMENTS
    assert "obligations_souveraines" in MARKET_COMPARTMENTS
    assert "obligations_corporate" in MARKET_COMPARTMENTS
    assert "sukuk" in MARKET_COMPARTMENTS

    # Indices
    assert "brvm_composite" in MARKET_INDICES
    assert "brvm_30" in MARKET_INDICES
    assert "brvm_prestige" in MARKET_INDICES

    # Sovereign debt instruments
    assert "bat" in PUBLIC_DEBT_INSTRUMENT_TYPES
    assert "oat" in PUBLIC_DEBT_INSTRUMENT_TYPES
    assert "sukuk_etat" in PUBLIC_DEBT_INSTRUMENT_TYPES


def test_official_market_sources():
    """Verify official sources catalogue for regional market entities."""
    short_names = [s["short_name"] for s in MARKET_OFFICIAL_SOURCES]
    assert "BRVM" in short_names
    assert "UMOA-Titres" in short_names
    assert "AMF-UMOA" in short_names
    assert "DC/BR" in short_names

    for src in MARKET_OFFICIAL_SOURCES:
        assert src["priority"] == 1
        assert src["is_active"] is True
        assert src["url"].startswith("https://")


def test_market_metrics_catalogue():
    """Verify the 12 official market and public debt metrics."""
    assert len(MARKET_METRICS) == 12
    assert len(MARKET_METRIC_CODES) == 12

    # BRVM Equity & Bond Market metrics
    assert "capitalisation_actions" in MARKET_METRIC_CODES
    assert "capitalisation_obligations" in MARKET_METRIC_CODES
    assert "indice_brvm_composite" in MARKET_METRIC_CODES
    assert "indice_brvm_30" in MARKET_METRIC_CODES
    assert "valeur_transactions_actions" in MARKET_METRIC_CODES
    assert "per_moyen_marche" in MARKET_METRIC_CODES
    assert "rendement_moyen_dividende" in MARKET_METRIC_CODES

    # UMOA-Titres Public Debt metrics
    assert "encours_titres_publics" in MARKET_METRIC_CODES
    assert "montant_emis_titres_publics" in MARKET_METRIC_CODES
    assert "taux_moyen_adjudication_bat" in MARKET_METRIC_CODES
    assert "taux_moyen_adjudication_oat" in MARKET_METRIC_CODES
    assert "taux_couverture_adjudications" in MARKET_METRIC_CODES

    for m in MARKET_METRICS:
        assert m["sector"] in ("markets", "sovereign")
        assert m["metric_family"] in ("market_data", "debt_service")
        assert m["is_calculated"] is False
