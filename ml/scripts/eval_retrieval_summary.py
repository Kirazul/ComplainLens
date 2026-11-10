"""Does searching with the LLM's English summary help retrieval? (development set, plan §7)

Observation that motivated it: a polite French message ("Bonjour, j'ai été facturé deux fois...
Merci de corriger") retrieved the wrong sections with dense search on the raw text. Help Center
sections share IDs across languages, so we can search with the LLM's one-line English summary in
the English index and return the same section in the customer's language.

Compared on the 70 development questions (MRR@10, Recall@1/3): dense and BM25 on the raw text,
dense and BM25 on the English summary, and Reciprocal Rank Fusion of raw-text and summary rankings.
Summaries come from the configured LLM and are cached on disk (re-runs are free and identical).

Usage:
    uv run python ml/scripts/eval_retrieval_summary.py --out reports/results/retrieval_summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from complaintlens.llm import complete_json, default_client
from complaintlens.rag.knowledge import Hit, KnowledgeBase
from complaintlens.rag.retrieval import (
    BM25Retriever,
    DenseRetriever,
    FastEmbedder,
    reciprocal_rank_fusion,
)
from complaintlens.settings import get_settings

QUESTIONS = Path("eval/retrieval_questions.jsonl")


class Summary(BaseModel):
    summary: str


SYSTEM = (
    "Rewrite the customer's message as ONE neutral English sentence describing the problem and "
    'what they want, without greetings. Return JSON: {"summary": "..."}'
)


def in_lang(hits: list[Hit], kb: KnowledgeBase, lang: str) -> list[Hit]:
    """Map English hits to the same sections in the customer's language."""
    out = []
    for h in hits:
        chunk = kb.get(h.chunk.id, lang)
        if chunk is not None:
            out.append(Hit(chunk, h.score))
    return out


def rank_of(hits: list[Hit], gold: str) -> int | None:
    ids = [h.chunk.id for h in hits]
    return ids.index(gold) + 1 if gold in ids else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    s = get_settings()
    client = default_client()
    if client is None:
        raise SystemExit("LLM required")
    kb = KnowledgeBase.load(s.help_center_dir)
    embedder = FastEmbedder(s.embedding_model, cache_dir=str(s.models_dir / "fastembed"))
    dense = DenseRetriever(kb, embedder)
    bm25 = BM25Retriever(kb)
    questions = [json.loads(x) for x in QUESTIONS.read_text(encoding="utf-8").splitlines()]

    variants: dict[str, list[float]] = {}
    for q in questions:
        summary = complete_json(client, SYSTEM, q["q"], Summary).summary
        k = 10
        runs = {
            "dense_text": dense.search(q["q"], q["lang"], k),
            "bm25_text": bm25.search(q["q"], q["lang"], k),
            "dense_summary": in_lang(dense.search(summary, "en", k), kb, q["lang"]),
            "bm25_summary": in_lang(bm25.search(summary, "en", k), kb, q["lang"]),
        }
        runs["rrf_dense_text+dense_summary"] = reciprocal_rank_fusion(
            [runs["dense_text"], runs["dense_summary"]]
        )
        runs["rrf_dense_text+dense_summary+bm25_summary"] = reciprocal_rank_fusion(
            [runs["dense_text"], runs["dense_summary"], runs["bm25_summary"]]
        )
        for name, hits in runs.items():
            r = rank_of(hits[:k], q["gold"])
            variants.setdefault(name, []).append(1 / r if r else 0.0)
            variants.setdefault(name + "@1", []).append(1.0 if r == 1 else 0.0)
            variants.setdefault(name + "@3", []).append(1.0 if r and r <= 3 else 0.0)

    results = {
        "questions": len(questions),
        "llm": client.model,
        "variants": {
            name: {
                "mrr@10": round(float(np.mean(variants[name])), 3),
                "recall@1": round(float(np.mean(variants[name + "@1"])), 3),
                "recall@3": round(float(np.mean(variants[name + "@3"])), 3),
            }
            for name in variants
            if "@" not in name
        },
    }
    for name, row in sorted(results["variants"].items(), key=lambda x: -x[1]["mrr@10"]):
        print(f"{name:45s} {row}")
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
