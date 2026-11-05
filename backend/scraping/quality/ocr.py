"""Bounded Tesseract OCR for scanned financial statements.

OCR is an optional path. It preserves page coordinates and token confidence so every OCR-derived
value can be traced to the original PDF and sent for visual review.
"""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass, field

import pymupdf


@dataclass(frozen=True)
class OCRWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float
    block: int
    paragraph: int
    line: int


@dataclass
class OCRPage:
    text: str
    words: list[OCRWord] = field(default_factory=list)
    mean_confidence: float | None = None


def tesseract_available(executable: str = "tesseract") -> bool:
    return shutil.which(executable) is not None


def recognize_page(
    page: pymupdf.Page,
    *,
    language: str = "fra+eng",
    dpi: int = 200,
    timeout_seconds: int = 45,
    executable: str = "tesseract",
) -> OCRPage:
    """OCR one PDF page and return text, word boxes in PDF points, and confidences."""
    if not tesseract_available(executable):
        raise RuntimeError("Tesseract OCR executable is not installed")
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    completed = subprocess.run(
        [executable, "stdin", "stdout", "-l", language, "--psm", "6", "tsv"],
        input=pixmap.tobytes("png"),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract exited {completed.returncode}: {reason[:400]}")

    scale = 72.0 / dpi
    words: list[OCRWord] = []
    reader = csv.DictReader(io.StringIO(completed.stdout.decode("utf-8", errors="replace")), delimiter="\t")
    for row in reader:
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        try:
            confidence = float(row.get("conf", "-1"))
            left, top = float(row["left"]), float(row["top"])
            width, height = float(row["width"]), float(row["height"])
            block, paragraph, line = (int(row[key]) for key in ("block_num", "par_num", "line_num"))
        except (KeyError, TypeError, ValueError):
            continue
        if confidence < 0:
            continue
        words.append(OCRWord(
            text=row["text"].strip(), x0=left * scale, y0=top * scale,
            x1=(left + width) * scale, y1=(top + height) * scale,
            confidence=max(0.0, min(1.0, confidence / 100.0)),
            block=block, paragraph=paragraph, line=line,
        ))

    grouped: dict[tuple[int, int, int], list[OCRWord]] = {}
    for word in words:
        grouped.setdefault((word.block, word.paragraph, word.line), []).append(word)
    lines = [" ".join(word.text for word in sorted(items, key=lambda word: word.x0))
             for _key, items in sorted(grouped.items(), key=lambda item: min(word.y0 for word in item[1]))]
    mean_confidence = sum(word.confidence for word in words) / len(words) if words else None
    return OCRPage(text="\n".join(lines), words=words, mean_confidence=mean_confidence)
