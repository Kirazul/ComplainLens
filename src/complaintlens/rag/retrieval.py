"""Retrievers over the Help Center: sparse (BM25), dense (embeddings), hybrid (RRF). Plan §7.

- Sparse (BM25) catches exact words: amounts, codes, product names.
- Dense (multilingual sentence embeddings) catches paraphrases: "you took the money out twice" ~
  "charged twice", with no word in common.
- Hybrid fuses the two *rankings* with Reciprocal Rank Fusion (Cormack et al., 2009):
      score(d) = sum over retrievers r of 1 / (k + rank_r(d)),  k = 60
  RRF uses ranks, not raw scores, because BM25 scores and cosine similarities live on different
  scales; it has a single, standard parameter.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import numpy as np

from complaintlens.rag.knowledge import Chunk, Hit, KnowledgeBase

RRF_K = 60


class Retriever(Protocol):
    name: str

    def search(self, query: str, lang: str, k: int = 4) -> list[Hit]: ...


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...


EMBED_BATCH = 8  # small batches keep the peak memory low (activations grow with the batch)
# Official int8 ONNX files published with some sentence-transformers models (dynamic
# quantization, AVX2 kernels: any modern x86 server). ~4x less memory than the default export;
# the effect on retrieval is measured in reports/results/retrieval_int8.json.
INT8_FILES = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "onnx/model_quint8_avx2.onnx",
}


def _register_int8(model_name: str) -> str:
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    name = f"{model_name}-int8"
    if all(m.model != name for m in TextEmbedding._list_supported_models()):
        base = next(m for m in TextEmbedding._list_supported_models() if m.model == model_name)
        TextEmbedding.add_custom_model(
            model=name,
            pooling=PoolingType.MEAN,  # as fastembed's built-in entry for these models
            normalization=False,  # we normalise ourselves (cosine similarity)
            sources=ModelSource(hf=model_name),
            dim=base.dim,
            model_file=INT8_FILES[model_name],
        )
    return name


class FastEmbedder:
    """fastembed (ONNX Runtime, no PyTorch) model; handles query/passage prefixes (e.g. e5).

    ``int8``: use the model's official int8 ONNX file when one exists (see INT8_FILES).
    """

    def __init__(self, model_name: str, cache_dir: str | None = None, int8: bool = False) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.quantized = int8 and model_name in INT8_FILES
        load_name = _register_int8(model_name) if self.quantized else model_name
        self._model = TextEmbedding(load_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array(
            list(self._model.passage_embed(texts, batch_size=EMBED_BATCH)), dtype=np.float32
        )

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self._model.query_embed(texts)), dtype=np.float32)


def _normalise(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-12, None)


class BM25Retriever:
    name = "bm25"

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def search(self, query: str, lang: str, k: int = 4) -> list[Hit]:
        return self.kb.search(query, lang, k)


class DenseRetriever:
    def __init__(self, kb: KnowledgeBase, embedder: Embedder) -> None:
        int8 = "+int8" if getattr(embedder, "quantized", False) else ""
        self.name = f"dense:{embedder.model_name}{int8}"
        self.embedder = embedder
        self._index: dict[str, tuple[list[Chunk], np.ndarray]] = {}
        for lang in sorted({c.lang for c in kb.chunks}):
            chunks = [c for c in kb.chunks if c.lang == lang]
            vectors = embedder.embed_documents([c.indexed_text for c in chunks])
            self._index[lang] = (chunks, _normalise(vectors))

    def search(self, query: str, lang: str, k: int = 4) -> list[Hit]:
        chunks, vectors = self._index.get(lang) or self._index["en"]
        q = _normalise(self.embedder.embed_queries([query]))[0]
        sims = vectors @ q
        order = np.argsort(-sims)[:k]
        return [Hit(chunks[i], round(float(sims[i]), 4)) for i in order]


def reciprocal_rank_fusion(rankings: Iterable[list[Hit]], k: int = RRF_K) -> list[Hit]:
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            key = f"{hit.chunk.id}@{hit.chunk.lang}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks[key] = hit.chunk
    ordered = sorted(scores, key=lambda key: -scores[key])
    return [Hit(chunks[key], round(scores[key], 5)) for key in ordered]


def search_with_summary(
    retriever: Retriever,
    kb: KnowledgeBase,
    text: str,
    summary: str | None,
    lang: str,
    k: int = 4,
) -> list[Hit]:
    """Fuse a search on the customer's own words (their language) with a search on the LLM's
    English summary (English index, mapped back to the same sections in the customer's language).

    Development set (reports/results/retrieval_summary.json): MRR@10 0.657 vs 0.613 for the text
    alone (deployed int8 model: 0.643 vs 0.589); it also fixes polite messages whose greetings
    dilute the query.
    """
    by_text = retriever.search(text, lang, 10)
    if not summary:
        return by_text[:k]
    by_summary = []
    for hit in retriever.search(summary, "en", 10):
        chunk = kb.get(hit.chunk.id, lang)
        if chunk is not None:
            by_summary.append(Hit(chunk, hit.score))
    return reciprocal_rank_fusion([by_text, by_summary])[:k]


def build_retriever(kb: KnowledgeBase) -> Retriever:
    """The configured retriever; falls back to BM25 if the embedding model cannot be loaded."""
    import logging

    from complaintlens.settings import get_settings

    s = get_settings()
    bm25 = BM25Retriever(kb)
    if s.retrieval not in ("dense", "hybrid"):
        return bm25
    try:
        embedder = FastEmbedder(
            s.embedding_model,
            cache_dir=str(s.models_dir / "fastembed"),
            int8=s.embedding_int8,
        )
        dense = DenseRetriever(kb, embedder)
        return dense if s.retrieval == "dense" else HybridRetriever(bm25, dense)
    except Exception:
        logging.getLogger(__name__).exception("dense retriever unavailable, using BM25")
        return bm25


class HybridRetriever:
    def __init__(self, sparse: Retriever, dense: Retriever, depth: int = 50) -> None:
        self.name = f"hybrid({sparse.name}+{dense.name})"
        self.sparse, self.dense, self.depth = sparse, dense, depth

    def search(self, query: str, lang: str, k: int = 4) -> list[Hit]:
        fused = reciprocal_rank_fusion(
            [
                self.sparse.search(query, lang, self.depth),
                self.dense.search(query, lang, self.depth),
            ]
        )
        return fused[:k]
