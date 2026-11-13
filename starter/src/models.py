"""Shared data contracts; keep traceability from chunk back to source."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentPage:
    """One physical page of a source document, with traceability metadata."""

    document_id: str
    source: str
    page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable unit; metadata lets us trace back to document/page."""

    chunk_id: str
    document_id: str
    source: str
    page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Question:
    """Benchmark question with gold evidence for retrieval evaluation.

    ``gold_page`` is the physical PDF page (1-based). ``alt_pages`` and
    ``alt_evidence`` accept any documented alternative gold source; a hit is
    credited when a retrieved chunk is on *any* gold page and contains *any*
    gold evidence (see ``evaluation.evaluate_query``).
    """

    id: str
    split: str  # "dev" | "test"
    question: str
    expected_answer: str
    gold_source_id: str
    gold_page: int
    evidence_quote: str
    type: str = "truc_tiep"
    filter: dict[str, Any] | None = None
    alt_pages: list[int] = field(default_factory=list)
    alt_evidence: list[str] = field(default_factory=list)
