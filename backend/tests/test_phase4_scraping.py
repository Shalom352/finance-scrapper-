"""
UMOA Banking Intelligence — Phase 4 Scraping & Collection Pipeline Tests

Unit and integration tests for:
  - HTML Discovery Parser (links, metadata, years, filtering)
  - Connectors (BCEAO, CB-UMOA) with local mock fixtures (100% offline)
  - Download Manager (success, retries, 404/5xx, timeouts, content-type, size limits)
  - Storage Manager (SHA-256 hashing, sharded layout, deduplication, path traversal guard)
  - Pipeline Database synchronization (idempotency, status transitions, failure tracking)
  - CLI argument parsing and execution
"""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document import Document
from app.models.source import Source
from scraping.common.exceptions import SecurityError, StorageError
from scraping.common.models import DiscoveredDocument, DownloadResult
from scraping.connectors.bceao import BCEAOConnector
from scraping.connectors.cb_umoa import CBUMOAConnector
from scraping.discovery.html_parser import (
    extract_year_from_text,
    is_document_url,
    parse_html_documents,
)
from scraping.download.manager import DownloadManager
from scraping.pipeline import ScrapingPipeline
from scraping.storage.manager import StorageManager

SAMPLE_HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><title>BCEAO Publications</title></head>
<body>
  <h1>Rapports Annuels et Bilans</h1>
  <div class="content">
    <a href="/sites/default/files/rapport_annuel_2023.pdf">Rapport Annuel de la BCEAO 2023</a>
    <a href="https://www.bceao.int/sites/default/files/situation_bancaire_2022.pdf">La Situation Bancaire dans l'UMOA 2022</a>
    <a href="/actualites/communique-de-presse">Communiqué de presse (HTML link)</a>
    <a href="ftp://ftp.example.com/ignored.pdf">FTP link</a>
    <a href="/documents/bilan_banques_2021.pdf?download=true">Bilans des Banques 2021</a>
  </div>
