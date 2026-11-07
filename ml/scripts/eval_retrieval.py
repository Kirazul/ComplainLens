"""Evaluate Help Center retrieval on the held-out question set (RQ3, retrieval part; plan §7).

The 70 questions (eval/retrieval_questions.jsonl, one EN + one FR per section) were written before
any retriever was compared. Each has one gold section. Metrics: Recall@1, Recall@3, MRR@10, with
bootstrap 95% CIs over questions and a paired bootstrap test against BM25. Latency per query is the
median over the set (warm model).

Usage:
    uv run python ml/scripts/eval_retrieval.py \
        --models sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
        --out reports/results/retrieval_helpcenter.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.rag.retrieval import BM25Retriever, DenseRetriever, FastEmbedder, HybridRetriever
from complaintlens.settings import get_settings

QUESTIONS = Path("eval/retrieval_questions.jsonl")


def evaluate(retriever, questions: list[dict]) -> dict:
    rr, r1, r3, ms = [], [], [], []
    for q in questions:
        start = time.perf_counter()
        hits = retriever.search(q["q"], q["lang"], k=10)
        ms.append((time.perf_counter() - start) * 1000)
        ids = [h.chunk.id for h in hits]
        rank = ids.index(q["gold"]) + 1 if q["gold"] in ids else None
        rr.append(1 / rank if rank else 0.0)
        r1.append(1.0 if rank == 1 else 0.0)
        r3.append(1.0 if rank and rank <= 3 else 0.0)
    return {"rr": np.array(rr), "r1": np.array(r1), "r3": np.array(r3), "ms": np.array(ms)}


def ci(values: np.ndarray, seed: int = 0, n: int = 2000) -> list[float]:
    rng = np.random.default_rng(seed)
    means = [values[rng.integers(0, len(values), len(values))].mean() for _ in range(n)]
    return [round(float(np.quantile(means, 0.025)), 3), round(float(np.quantile(means, 0.975)), 3)]


def paired_p(a: np.ndarray, b: np.ndarray, seed: int = 0, n: int = 5000) -> float:
    """One-sided paired bootstrap: is mean(a) > mean(b)?"""
    delta = a.mean() - b.mean()
    if delta <= 0:
        return 1.0
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(n):
        idx = rng.integers(0, len(a), len(a))
        if a[idx].mean() - b[idx].mean() >= 2 * delta:
            exceed += 1
    return (exceed + 1) / (n + 1)


def summary(res: dict, langs: list[str]) -> dict:
    out = {
        "recall@1": round(float(res["r1"].mean()), 3),
        "recall@3": round(float(res["r3"].mean()), 3),
        "mrr@10": round(float(res["rr"].mean()), 3),
        "mrr@10_ci95": ci(res["rr"]),
        "median_ms": round(float(np.median(res["ms"])), 2),
    }
    for lang in sorted(set(langs)):
        mask = np.array([lg == lang for lg in langs])
        out[f"mrr@10_{lang}"] = round(float(res["rr"][mask].mean()), 3)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    s = get_settings()
    kb = KnowledgeBase.load(s.help_center_dir)
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    langs = [q["lang"] for q in questions]

    bm25 = BM25Retriever(kb)
    retrievers = [bm25]
    for model in args.models:
        start = time.perf_counter()
        dense = DenseRetriever(kb, FastEmbedder(model, cache_dir=str(s.models_dir / "fastembed")))
        print(f"indexed {model} in {time.perf_counter() - start:.1f} s")
        retrievers += [dense, HybridRetriever(bm25, dense)]

    raw = {r.name: evaluate(r, questions) for r in retrievers}
    results = {
        "questions": len(questions),
        "retrievers": {name: summary(res, langs) for name, res in raw.items()},
        "paired_vs_bm25_mrr": {
            name: {
                "delta": round(float(res["rr"].mean() - raw["bm25"]["rr"].mean()), 3),
                "p_one_sided": round(paired_p(res["rr"], raw["bm25"]["rr"]), 4),
            }
            for name, res in raw.items()
            if name != "bm25"
        },
        "bm25_failures": [
            {"id": q["id"], "q": q["q"], "gold": q["gold"]}
            for q, rr in zip(questions, raw["bm25"]["rr"], strict=True)
            if rr < 1.0
        ],
    }
    for name, row in results["retrievers"].items():
        print(f"{name:90s} {row}")
    print(json.dumps(results["paired_vs_bm25_mrr"], indent=1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
