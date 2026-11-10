"""Does int8 quantization of the embedding model hurt retrieval? (deployment check, plan §7)

Same 70 held-out questions as eval_retrieval.py; fastembed's default export of the model
(16-bit weights) against the official int8 ONNX file. Reports MRR@10 / Recall@1 / Recall@3 with
bootstrap CIs, a two-sided paired bootstrap test on the MRR difference, how often both put the
same section first, model size and median query latency.

    uv run python ml/scripts/eval_quantization.py --out reports/results/retrieval_int8.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from eval_retrieval import QUESTIONS, evaluate, summary

from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.rag.retrieval import INT8_FILES, DenseRetriever, FastEmbedder
from complaintlens.settings import get_settings


def paired_two_sided(a: np.ndarray, b: np.ndarray, seed: int = 0, n: int = 5000) -> float:
    """Bootstrap p-value for 'mean(a) != mean(b)' (resampling centred on the null)."""
    diff = a - b
    observed = abs(diff.mean())
    centred = diff - diff.mean()
    rng = np.random.default_rng(seed)
    hits = sum(
        abs(centred[rng.integers(0, len(diff), len(diff))].mean()) >= observed for _ in range(n)
    )
    return (hits + 1) / (n + 1)


def top1(retriever: DenseRetriever, questions: list[dict]) -> list[str]:
    return [retriever.search(q["q"], q["lang"], k=1)[0].chunk.id for q in questions]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    s = get_settings()
    kb = KnowledgeBase.load(s.help_center_dir)
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    langs = [q["lang"] for q in questions]
    cache = str(s.models_dir / "fastembed")

    def run(int8: bool) -> tuple[dict, list[str]]:
        # One model in memory at a time: two ONNX sessions compete for the CPU threads and
        # distort the latencies.
        retriever = DenseRetriever(kb, FastEmbedder(s.embedding_model, cache_dir=cache, int8=int8))
        evaluate(retriever, questions[:3])  # warm-up before timing
        return evaluate(retriever, questions), top1(retriever, questions)

    (res32, first32), (res8, first8) = run(int8=False), run(int8=True)
    default_file = next(Path(cache).glob("models--Qdrant--*/snapshots/*/model_optimized.onnx"))
    pattern = f"models--sentence-transformers--*/snapshots/*/{INT8_FILES[s.embedding_model]}"
    int8_file = next(Path(cache).glob(pattern))

    results = {
        "questions": len(questions),
        "model": s.embedding_model,
        "default": {
            "file": "Qdrant export used by fastembed (16-bit weights)",
            **summary(res32, langs),
            "model_mb": round(default_file.stat().st_size / 1e6),
        },
        "int8": {
            "file": f"{s.embedding_model}/{INT8_FILES[s.embedding_model]} (official)",
            **summary(res8, langs),
            "model_mb": round(int8_file.stat().st_size / 1e6),
        },
        "mrr_delta_int8_minus_default": round(float(res8["rr"].mean() - res32["rr"].mean()), 3),
        "p_two_sided": round(paired_two_sided(res8["rr"], res32["rr"]), 4),
        "same_top1_share": round(float(np.mean(np.array(first32) == np.array(first8))), 3),
    }
    print(json.dumps(results, indent=1))
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
