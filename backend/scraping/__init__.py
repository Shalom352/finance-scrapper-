"""
UMOA Banking Intelligence — Document Collection & Scraping Pipeline

Provides modular components for:
  - Discovery: BaseDiscoveryEngine, HTML link and document extraction
  - Connectors: BCEAOConnector, CBUMOAConnector
  - Download: DownloadManager with concurrency, retries, and size checks
  - Storage: StorageManager with content-addressed SHA-256 layout
  - Pipeline: ScrapingPipeline orchestrator
"""
from scraping.common.models import DiscoveredDocument, DownloadResult, StorageResult
from scraping.connectors.base import BaseSourceConnector
from scraping.connectors.bceao import BCEAOConnector
from scraping.connectors.cb_umoa import CBUMOAConnector
from scraping.download.manager import DownloadManager
from scraping.pipeline import ScrapingPipeline
from scraping.storage.manager import StorageManager

__all__ = [
    "DiscoveredDocument",
    "DownloadResult",
    "StorageResult",
    "BaseSourceConnector",
    "BCEAOConnector",
    "CBUMOAConnector",
    "DownloadManager",
    "StorageManager",
    "ScrapingPipeline",
]
