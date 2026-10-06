"""
UMOA Banking Intelligence — HTML Discovery Parser

Robust HTML link and metadata extractor using the standard library HTMLParser.
Zero external parsing dependencies required.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from scraping.common.models import DiscoveredDocument


class LinkExtractor(HTMLParser):
    """HTML parser collecting <a> tags with href and anchor text."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self._current_href = href.strip()
                self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            anchor_text = " ".join(part for part in self._current_text if part)
            self.links.append((self._current_href, anchor_text))
            self._current_href = None
            self._current_text = []


_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_DATE_COMPACT_PATTERN = re.compile(r"(?:^|[^0-9])(19\d{2}|20\d{2})(?:0[1-9]|1[0-2])(?:[0-2][0-9]|3[01])(?:[^0-9]|$)")
_DATE_DOTTED_PATTERN = re.compile(r"(?:[0-2][0-9]|3[01])[\.\-_/](?:0[1-9]|1[0-2])[\.\-_/](19\d{2}|20\d{2})")
_PDF_PATTERN = re.compile(r"\.pdf($|\?|#)", re.IGNORECASE)


def extract_year_from_text(text: str) -> int | None:
    """Extract a 4-digit calendar year (1900-2099) from text, filename or date string."""
    # 1. Standalone 4-digit year
    matches = _YEAR_PATTERN.findall(text)
    if matches:
        return int(matches[-1])

    # 2. Compact date YYYYMMDD (e.g. boc_20260929_2.pdf)
    m_compact = _DATE_COMPACT_PATTERN.findall(text)
    if m_compact:
        return int(m_compact[-1])

    # 3. Dotted/dashed date DD.MM.YYYY or DD-MM-YYYY
    m_dotted = _DATE_DOTTED_PATTERN.findall(text)
    if m_dotted:
        return int(m_dotted[-1])

    return None


def is_document_url(url: str) -> bool:
    """Check if the URL points to a document artifact (e.g. PDF)."""
    parsed = urlparse(url)
    return bool(_PDF_PATTERN.search(parsed.path) or _PDF_PATTERN.search(parsed.query))


def parse_html_documents(
    html_content: str,
    base_page_url: str,
    source_short_name: str,
    document_type: str = "annual_report",
) -> list[DiscoveredDocument]:
    """
    Parse an HTML document to extract downloadable official documents.

    Args:
        html_content: Raw HTML text of the page.
        base_page_url: The URL of the page (for relative resolution).
        source_short_name: Source acronym (e.g. "BCEAO", "CB-UMOA").
        document_type: Category of documents on this page.

    Returns:
        List of unique DiscoveredDocument objects.
    """
    extractor = LinkExtractor()
    extractor.feed(html_content)

    discovered: list[DiscoveredDocument] = []
    seen_urls: set[str] = set()

    for href, text in extractor.links:
        full_url = urljoin(base_page_url, href)
        parsed = urlparse(full_url)

        # Basic security: only accept http and https schemes
        if parsed.scheme not in ("http", "https"):
            continue

        if full_url in seen_urls:
            continue

        if is_document_url(full_url):
            seen_urls.add(full_url)

            # Determine title: fallback to filename if anchor text is missing or generic
            from urllib.parse import unquote
            filename = unquote(parsed.path.split("/")[-1])
            generic_anchors = {
                "télécharger", "telecharger", "download", "pdf", "lire", "consulter", "ici", "lien", "link",
                "télécharger pdf", "telecharger pdf", "télécharger le rapport", "telecharger le rapport",
                "télécharger le document", "telecharger le document",
            }
            clean_anchor = re.sub(r"[,\.:;\-_]+", " ", text.lower()).strip()
            if text and len(text) > 3 and clean_anchor not in generic_anchors and not clean_anchor.startswith("télécharger pdf"):
                title = text
            else:
                clean_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
                title = clean_name.strip() if clean_name else filename

            # Deduce year from text or filename
            period_year = extract_year_from_text(f"{text} {filename}")

            doc = DiscoveredDocument(
                title=title,
                url=full_url,
                source_short_name=source_short_name,
                document_type=document_type,
                source_page_url=base_page_url,
                period_year=period_year,
                period_type="annual",
                language="fr",
                metadata={"anchor_text": text, "filename": filename},
            )
            discovered.append(doc)

    return discovered
