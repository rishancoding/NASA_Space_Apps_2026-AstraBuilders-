"""Keyword (BM25) search over NASA document text in evidence_chunks.jsonl.

Chunks of kind `experiment_plan_text` describe proposed tests; results mark them
so they are never cited as observed outcomes.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from .data import catalog, evidence_chunks

KIND_LABEL = {
    "investigation_metadata": "NASA investigation metadata",
    "document_text": "NASA science document",
    "report_text": "NASA report",
    "experiment_plan_text": "Experiment PLAN (proposed tests, not results)",
}
_STOP = set("a an the of and or in on to for is are was were be by with as at from that this it its how what which does do".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if t not in _STOP and len(t) > 1]


@lru_cache(maxsize=None)
def _index():
    chunks = evidence_chunks()
    names = {r["source_record"]: r["investigation_name"] for _, r in catalog().iterrows()}
    docs = []
    for c in chunks:
        # Prefix the investigation name so "BASS" or "Saffire" queries match its chunks.
        docs.append(_tokens(f"{names.get(c['source_record'], '')} {c['source_record']} {c['text']}"))
    df = Counter(t for d in docs for t in set(d))
    avg = sum(map(len, docs)) / max(len(docs), 1)
    return chunks, docs, df, avg, names


def search(query: str, k: int = 5, source_record: str | None = None, include_plans: bool = True) -> list[dict]:
    chunks, docs, df, avg, names = _index()
    q = _tokens(query)
    n = len(docs)
    scored = []
    for i, d in enumerate(docs):
        c = chunks[i]
        if source_record and c["source_record"] != source_record:
            continue
        if not include_plans and c["kind"] == "experiment_plan_text":
            continue
        tf = Counter(d)
        score = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if score > 0:
            scored.append((score, i))
    scored.sort(reverse=True)
    out = []
    for score, i in scored[:k]:
        c = chunks[i]
        out.append({
            "chunk_id": c["chunk_id"],
            "source_record": c["source_record"],
            "investigation": names.get(c["source_record"], ""),
            "kind": c["kind"],
            "kind_label": KIND_LABEL.get(c["kind"], c["kind"]),
            "source_file": c["source_file"],
            "locator": c["locator"],
            "source_url": c["source_url"],
            "text": c["text"][:1500],
            "score": round(score, 2),
        })
    return out
