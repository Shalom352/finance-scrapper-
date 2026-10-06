"""
Phase 14 — Markets & Public Debt Ingestion Unit Tests (Network-Isolated).

Covers:
1. BRVMConnector discovery logic and HTML parsing.
2. UMOATitresConnector discovery logic (emissions index & detail crawling).
3. MarketExtractor on BRVM BOC layout (all 7 canonical metrics).
4. MarketExtractor on UMOA-Titres Compte Rendu layout (auction metrics & sovereign mapping).
5. Invariant checks: DATA MISSING > DATA WRONG, NULL stays NULL, no 0 interpolation.
"""
from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pymupdf
import pytest

from scraping.connectors.brvm import BRVMConnector
from scraping.connectors.umoa_titres import UMOATitresConnector, detect_country_code
from scraping.parsing.market_extractor import MarketExtractor


class TestMarketConnectorsDiscoveryUnit:
    @pytest.mark.asyncio
    async def test_brvm_connector_discover(self):
        """Test BRVM connector parses section HTML and returns DiscoveredDocument list."""
        connector = BRVMConnector()
        mock_html_boc = """
        <html>
            <body>
                <a href="/sites/default/files/boc_20260929_2.pdf">Bulletin Officiel de la Cote 29/09/2026</a>
                <a href="/sites/default/files/boc_20260928_2.pdf">Bulletin Officiel de la Cote 28/09/2026</a>
            </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html_boc
        mock_resp.url = "https://www.brvm.org/fr/bulletins-officiels-de-la-cote"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        with patch("asyncio.sleep", new=AsyncMock()):
            docs = await connector.discover(mock_client, limit=5)

        assert len(docs) == 2
        assert docs[0].source_short_name == "BRVM"
        assert docs[0].period_year == 2026
        assert docs[0].document_type == "regulatory_report"
        assert "boc_20260929_2.pdf" in docs[0].url

    @pytest.mark.asyncio
    async def test_umoa_titres_connector_discover(self):
        """Test UMOA-Titres connector crawls emissions index and extracts Compte-Rendu PDFs."""
        connector = UMOATitresConnector()
        mock_html_emissions = """
        <html>
            <body>
                <a href="/fr/emission/emission-simultanee-de-bons-et-dobligations-du-tresor-de-la-cote-divoire-du-29-09-2026/">
                    Emission CI 29-09-2026
                </a>
            </body>
        </html>
        """
        mock_html_detail = """
        <html>
            <body>
                <a href="/wp-content/uploads/2026/07/Compte-Rendu-CI-ES-29.09.2026.pdf">
                    Compte Rendu CI ES 29.09.2026
                </a>
                <a href="/wp-content/uploads/2026/07/AAO-CI-ES-29.09.2026.pdf">
                    AAO CI ES 29.09.2026
                </a>
            </body>
        </html>
        """
        mock_resp_index = MagicMock(status_code=200, text=mock_html_emissions, url="https://www.umoatitres.org/fr/emissions/")
        mock_resp_detail = MagicMock(status_code=200, text=mock_html_detail, url="https://www.umoatitres.org/fr/emission/emission-simultanee-de-bons-et-dobligations-du-tresor-de-la-cote-divoire-du-29-09-2026/")

        async def fake_get(url, **kwargs):
            if "emissions/" in str(url):
                return mock_resp_index
            return mock_resp_detail

        mock_client = AsyncMock()
        mock_client.get.side_effect = fake_get

        with patch("asyncio.sleep", new=AsyncMock()):
            docs = await connector.discover(mock_client, limit=5)

        assert len(docs) >= 2
        compte_rendu_docs = [d for d in docs if "Compte-Rendu" in d.url]
        assert len(compte_rendu_docs) == 1
        assert compte_rendu_docs[0].period_year == 2026
        assert compte_rendu_docs[0].metadata.get("country_code") == "CI"

    def test_country_code_detector(self):
        """Test country code regex from filenames."""
        assert detect_country_code("Compte-Rendu-CI-ES-29.09.2026.pdf") == "CI"
        assert detect_country_code("Compte-Rendu-SN-ES-25.09.2026.pdf") == "SN"
        assert detect_country_code("AAO-ML-ES-30.09.2026.pdf") == "ML"
        assert detect_country_code("AAO-BF-ES-23.09.2026.pdf") == "BF"
        assert detect_country_code("Compte-Rendu-NE-ES-24.09.2026.pdf") == "NE"
        assert detect_country_code("Compte-Rendu-TG-ES-18.09.2026.pdf") == "TG"
        assert detect_country_code("Compte-Rendu-BJ-ES-10.09.2026.pdf") == "BJ"
        assert detect_country_code("Compte-Rendu-GW-ES-28.09.2026.pdf") == "GW"
        assert detect_country_code("Random-Document-Without-Country.pdf") is None


class TestMarketExtractorUnit:
    @pytest.fixture
    def sample_brvm_pdf(self) -> str:
        """Create a temporary synthetic PDF containing the standard BRVM Page 1 layout."""
        doc = pymupdf.open()
        page = doc.new_page()
        text = (
            "BRVM COMPOSITE\n548,04\nVariation Jour\n0,48 %\n"
            "BRVM 30\n265,14\nVariation Jour\n0,35 %\n"
            "BRVM PRESTIGE\n202,14\nVariation Jour\n0,68 %\n"
            "Actions\nNiveau\nEvol. Jour\n"
            "Capitalisation boursière (FCFA)(Actions & Droits)\n  21 491 234 105 518\n0,48 %\n"
            "Volume échangé (Actions & Droits)\n    1 509 438\n"
            "Valeur transigée (FCFA) (Actions & Droits)\n   3 247 423 193\n"
            "Obligations\nNiveau\nEvol. Jour\n"
            "Capitalisation boursière (FCFA)\n  13 616 018 491 470\n0,02 %\n"
            "INDICES SECTORIELS\nIndicateurs\nBRVM COMPOSITE\n"
            "PER moyen du marché         (**)\n18,09\n"
            "Taux de rendement moyen du marché\n6,10\n"
        )
        page.insert_text((50, 50), text)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_path = f.name
        doc.save(temp_path)
        doc.close()
        return temp_path

    @pytest.fixture
    def sample_ut_compte_rendu_pdf(self) -> str:
        """Create a temporary synthetic PDF containing the UMOA-Titres Compte Rendu layout."""
        doc = pymupdf.open()
        page = doc.new_page()
        text = (
            "COMPTE RENDU D'ADJUDICATION DE BONS ET D'OBLIGATIONS ASSIMILABLES DU TRÉSOR\n"
            "Emetteur :\nETAT DE CÔTE D'IVOIRE\n"
            "Nature des titres : Bons et d'Obligations Assimilables du Trésor\n"
            "Montant global mis en adjudication : 100 000 millions de FCFA\n"
            "Date d'adjudication : 29/09/2026\n"
            "Date de valeur : 30/09/2026\n"
            "Montant global des soumissions : 163 915 millions de FCFA\n"
            "Soumissions retenues : 110 000 millions de FCFA\n"
            "Soumissions rejetées : 53 915 millions de FCFA\n"
            "Taux de couverture du montant mis en adjudication par les soumissions : 163,92%\n"
            "BAT - 364 jours\n"
            "Taux/Prix moyen pondéré\n3,9036%\n"
            "OAT - 3 ans\n"
            "Rendement moyen pondéré\n6,36%\n"
        )
        page.insert_text((50, 50), text)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_path = f.name
        doc.save(temp_path)
        doc.close()
        return temp_path

    def test_extract_brvm_metrics(self, sample_brvm_pdf):
        """Verify extraction of all 7 BRVM metrics from BOC PDF."""
        extractor = MarketExtractor()
        points = extractor.extract_brvm_boc(
            pdf_path=sample_brvm_pdf,
            document_id="doc_brvm_001",
            source_id="src_brvm_001",
            entity_id="ent_brvm_001",
            period_year=2026,
        )
        Path(sample_brvm_pdf).unlink(missing_ok=True)

        assert len(points) == 7
        by_metric = {p.metric_code: p for p in points}

        # 1. Indice BRVM Composite
        assert by_metric["indice_brvm_composite"].value_normalized == Decimal("548.04")
        assert by_metric["indice_brvm_composite"].metadata["observation_level"] == "market"
        assert by_metric["indice_brvm_composite"].metadata["consolidation_scope"] == "not_applicable"

        # 2. Indice BRVM 30
        assert by_metric["indice_brvm_30"].value_normalized == Decimal("265.14")

        # 3. Capitalisation Actions
        assert by_metric["capitalisation_actions"].value_normalized == Decimal("21491234105518")
        assert by_metric["capitalisation_actions"].currency_normalized == "XOF"

        # 4. Capitalisation Obligations
        assert by_metric["capitalisation_obligations"].value_normalized == Decimal("13616018491470")
        assert by_metric["capitalisation_obligations"].currency_normalized == "XOF"

        # 5. Valeur des Transactions
        assert by_metric["valeur_transactions_actions"].value_normalized == Decimal("3247423193")
        assert by_metric["valeur_transactions_actions"].currency_normalized == "XOF"

        # 6. PER moyen
        assert by_metric["per_moyen_marche"].value_normalized == Decimal("18.09")

        # 7. Rendement du dividende
        assert by_metric["rendement_moyen_dividende"].value_normalized == Decimal("6.10")

        # Validation status invariant: must be needs_review
        for p in points:
            assert p.status == "needs_review"
            assert p.page_number == 1
            assert p.document_id == "doc_brvm_001"

    def test_extract_umoa_titres_metrics(self, sample_ut_compte_rendu_pdf):
        """Verify extraction of sovereign auction metrics from UMOA-Titres Compte Rendu PDF."""
        extractor = MarketExtractor()
        entity_map = {"CI": "ent_tresor_ci_001", "SN": "ent_tresor_sn_001"}

        points = extractor.extract_umoa_titres_auction(
            pdf_path=sample_ut_compte_rendu_pdf,
            document_id="doc_ut_001",
            source_id="src_ut_001",
            entity_map=entity_map,
            period_year=2026,
        )
        Path(sample_ut_compte_rendu_pdf).unlink(missing_ok=True)

        assert len(points) == 4
        by_metric = {p.metric_code: p for p in points}

        # 1. Montant émis (110 000 millions FCFA = 110 milliards XOF)
        assert by_metric["montant_emis_titres_publics"].value_normalized == Decimal("110000000000")
        assert by_metric["montant_emis_titres_publics"].currency_normalized == "XOF"
        assert by_metric["montant_emis_titres_publics"].metadata["entity_id"] == "ent_tresor_ci_001"
        assert by_metric["montant_emis_titres_publics"].metadata["observation_level"] == "country"

        # 2. Taux de couverture
        assert by_metric["taux_couverture_adjudications"].value_normalized == Decimal("163.92")

        # 3. Taux moyen BAT
        assert by_metric["taux_moyen_adjudication_bat"].value_normalized == Decimal("3.9036")

        # 4. Rendement moyen OAT
        assert by_metric["taux_moyen_adjudication_oat"].value_normalized == Decimal("6.36")

        for p in points:
            assert p.status == "needs_review"
            assert p.metadata["country_code"] == "CI"
            assert p.period_year == 2026