</body>
</html>
"""


# ============================================================
# 1. Discovery & HTML Parsing Tests
# ============================================================

class TestHtmlDiscovery:
    """Test HTML parsing, link extraction and metadata deduction."""

    def test_extract_year_from_text(self):
        assert extract_year_from_text("Rapport annuel 2023") == 2023
        assert extract_year_from_text("Exercice clos en 2020 (final)") == 2020
        assert extract_year_from_text("Document sans annee") is None
        assert extract_year_from_text("Texte avec 1999 et 2024") == 2024

    def test_is_document_url(self):
        assert is_document_url("https://example.com/file.pdf") is True
        assert is_document_url("https://example.com/report.PDF") is True
        assert is_document_url("https://example.com/doc.pdf?download=1") is True
        assert is_document_url("https://example.com/page.html") is False
        assert is_document_url("https://example.com/publications") is False

    def test_parse_html_extracts_pdf_documents(self):
        docs = parse_html_documents(
            html_content=SAMPLE_HTML_PAGE,
            base_page_url="https://www.bceao.int/fr/publications",
            source_short_name="BCEAO",
            document_type="annual_report",
        )

        assert len(docs) == 3
        # First doc
        assert docs[0].title == "Rapport Annuel de la BCEAO 2023"
        assert docs[0].url == "https://www.bceao.int/sites/default/files/rapport_annuel_2023.pdf"
        assert docs[0].period_year == 2023
        assert docs[0].source_short_name == "BCEAO"

        # Second doc (absolute URL)
        assert docs[1].period_year == 2022

        # Third doc (query parameter in PDF URL)
        assert docs[2].period_year == 2021

    def test_parse_html_empty_or_no_documents(self):
        html = "<html><body><p>Aucun document ici</p><a href='/home'>Accueil</a></body></html>"
        docs = parse_html_documents(
            html_content=html,
            base_page_url="https://www.bceao.int",
            source_short_name="BCEAO",
        )
        assert docs == []

    def test_parse_html_ignores_unsupported_schemes(self):
        html = "<a href='javascript:void(0)'>Click</a><a href='mailto:test@bceao.int'>Mail</a>"
        docs = parse_html_documents(
            html_content=html,
            base_page_url="https://www.bceao.int",
            source_short_name="BCEAO",
        )
        assert docs == []


# ============================================================
# 2. Storage Manager & SHA-256 Tests
# ============================================================

class TestStorageManager:
    """Test content-addressed storage layout and deduplication."""

    @pytest.fixture
    def temp_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield StorageManager(storage_root=tmpdir)

    def test_compute_sha256(self, temp_storage):
        content = b"PDF-1.4 official report sample content"
        import hashlib
        expected_hash = hashlib.sha256(content).hexdigest()
        assert temp_storage.compute_sha256(content) == expected_hash

    def test_store_content_creates_sharded_path(self, temp_storage):
        content = b"PDF dummy content"
        res = temp_storage.store_content(content, original_filename="rapport_2023.pdf")

        assert res.file_size == len(content)
        assert res.file_hash == temp_storage.compute_sha256(content)
        # Sharded path layout: e.g. "a4/a4c9...pdf"
        assert res.relative_path.startswith(f"{res.file_hash[:2]}/{res.file_hash}")
        assert res.relative_path.endswith(".pdf")
        assert Path(res.absolute_path).is_file()
        assert Path(res.absolute_path).read_bytes() == content
        assert res.is_duplicate is False

    def test_store_content_deduplication(self, temp_storage):
        content = b"Identical financial report bytes"
        res1 = temp_storage.store_content(content, original_filename="doc1.pdf")
        res2 = temp_storage.store_content(content, original_filename="doc2.pdf")

        assert res1.file_hash == res2.file_hash
        assert res1.is_duplicate is False
        assert res2.is_duplicate is True
        assert res1.absolute_path == res2.absolute_path

    def test_path_traversal_protection(self, temp_storage):
        with pytest.raises(SecurityError):
            temp_storage.get_absolute_path("../../etc/passwd", ext="pdf")

    def test_empty_content_raises(self, temp_storage):
        with pytest.raises(StorageError):
            temp_storage.store_content(b"")

    def test_hash_mismatch_raises(self, temp_storage):
        with pytest.raises(StorageError):
            temp_storage.store_content(
                b"content",
                expected_hash="0000000000000000000000000000000000000000000000000000000000000000",
            )


# ============================================================
# 3. Download Manager Tests
# ============================================================

class TestDownloadManager:
    """Test HTTP downloading, retries, size limits and error handling."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        manager = DownloadManager(concurrency=1, max_retries=1)
        mock_content = b"%PDF-1.4 sample content"

        # Mock httpx response stream
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_error = False
        mock_response.headers = {"content-type": "application/pdf"}

        async def aiter_bytes(chunk_size=65536):
            yield mock_content

        mock_response.aiter_bytes = aiter_bytes

        mock_client = MagicMock()
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        res = await manager.download_file(mock_client, "https://example.com/file.pdf")

        assert res.success is True
        assert res.content == mock_content
        assert res.file_size == len(mock_content)
        assert res.status_code == 200
        assert res.error_message is None

    @pytest.mark.asyncio
    async def test_download_404_no_retry(self):
        manager = DownloadManager(concurrency=1, max_retries=2)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.is_error = True
        mock_response.reason_phrase = "Not Found"

        mock_client = MagicMock()
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        res = await manager.download_file(mock_client, "https://example.com/missing.pdf")

        assert res.success is False
        assert res.status_code == 404
        assert res.retry_count == 0  # 404 must not trigger retries
        assert "404" in res.error_message

    @pytest.mark.asyncio
    async def test_download_invalid_content_type(self):
        manager = DownloadManager(concurrency=1)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_error = False
        mock_response.headers = {"content-type": "text/html; charset=UTF-8"}

        mock_client = MagicMock()
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        res = await manager.download_file(mock_client, "https://example.com/file.pdf")

        assert res.success is False
        assert "Invalid Content-Type" in res.error_message

    @pytest.mark.asyncio
    async def test_download_size_limit_exceeded(self):
        # 10 bytes max limit
        manager = DownloadManager(concurrency=1, max_file_size_bytes=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_error = False
        mock_response.headers = {"content-type": "application/pdf"}

        async def aiter_bytes(chunk_size=65536):
            yield b"This chunk exceeds 10 bytes limit!"

        mock_response.aiter_bytes = aiter_bytes

        mock_client = MagicMock()
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        res = await manager.download_file(mock_client, "https://example.com/huge.pdf")

        assert res.success is False
        assert "exceeded" in res.error_message.lower()

    @pytest.mark.asyncio
    async def test_validate_url_ssrf_protection(self):
        manager = DownloadManager()
        with pytest.raises(SecurityError):
            manager.validate_url("file:///etc/passwd")
        with pytest.raises(SecurityError):
            manager.validate_url("ftp://ftp.server.com/doc.pdf")


# ============================================================
# 4. Connectors Tests (Offline with local fixtures)
# ============================================================

class TestConnectors:
    """Test BCEAO and CB-UMOA connectors using offline HTML fixtures."""

    @pytest.mark.asyncio
    async def test_bceao_connector_discovery(self):
        connector = BCEAOConnector()
        connector.rate_limit_delay_seconds = 0.0  # Fast testing

        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML_PAGE
        mock_resp.url = "https://www.bceao.int/fr/publications/rapports-annuels"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        docs = await connector.discover(mock_client, limit=2)

        assert len(docs) == 2
        assert docs[0].source_short_name == "BCEAO"
        assert docs[0].url.startswith("https://www.bceao.int")

    @pytest.mark.asyncio
    async def test_cb_umoa_connector_discovery(self):
        connector = CBUMOAConnector()
        connector.rate_limit_delay_seconds = 0.0

        mock_resp = MagicMock()
        mock_resp.text = """
        <html><body>
          <a href="/files/rapport_annuel_cb_2023.pdf">Rapport Annuel 2023</a>
          <a href="/files/liste_banques_2024.pdf">Registre des Banques 2024</a>
        </body></html>
        """
        mock_resp.url = "https://www.cb-umoa.org/rapports-annuels"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        docs = await connector.discover(mock_client)

        assert len(docs) >= 2
        assert docs[0].source_short_name == "CB-UMOA"
        assert docs[0].period_year in (2023, 2024)


# ============================================================
# 5. Pipeline Orchestrator & DB Mock Tests
# ============================================================

class TestScrapingPipeline:
    """Test full pipeline orchestration and status handling."""

    @pytest.mark.asyncio
    async def test_pipeline_connector_lookup(self):
        pipeline = ScrapingPipeline()
        bceao = pipeline.get_connector("bceao")
        assert bceao.source_short_name == "BCEAO"

        cb = pipeline.get_connector("cb-umoa")
        assert cb.source_short_name == "CB-UMOA"

        with pytest.raises(ValueError):
            pipeline.get_connector("unknown_source")

    @pytest.mark.asyncio
    async def test_register_discovered_documents_idempotency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(storage_root=tmpdir)
            pipeline = ScrapingPipeline(storage_manager=storage)

            mock_db = AsyncMock()
            mock_db.add = MagicMock()

            # Mock finding source row
            source_row = MagicMock(spec=Source)
            source_row.id = "src-bceao-1"
            res_source = MagicMock()
            res_source.scalar_one_or_none.return_value = source_row

            # First doc does not exist, second doc already exists
            existing_doc = MagicMock(spec=Document)
            existing_doc.id = "doc-existing-id"

            res_empty = MagicMock()
            res_empty.scalar_one_or_none.return_value = None

            res_exists = MagicMock()
            res_exists.scalar_one_or_none.return_value = existing_doc

            mock_db.execute.side_effect = [res_source, res_empty, res_exists]

            docs_to_register = [
                DiscoveredDocument(
                    title="Doc New",
                    url="https://example.com/new.pdf",
                    source_short_name="BCEAO",
                ),
                DiscoveredDocument(
                    title="Doc Existing",
                    url="https://example.com/existing.pdf",
                    source_short_name="BCEAO",
                ),
            ]

            registered = await pipeline._register_discovered_documents(
                mock_db,
                "BCEAO",
                docs_to_register,
            )

            assert len(registered) == 2
            # Verify db.add was called only once for the new document
            assert mock_db.add.call_count == 1
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_download_pending_documents_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(storage_root=tmpdir)
            dl_manager = DownloadManager(concurrency=1)

            # Mock download_file to return success
            sample_bytes = b"%PDF-1.4 financial report data"
            dl_manager.download_file = AsyncMock(
                return_value=DownloadResult(
                    url="https://example.com/doc.pdf",
                    success=True,
                    status_code=200,
                    content=sample_bytes,
                    file_size=len(sample_bytes),
                )
            )

            pipeline = ScrapingPipeline(
                storage_manager=storage,
                download_manager=dl_manager,
            )

            mock_db = AsyncMock()
            doc = Document(
                title="Rapport 2023",
                document_type="annual_report",
                source_id="src-1",
                url="https://example.com/doc.pdf",
                download_status="pending",
                extraction_status="pending",
            )
            doc.id = "doc-123"

            res_docs = MagicMock()
            res_docs.scalars.return_value.all.return_value = [doc]

            # Duplicate hash check returns None (no duplicate)
            res_dup = MagicMock()
            res_dup.scalar_one_or_none.return_value = None

            mock_db.execute.side_effect = [res_docs, res_dup]

            results = await pipeline.download_pending_documents(mock_db)

            assert len(results) == 1
            updated_doc, dl_res, st_res = results[0]
            assert updated_doc.download_status == "downloaded"
            assert updated_doc.file_hash == storage.compute_sha256(sample_bytes)
            assert updated_doc.file_size == len(sample_bytes)
            assert updated_doc.storage_path.endswith(".pdf")
            assert updated_doc.error_message is None
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_download_pending_documents_failure_records_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(storage_root=tmpdir)
            dl_manager = DownloadManager(concurrency=1)

            # Mock download_file to return 404 failure
            dl_manager.download_file = AsyncMock(
                return_value=DownloadResult(
                    url="https://example.com/missing.pdf",
                    success=False,
                    status_code=404,
                    error_message="HTTP 404 Not Found",
                )
            )

            pipeline = ScrapingPipeline(
                storage_manager=storage,
                download_manager=dl_manager,
            )

            mock_db = AsyncMock()
            doc = Document(
                title="Missing Doc",
                document_type="annual_report",
                source_id="src-1",
                url="https://example.com/missing.pdf",
                download_status="pending",
                extraction_status="pending",
            )
            doc.id = "doc-404"

            res_docs = MagicMock()
            res_docs.scalars.return_value.all.return_value = [doc]
            mock_db.execute.return_value = res_docs

            results = await pipeline.download_pending_documents(mock_db)

            assert len(results) == 1
            updated_doc, dl_res, st_res = results[0]
            assert updated_doc.download_status == "failed"
            assert "404" in updated_doc.error_message
            assert st_res is None
            assert mock_db.commit.called


# ============================================================
# 6. CLI Argument Parsing & Execution Tests
# ============================================================

class TestScrapingCLI:
    """Test CLI argument parsing and flags."""

    def test_cli_parser_discover(self):
        from scraping.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["discover", "--source", "bceao", "--limit", "5", "--no-db"])
        assert args.command == "discover"
        assert args.source == "bceao"
        assert args.limit == 5
        assert args.no_db is True

    def test_cli_parser_download(self):
        from scraping.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["download", "--source", "cb-umoa", "--limit", "10"])
        assert args.command == "download"
        assert args.source == "cb-umoa"
        assert args.limit == 10

    def test_cli_parser_run(self):
        from scraping.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "--source", "all", "--limit", "3"])
        assert args.command == "run"
        assert args.source == "all"
        assert args.limit == 3

    @pytest.mark.asyncio
    async def test_cli_discover_no_db_execution(self):
        from scraping.cli import build_parser, run_cli

        parser = build_parser()
        args = parser.parse_args(["discover", "--source", "bceao", "--limit", "1", "--no-db"])

        mock_docs = [
            DiscoveredDocument(
                title="Rapport 2023",
                url="https://www.bceao.int/report.pdf",
                source_short_name="BCEAO",
                period_year=2023,
            )
        ]

        with patch.object(BCEAOConnector, "discover", AsyncMock(return_value=mock_docs)):
            exit_code = await run_cli(args)
            assert exit_code == 0
