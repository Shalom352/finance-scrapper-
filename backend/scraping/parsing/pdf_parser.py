"""
UMOA Banking Intelligence — PDF Parser

Extracts page-by-page text, detects images, measures length, normalizes technical layout,
and integrates with PageAnalyzer and DocumentClassifier.

Built on PyMuPDF (fitz) for speed, accuracy, and robust error handling.
"""
import re
import time
from pathlib import Path
from typing import Any

import pymupdf

from app.core.logging import get_logger
from scraping.parsing.base import BaseParser
from scraping.parsing.classifier import DocumentClassifier
from scraping.parsing.exceptions import (
    EmptyPDFError,
    InvalidPDFError,
    PDFParsingError,
    UnsupportedPDFError,
)
from scraping.parsing.models import PageAnalysis, ParsedDocument, ParsedPage
from scraping.parsing.page_analyzer import PageAnalyzer

logger = get_logger(__name__)


def clean_text(raw_text: str) -> str:
    """
    Light technical normalization of extracted text.

    Preserves:
      - Line breaks (normalized to \\n)
      - Numbers, digits, percentages, financial punctuation: -, +, %, /, (, )
      - Accented characters (FR)
      - Tabular whitespace alignment
    Removes:
      - Hostile/corrupted control characters (except \\n and \\t)
    """
    if not raw_text:
        return ""

    # Normalize carriage returns
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove non-printable control characters except tab and newline
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Clean trailing spaces per line while preserving indentation/columns
    lines = [line.rstrip() for line in text.split("\n")]

    # Collapse excessive consecutive blank lines (> 2)
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(line)

    return "\n".join(cleaned).strip()


class PDFParser(BaseParser):
    """Robust PDF document parser using PyMuPDF."""

    def __init__(
        self,
        page_analyzer: PageAnalyzer | None = None,
        document_classifier: DocumentClassifier | None = None,
    ) -> None:
        self.page_analyzer = page_analyzer or PageAnalyzer()
        self.document_classifier = document_classifier or DocumentClassifier()

    async def parse(
        self,
        file_path: str,
        document_id: str | None = None,
        document_title: str | None = None,
        **kwargs: Any,
    ) -> ParsedDocument:
        """
        Open and parse a PDF file into structured, page-by-page extracted content.

        Args:
            file_path: Path to the PDF file.
            document_id: Optional UUID of the Document record for audit provenance.
            document_title: Optional title of the document for classification heuristics.

        Returns:
            ParsedDocument containing pages, analyses, scan status, and classification.
        """
        path = Path(file_path)
        if not path.is_file():
            raise InvalidPDFError(f"PDF file does not exist: {file_path}", file_path=file_path)

        start_time = time.perf_counter()
        logger.info("pdf_parsing_started", file_path=file_path, document_id=document_id)

        try:
            content = path.read_bytes()
            doc = pymupdf.open(stream=content, filetype="pdf")
        except pymupdf.FileDataError as err:
            logger.error("pdf_invalid_file_data", file_path=file_path, error=str(err))
            raise InvalidPDFError(f"Corrupted or invalid PDF: {err}", file_path=file_path) from err
        except OSError as err:
            logger.error("pdf_read_error", file_path=file_path, error=str(err))
            raise PDFParsingError(f"Failed to read file: {err}", file_path=file_path) from err
        except Exception as err:
            logger.error("pdf_open_failed", file_path=file_path, error=str(err))
            raise PDFParsingError(f"Failed to open PDF: {err}", file_path=file_path) from err

        try:
            # Check encryption
            if doc.is_encrypted and doc.needs_pass:
                raise UnsupportedPDFError("Password-protected encrypted PDF is unsupported", file_path=file_path)

            page_count = doc.page_count
            if page_count == 0:
                raise EmptyPDFError("PDF has 0 pages", file_path=file_path)

            pages: list[ParsedPage] = []
            page_analyses: list[PageAnalysis] = []
            statement_candidates: dict[str, list[int]] = {
                "balance_sheet": [],
                "income_statement": [],
                "cash_flow": [],
                "notes": [],
            }
            total_chars = 0
            total_images = 0

            # Process page by page
            for i in range(page_count):
                page_number = i + 1
                page = doc[i]

                # Extract text with technical normalization
                raw_text = page.get_text("text")
                normalized_text = clean_text(raw_text)
                char_count = len(normalized_text)
                word_count = len(normalized_text.split())
                is_empty = char_count == 0

                # Detect images
                images = page.get_images()
                image_count = len(images)
                total_images += image_count
                total_chars += char_count

                # Optional table presence metadata
                table_count = 0
                if hasattr(page, "find_tables"):
                    try:
                        table_count = len(page.find_tables().tables)
                    except Exception:
                        table_count = 0

                parsed_page = ParsedPage(
                    page_number=page_number,
                    text=normalized_text,
                    char_count=char_count,
                    word_count=word_count,
                    is_empty=is_empty,
                    has_images=image_count > 0,
                    image_count=image_count,
                    metadata={"table_count": table_count},
                )
                pages.append(parsed_page)

                # Page-level keyword analysis
                analysis = self.page_analyzer.analyze_page(page_number, normalized_text)
                page_analyses.append(analysis)

                if analysis.is_financial_statement_candidate and analysis.detected_statement_type:
                    st_type = analysis.detected_statement_type
                    if st_type in statement_candidates:
                        statement_candidates[st_type].append(page_number)

            # Determine scan status
            if total_chars == 0 and total_images == 0:
                scan_status = "empty"
            elif (total_chars / max(1, page_count)) < 60 and (total_images > 0 or all(p.char_count < 30 for p in pages)):
                scan_status = "possibly_scanned"
            else:
                scan_status = "text_based"

            # Determine document classification
            classification, confidence = self.document_classifier.classify(
                pages=pages,
                page_analyses=page_analyses,
                document_title=document_title or path.name,
            )

            duration = time.perf_counter() - start_time
            logger.info(
                "pdf_parsing_completed",
                file_path=file_path,
                document_id=document_id,
                page_count=page_count,
                scan_status=scan_status,
                classification=classification,
                duration_seconds=round(duration, 3),
            )

            return ParsedDocument(
                file_path=str(path),
                document_id=document_id,
                page_count=page_count,
                scan_status=scan_status,
                total_char_count=total_chars,
                pages=pages,
                page_analyses=page_analyses,
                document_classification=classification,
                classification_confidence=confidence,
                financial_statement_candidates=statement_candidates,
                metadata={
                    "total_images": total_images,
                    "parse_duration_seconds": round(duration, 3),
                },
            )

        finally:
            doc.close()
