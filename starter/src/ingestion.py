"""Read and normalize source data (PDF) with source traceability."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping paragraph structure.

    Steps:
      1. NFC-normalize so Vietnamese precomposed diacritics are canonical.
      2. Normalize CRLF/CR to LF.
      3. Collapse horizontal whitespace (spaces, tabs, NBSP...) to a single
         space but **preserve newlines** so paragraph-aware chunking can use
         them.
      4. Collapse 3+ consecutive blank lines and strip trailing spaces.

    Note on PDF artifacts: this corpus is a Word->PDF export. ``pypdf`` with
    ``extraction_mode="layout"`` resolves most spurious intra-word spaces; a
    few may remain and are handled at *evidence-matching* time by a de-spaced
    comparison (see ``evaluation._despace``). They do not affect semantic
    embeddings.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Horizontal whitespace -> single space (newlines preserved).
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse long runs of blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing spaces per line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page, keeping its 1-based page number and source.

    Pages whose text could not be read are still returned (with empty text and
    an ``extraction_error`` in metadata) so the caller can log them instead of
    silently dropping content. OCR, when needed, is a separate step that this
    function deliberately does not perform.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    for index, pdf_page in enumerate(reader.pages, start=1):
        raw = ""
        error: str | None = None
        try:
            raw = pdf_page.extract_text(extraction_mode="layout") or ""
        except Exception as exc:  # noqa: BLE001 - record, don't crash the batch
            error = f"{type(exc).__name__}: {exc}"

        text = normalize_text(raw)
        metadata: dict[str, Any] = {}
        if error:
            metadata["extraction_error"] = error
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=index,
                text=text,
                metadata=metadata,
            )
        )
    return pages
