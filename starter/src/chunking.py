"""Fixed-size and structure-aware chunking."""
from __future__ import annotations

import re

from .models import Chunk, DocumentPage

# Heading-like lines used by the structure-aware chunker to start a new chunk.
_HEADING_RE = re.compile(
    r"^(?:CHƯƠNG|PHẦN|KẾT LUẬN|TÀI LIỆU THAM KHẢO)\b"
    r"|^\d+(?:\.\d+)+\s"  # e.g. "1.1", "2.5.2", "3.5.3.1"
)


def _looks_like_heading(text: str) -> bool:
    """Return True when a block looks like a chapter/section heading."""
    return bool(text) and bool(_HEADING_RE.match(text))


def _make_chunk_id(document_id: str, page: int, index: int) -> str:
    return f"{document_id}-p{page}-c{index}"


def _new_chunk(page: DocumentPage, index: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=_make_chunk_id(page.document_id, page.page, index),
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=dict(page.metadata),  # copy so page metadata flows through
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split page text into overlapping fixed-size windows.

    Text is first flattened (all whitespace -> single space); the sliding
    window stride is ``size - overlap``. Chunks keep the page metadata.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = re.sub(r"\s+", " ", page.text).strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    index = 0
    while start < len(text):
        window = text[start : start + size]
        chunks.append(_new_chunk(page, index, window))
        index += 1
        if start + size >= len(text):
            break
        start += step
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs (and heading lines) into chunks up to ``max_size``.

    Paragraphs are blank-line-separated blocks; a heading line starts a new
    chunk so semantic units are not merged. Oversized paragraphs are hard-split
    at ``max_size`` boundaries. Chunks keep the page metadata.
    """
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    # Blank-line-separated paragraphs; each paragraph's lines joined by spaces.
    paragraphs = [
        re.sub(r"\s+", " ", p).strip()
        for p in re.split(r"\n\s*\n", page.text.strip())
    ]
    paragraphs = [p for p in paragraphs if p]

    # Hard-split oversized paragraphs into <= max_size pieces.
    blocks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_size:
            blocks.append(para)
        else:
            blocks.extend(para[i : i + max_size] for i in range(0, len(para), max_size))

    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    index = 0

    for block in blocks:
        heading = _looks_like_heading(block)
        # A heading (or an oversized current chunk) ends the current chunk.
        if heading and current:
            chunks.append(_new_chunk(page, index, " ".join(current).strip()))
            index += 1
            current = []
            current_len = 0
        # Adding this block would overflow: flush current first.
        separator = 1 if current else 0
        if current_len + len(block) + separator > max_size:
            chunks.append(_new_chunk(page, index, " ".join(current).strip()))
            index += 1
            current = []
            current_len = 0
        current.append(block)
        current_len += len(block) + (1 if len(current) > 1 else 0)

    if current:
        chunks.append(_new_chunk(page, index, " ".join(current).strip()))
    return chunks
