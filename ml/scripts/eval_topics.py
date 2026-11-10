"""Problem discovery on the real @Uber_Support stream: embeddings vs. classical topic models.

Protocol (fixed in advance): Uber first contacts 2017-10-01..2017-12-02; k = 30 clusters for every
method; seeds 0, 1, 2. Every method's clusters are described by the same c-TF-IDF function, so only
the clustering differs. Metrics: NPMI coherence of the top-10 words (computed on the same corpus,
an intrinsic measure), topic diversity, and the share of the largest cluster (a "junk" cluster that
swallows everything is a known failure).

Methods:
- tfidf_kmeans: TF-IDF word vectors + k-means
- lda: latent Dirichlet allocation (counts), each message assigned to its most probable topic
- embedding_kmeans: multilingual MiniLM sentence embeddings (ONNX) + k-means

Usage:
    uv run python ml/scripts/eval_topics.py --out reports/results/topics_uber.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

from complaintlens.rag.retrieval import FastEmbedder
from complaintlens.settings import get_settings
from complaintlens.topics import ctfidf_top_terms, npmi_coherence, topic_diversity
from complaintlens.trends import doc_terms

DATA = Path("data/interim/uber_first_contacts.parquet")
CACHE_DIR = Path("data/interim")
K = 30
SEEDS = [0, 1, 2]


def load() -> list[str]:
    df = pl.read_parquet(DATA).filter(
        (pl.col("created_at") >= datetime(2017, 10, 1, tzinfo=UTC))
        & (pl.col("created_at") < datetime(2017, 12, 3, tzinfo=UTC))
    )
    return df["text"].to_list()


def cache_path(texts: list[str]) -> Path:
    """One cache file per exact list of texts: a changed dataset never reuses old vectors."""
    digest = hashlib.sha256("".join(texts).encode()).hexdigest()[:12]
    return CACHE_DIR / f"uber_minilm_{digest}.npy"


def embeddings(texts: list[str]) -> np.ndarray:
    cache = cache_path(texts)
    if cache.exists():
        return np.load(cache).astype(np.float32)
    s = get_settings()
    embedder = FastEmbedder(s.embedding_model, cache_dir=str(s.models_dir / "fastembed"))
    vectors = embedder.embed_documents(texts)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    np.save(cache, vectors.astype(np.float16))  # half precision: 32 MB instead of 64
    return vectors


def cluster(method: str, texts: list[str], vectors: np.ndarray, seed: int) -> np.ndarray:
    if method == "tfidf_kmeans":
        x = TfidfVectorizer(analyzer=lambda t: list(doc_terms(t)), min_df=5, sublinear_tf=True)
        return KMeans(K, n_init=3, random_state=seed).fit_predict(x.fit_transform(texts))
    if method == "lda":
        counts = CountVectorizer(analyzer=lambda t: list(doc_terms(t)), min_df=5).fit_transform(
            texts
        )
        lda = LatentDirichletAllocation(K, learning_method="online", max_iter=10, random_state=seed)
        return lda.fit_transform(counts).argmax(axis=1)
    if method == "embedding_kmeans":
        return KMeans(K, n_init=3, random_state=seed).fit_predict(vectors)
    raise ValueError(method)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    texts = load()
    terms = [doc_terms(t) for t in texts]
    vectors = embeddings(texts)
    print(f"{len(texts)} messages, embeddings {vectors.shape}")

    results: dict = {
        "protocol": __doc__.split("Usage:")[0].strip(),
        "messages": len(texts),
        "methods": {},
    }
    examples = {}
    for method in ["tfidf_kmeans", "lda", "embedding_kmeans"]:
        npmi, div, largest = [], [], []
        for seed in SEEDS:
            labels = cluster(method, texts, vectors, seed)
            top = ctfidf_top_terms(terms, labels.tolist(), top_n=10)
            topics = [top[c] for c in sorted(top)]
            npmi.append(npmi_coherence(topics, terms))
            div.append(topic_diversity(topics))
            sizes = np.bincount(labels, minlength=K)
            largest.append(float(sizes.max() / sizes.sum()))
            if seed == 0:
                order = np.argsort(-sizes)
                examples[method] = [
                    {"size": int(sizes[c]), "words": top.get(int(c), [])[:6]} for c in order[:12]
                ]
        results["methods"][method] = {
            "npmi_mean": round(float(np.mean(npmi)), 4),
            "npmi_std": round(float(np.std(npmi, ddof=1)), 4),
            "diversity_mean": round(float(np.mean(div)), 3),
            "largest_cluster_share_mean": round(float(np.mean(largest)), 3),
        }
        print(method, results["methods"][method])
    results["largest_topics_seed0"] = examples
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
