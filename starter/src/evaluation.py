"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _despace(text: str) -> str:
    """Lowercase and strip ALL whitespace for robust evidence matching.

    The corpus keeps a few residual intra-word spaces from the PDF extraction;
    comparing de-spaced text makes evidence matching robust to those artifacts
    without altering the stored chunk text.
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text)).lower()


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep Hit@1 / Hit@3 trace.

    A retrieved chunk is a *hit* when (a) its page is a gold page and (b) its
    text contains the gold evidence (or any documented alternative). Matching is
    de-spaced substring matching. This is an automatic *evidence-retrieval*
    proxy; it does not infer human grounding/coherence labels.
    """
    gold_pages = {int(question["gold_page"])}
    gold_pages.update(int(p) for p in (question.get("alt_pages") or []))

    evidence_quotes = [question["evidence_quote"]]
    evidence_quotes.extend(question.get("alt_evidence") or [])
    evidence_despaced = [_despace(e) for e in evidence_quotes]

    hit_flags: list[bool] = []
    for hit in hits:
        text_d = _despace(hit.get("text", ""))
        page_ok = int(hit.get("page", -1)) in gold_pages
        evidence_ok = any(e and e in text_d for e in evidence_despaced)
        hit_flags.append(page_ok and evidence_ok)

    hit1 = bool(hits) and hit_flags[0]
    hit3 = any(hit_flags[:3])

    # Metadata-usefulness helper: does each top-3 hit respect the requested
    # filter (if any)? Recorded for reporting; the human audit stays separate.
    qfilter = question.get("filter") or {}
    filter_compliant: list[bool] | None = None
    if qfilter:
        filter_compliant = [
            all(str(hit.get(k)) == str(v) for k, v in qfilter.items())
            for hit in hits[:3]
        ]

    return {
        "question_id": question["id"],
        "split": question.get("split"),
        "filter": qfilter,
        "gold_page": question["gold_page"],
        "hits": [
            {
                "chunk_id": h.get("chunk_id"),
                "page": h.get("page"),
                "section": h.get("section"),
                "score": h.get("score"),
                "text": h.get("text"),
                "hit": hit_flags[i] if i < len(hit_flags) else False,
            }
            for i, h in enumerate(hits)
        ],
        "hit@1": hit1,
        "evidence_hit@3": hit3,
        "filter_compliant_top3": filter_compliant,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for trace in traces:
        key = (trace.get("strategy", "?"), trace.get("split", "?"))
        g = grouped.setdefault(key, {"n": 0, "hit1": 0, "hit3": 0})
        g["n"] += 1
        g["hit1"] += int(trace.get("hit@1", False))
        g["hit3"] += int(trace.get("evidence_hit@3", False))

    summary: dict[str, dict[str, Any]] = {}
    for (strategy, split), g in grouped.items():
        n = g["n"]
        summary.setdefault(strategy, {})[split] = {
            "n": n,
            "hit@1": f"{g['hit1']}/{n}",
            "hit@1_rate": round(g["hit1"] / n, 4) if n else 0.0,
            "evidence_hit@3": f"{g['hit3']}/{n}",
            "evidence_hit@3_rate": round(g["hit3"] / n, 4) if n else 0.0,
        }
    return summary
