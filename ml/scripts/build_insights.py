"""Pre-compute the console's Insights page from the real @Uber_Support stream.

Output (reports/results/insights_uber.json): daily volume, detected incidents per day (the z-score
detector with the threshold chosen in eval_trends.py), and the 30 problem clusters found with
multilingual embeddings + k-means (seed 0, cached embeddings from eval_topics.py) with their
c-TF-IDF labels, sizes and three example messages each.

Usage:
    uv run python ml/scripts/build_insights.py --out reports/results/insights_uber.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_topics import embeddings, load
from eval_trends import load_days

from complaintlens.topics import ctfidf_top_terms
from complaintlens.trends import detect_bursts, doc_terms, group_incidents

TRENDS = Path("reports/results/trends_uber.json")
K = 30


def load_day_labels() -> list[str]:
    """UTC day of each message, in the same order as eval_topics.load()."""
    from datetime import UTC, datetime

    import polars as pl

    df = pl.read_parquet("data/interim/uber_first_contacts.parquet").filter(
        (pl.col("created_at") >= datetime(2017, 10, 1, tzinfo=UTC))
        & (pl.col("created_at") < datetime(2017, 12, 3, tzinfo=UTC))
    )
    return [d.isoformat() for d in df["created_at"].dt.date().to_list()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    days, docs_by_day = load_days()
    texts = load()  # same rows, same order as load_days (identical UTC filters)
    vectors = embeddings(texts)
    day_labels = load_day_labels()
    assert len(day_labels) == len(texts) == len(vectors) == sum(len(d) for d in docs_by_day)
    # Rows of different days can interleave in the file, so index each day's rows explicitly.
    by_day: dict[str, list[int]] = {}
    for i, d in enumerate(day_labels):
        by_day.setdefault(d, []).append(i)
    vectors_by_bin = {i: vectors[by_day.get(day.isoformat(), [])] for i, day in enumerate(days)}
    docs_by_day = [[doc_terms(texts[j]) for j in by_day.get(d.isoformat(), [])] for d in days]

    z = json.loads(TRENDS.read_text(encoding="utf-8"))["methods"]["zscore"]["chosen_param"]
    counts = [Counter(t for d in day for t in d) for day in docs_by_day]
    alerts = detect_bursts(counts, [len(d) for d in docs_by_day], window=7, z_threshold=z)
    words_only = group_incidents(alerts, dict(enumerate(docs_by_day)))
    incidents = group_incidents(alerts, dict(enumerate(docs_by_day)), vectors_by_bin=vectors_by_bin)
    print(f"incidents: {len(words_only)} with word overlap only, {len(incidents)} with embeddings")
    timeline = []
    for i, d in enumerate(days):
        today = sorted((x for x in incidents if x.bin == i), key=lambda x: -x.z_max)[:3]
        timeline.append(
            {
                "day": d.isoformat(),
                "messages": len(docs_by_day[i]),
                "incidents": [
                    {"terms": x.terms[:5], "messages": x.messages, "z": round(x.z_max, 1)}
                    for x in today
                ],
            }
        )

    terms = [doc_terms(t) for t in texts]
    labels = KMeans(K, n_init=3, random_state=0).fit_predict(vectors)
    top = ctfidf_top_terms(terms, labels.tolist(), top_n=8)
    sizes = np.bincount(labels, minlength=K)
    clusters = []
    for c in np.argsort(-sizes):
        members = np.flatnonzero(labels == c)
        examples = [texts[i] for i in members[:: max(1, len(members) // 3)][:3]]
        clusters.append(
            {
                "id": int(c),
                "size": int(sizes[c]),
                "words": top.get(int(c), []),
                "examples": examples,
            }
        )

    out = {
        "source": "Customer Support on Twitter, @Uber_Support first contacts (brand masked)",
        "zscore_threshold": z,
        "timeline": timeline,
        "clusters": clusters,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    busiest = max(timeline, key=lambda d: d["messages"])
    print(f"{len(timeline)} days, {sum(len(d['incidents']) for d in timeline)} incidents shown")
    print("busiest:", busiest)
    print("largest clusters:", [(c["size"], c["words"][:4]) for c in clusters[:5]])
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
