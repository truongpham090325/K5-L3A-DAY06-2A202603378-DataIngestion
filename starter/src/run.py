"""Pipeline entry point: load corpus, build 3 strategies, embed, store, evaluate.

Runs the three data strategies A/B/C on the same corpus, embedding model and
benchmark, then saves full top-3 traces and retrieval metrics. Manual audit
samples (chunk coherence, metadata usefulness, grounding) are reported by the
student in ``report/``; this module computes the automatic retrieval metrics.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .models import Chunk, DocumentPage
from .store import PgVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("day06")

# --------------------------------------------------------------------------- #
# Repository layout (robust regardless of the working directory).
# --------------------------------------------------------------------------- #
SRC_DIR = Path(__file__).resolve().parent       # starter/src
STARTER_DIR = SRC_DIR.parent                    # starter
REPO_ROOT = STARTER_DIR.parent                  # repo root

# --------------------------------------------------------------------------- #
# Corpus configuration (corpus-specific; documented in data/manifest.json).
# --------------------------------------------------------------------------- #
DOCUMENT_ID = "ktpm_e2e_selenium"
SOURCE = "data/KTPM_N11.pdf"
DEFAULT_CORPUS = REPO_ROOT / "data" / "KTPM_N11.pdf"

# (section, first_physical_page, last_physical_page). Pages outside these ranges
# (cover, TOC, references) are excluded from the ingestable corpus.
SECTION_RANGES: list[tuple[str, int, int]] = [
    ("mo_dau", 10, 12),       # PHẦN I. MỞ ĐẦU
    ("chuong_1", 13, 21),     # CHƯƠNG 1. Tổng quan về kiểm thử phần mềm
    ("chuong_2", 22, 32),     # CHƯƠNG 2. Tìm hiểu kỹ thuật kiểm thử End-to-End
    ("chuong_3", 33, 69),     # CHƯƠNG 3. Kết quả thực nghiệm
    ("ket_luan", 70, 70),     # KẾT LUẬN
]
MIN_CONTENT_PAGES = 30

# --------------------------------------------------------------------------- #
# Strategy definitions. A: fixed-size; B: paragraph; C: B + metadata filter.
# B and C differ ONLY by the filter, so their effect can be isolated.
# --------------------------------------------------------------------------- #
STRATEGIES: dict[str, dict[str, Any]] = {
    "A": {"chunking": "fixed_size", "size": 500, "overlap": 50, "use_filter": False},
    "B": {"chunking": "by_paragraph", "max_size": 700, "use_filter": False},
    "C": {"chunking": "by_paragraph", "max_size": 700, "use_filter": True},
}

# OpenAI text-embedding-3-small list price (USD per 1M tokens) for cost estimate.
EMBED_COST_PER_1M_TOKENS = 0.02


def section_for(page: int) -> str | None:
    for name, start, end in SECTION_RANGES:
        if start <= page <= end:
            return name
    return None


def load_config() -> dict[str, Any]:
    """Read configuration from .env (starter/ then repo root) and env vars."""
    for env_file in (STARTER_DIR / ".env", REPO_ROOT / ".env"):
        if env_file.exists():
            load_dotenv(env_file, override=False)

    return {
        "database_url": os.getenv(
            "DATABASE_URL",
            "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab",
        ),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        "corpus_path": Path(os.getenv("CORPUS_PATH", str(DEFAULT_CORPUS))),
        "benchmark_path": Path(
            os.getenv("BENCHMARK_PATH", str(REPO_ROOT / "benchmark" / "benchmark.json"))
        ),
        "manifest_path": Path(
            os.getenv("MANIFEST_PATH", str(REPO_ROOT / "data" / "manifest.json"))
        ),
        "results_dir": Path(os.getenv("RESULTS_DIR", str(STARTER_DIR / "results"))),
    }


def chunk_page(page: DocumentPage, cfg: dict[str, Any]) -> list[Chunk]:
    if cfg["chunking"] == "fixed_size":
        return fixed_size(page, cfg["size"], cfg["overlap"])
    return by_paragraph(page, cfg["max_size"])


def load_benchmark(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = data["questions"]

    n_dev = sum(1 for q in questions if q.get("split") == "dev")
    n_test = sum(1 for q in questions if q.get("split") == "test")
    n_filter = sum(1 for q in questions if q.get("filter"))
    n_filter_test = sum(
        1 for q in questions if q.get("filter") and q.get("split") == "test"
    )

    problems: list[str] = []
    if len(questions) < 20:
        problems.append(f"need >=20 questions, got {len(questions)}")
    if n_dev < 15:
        problems.append(f"need >=15 dev, got {n_dev}")
    if n_test < 5:
        problems.append(f"need >=5 test, got {n_test}")
    if n_filter < 3:
        problems.append(f"need >=3 filter questions, got {n_filter}")
    if n_filter_test < 1:
        problems.append("need >=1 filter question in test split")
    if problems:
        raise SystemExit("Benchmark validation failed: " + "; ".join(problems))

    log.info(
        "Benchmark loaded: %d questions (%d dev / %d test, %d filter questions).",
        len(questions), n_dev, n_test, n_filter,
    )
    return questions


def build_pages(corpus_path: Path) -> tuple[list[DocumentPage], list[DocumentPage]]:
    """Load pages and attach the ``section`` metadata field (the filter field)."""
    all_pages = load_pdf(corpus_path, DOCUMENT_ID, SOURCE)
    for page in all_pages:
        page.metadata["section"] = section_for(page.page)

    content = [p for p in all_pages if p.metadata.get("section") is not None]
    if len(content) < MIN_CONTENT_PAGES:
        raise SystemExit(
            f"Corpus has {len(content)} content pages; need >= {MIN_CONTENT_PAGES}."
        )

    empty = [p.page for p in all_pages if not p.text.strip()]
    low_text = [p.page for p in content if len(p.text) < 100]
    log.info(
        "Corpus: %d physical pages, %d content pages (%s..%s).",
        len(all_pages), len(content), content[0].page, content[-1].page,
    )
    if empty:
        log.warning("Pages with no extracted text: %s", empty)
    if low_text:
        log.info("Content pages with <100 chars (figure/table-heavy): %s", low_text)
    return all_pages, content


def chunk_stats(chunks: list[Chunk]) -> dict[str, Any]:
    lengths = [len(c.text) for c in chunks]
    return {
        "count": len(chunks),
        "total_chars": sum(lengths),
        "min_chars": min(lengths) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
        "mean_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
    }


def main() -> None:
    cfg = load_config()
    cfg["results_dir"].mkdir(parents=True, exist_ok=True)

    if not cfg["corpus_path"].exists():
        raise SystemExit(f"Corpus not found: {cfg['corpus_path']}")
    if not cfg["benchmark_path"].exists():
        raise SystemExit(f"Benchmark not found: {cfg['benchmark_path']}")

    # 1) Corpus + benchmark.
    _all_pages, content_pages = build_pages(cfg["corpus_path"])
    questions = load_benchmark(cfg["benchmark_path"])

    # 2) One real embedding model + one persistent store for all strategies.
    embedder = MyEmbedder(model_name=cfg["embedding_model"])
    log.info(
        "Embedding model: %s (%d dims).", embedder.model_name, embedder.dimensions
    )
    store = PgVectorStore(cfg["database_url"], embedder.dimensions)
    store.create_schema()

    all_traces: list[dict[str, Any]] = []
    strategy_stats: dict[str, dict[str, Any]] = {}

    for strategy, scfg in STRATEGIES.items():
        log.info("=== Strategy %s: %s ===", strategy, scfg)

        # 2a) Chunk.
        chunks: list[Chunk] = []
        for page in content_pages:
            chunks.extend(chunk_page(page, scfg))
        stats = chunk_stats(chunks)
        stats.update({"strategy": strategy, "config": scfg})
        log.info("Chunks: %d (mean %s chars).", stats["count"], stats["mean_chars"])

        # 2b) Embed + store (time it).
        t0 = time.perf_counter()
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.upsert(strategy, chunks, vectors)
        ingest_seconds = time.perf_counter() - t0

        total_chars = stats["total_chars"]
        est_tokens = max(1, total_chars // 4)
        est_cost_usd = est_tokens * EMBED_COST_PER_1M_TOKENS / 1_000_000
        stats.update(
            {
                "ingest_seconds": round(ingest_seconds, 3),
                "estimated_tokens": est_tokens,
                "estimated_cost_usd": round(est_cost_usd, 6),
            }
        )
        log.info(
            "Ingested in %.3fs (~%s tokens, ~$%.6f).",
            ingest_seconds, est_tokens, est_cost_usd,
        )

        # 2c) Run the same questions and keep full top-3 traces.
        for q in questions:
            query_vec = embedder.embed_query(q["question"])
            filters = q.get("filter") if scfg["use_filter"] else None
            hits = store.search(strategy, query_vec, top_k=3, filters=filters)
            trace = evaluate_query(q, hits)
            trace["strategy"] = strategy
            trace["split"] = q.get("split")
            all_traces.append(trace)

        strategy_stats[strategy] = stats

    # 3) Summarize and persist artifacts.
    summary = {
        "embedding_model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "strategies": strategy_stats,
        "metrics": summarize(all_traces),
    }

    traces_path = cfg["results_dir"] / "traces.json"
    summary_path = cfg["results_dir"] / "summary.json"
    traces_path.write_text(
        json.dumps(all_traces, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log.info("Traces -> %s", traces_path)
    log.info("Summary -> %s", summary_path)
    for strategy, m in summary["metrics"].items():
        for split in ("dev", "test"):
            if split in m:
                s = m[split]
                log.info(
                    "[%s/%s] Hit@1 %s | Evidence Hit@3 %s",
                    strategy, split, s["hit@1"], s["evidence_hit@3"],
                )


if __name__ == "__main__":
    main()
