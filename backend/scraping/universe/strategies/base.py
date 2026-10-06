"""
Discovery strategy contract (Phase 15).

A strategy is one way of closing gaps (one "round" of the search loop). Strategies are ordered
by source priority: regulator → institution → market infrastructure → public body → federation
→ verified secondary source. A lower-priority strategy never replaces what a higher one found.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.discovery import DiscoveryGap, DiscoveryRun
    from scraping.universe.documents import DocumentRegistrar
    from scraping.universe.http import OfficialFetcher
    from scraping.universe.resolution import EntityResolver


@dataclass
class DiscoveryContext:
    db: AsyncSession
    fetcher: OfficialFetcher
    registrar: DocumentRegistrar
    resolver: EntityResolver
    run: DiscoveryRun
    universe_code: str
    country_codes: tuple[str, ...]
    target_years: list[int]
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    sources_found: int = 0
    new_entities: int = 0
    new_documents: int = 0
    new_document_links: int = 0
    new_observations: int = 0
    targets: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    blocked_entity_ids: set[str] = field(default_factory=set)
    # Reference strategies only: the official list could not be obtained / read consistently.
    reference_unavailable: bool = False
    reference_reason: str | None = None

    @property
    def progress(self) -> bool:
        return any((self.sources_found, self.new_entities, self.new_documents, self.new_document_links,
                    self.new_observations))


class DiscoveryStrategy(ABC):
    code: str
    description: str
    # Source priority of what the strategy looks for (1 = regulator ... 7 = secondary).
    priority: int
    # Gap types this strategy may close (empty for reference strategies).
    handles: frozenset[str] = frozenset()
    # Reference strategies run at the start of every run (detect new official lists).
    always_run: bool = False
    enabled: bool = True
    disabled_reason: str | None = None

    @abstractmethod
    async def run(self, ctx: DiscoveryContext, targets: list[DiscoveryGap]) -> StrategyResult:
        """Execute one round. Must never raise for a source failure: record it in ``errors``."""


class SearchProvider(ABC):
    """Pluggable web-search provider (NOT implemented in this phase by policy).

    A future provider would only return CANDIDATE URLs; every candidate must still pass the
    content verification of the website strategy before becoming VERIFIED, and a search
    result never replaces an official source.
    """

    name: str

    @abstractmethod
    async def search(self, query: str, *, country_code: str | None = None, limit: int = 10) -> list[str]:
        """Return candidate URLs for a query."""
