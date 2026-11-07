import numpy as np
import pytest

from complaintlens.rag.knowledge import Chunk, Hit, KnowledgeBase
from complaintlens.rag.retrieval import (
    BM25Retriever,
    DenseRetriever,
    HybridRetriever,
    reciprocal_rank_fusion,
)
from complaintlens.settings import get_settings


def chunk(cid: str) -> Chunk:
    return Chunk(cid, "en", cid.split("#")[0], "t", "h", "x")


def test_rrf_rewards_items_ranked_well_by_both_retrievers():
    a, b, c = chunk("A#1"), chunk("B#1"), chunk("C#1")
    fused = reciprocal_rank_fusion(
        [[Hit(a, 9), Hit(b, 5), Hit(c, 1)], [Hit(b, 0.9), Hit(c, 0.8), Hit(a, 0.1)]]
    )
    # b: 1/62 + 1/61 > a: 1/61 + 1/63 > c: 1/63 + 1/62
    assert [h.chunk.id for h in fused] == ["B#1", "A#1", "C#1"]


class KeywordEmbedder:
    """Deterministic toy embedder: one dimension per concept, so paraphrases share a vector."""

    model_name = "toy"
    concepts = (
        ("twice", "two payments", "deux fois", "deux paiements"),
        ("lost", "forgot", "oubli"),
    )

    def _vec(self, text: str) -> np.ndarray:
        t = text.lower()
        return np.array([1.0 if any(w in t for w in c) else 0.0 for c in self.concepts] + [0.01])

    def embed_documents(self, texts):
        return np.array([self._vec(t) for t in texts])

    embed_queries = embed_documents


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(get_settings().help_center_dir)


def test_dense_retriever_finds_a_paraphrase_without_shared_words(kb):
    dense = DenseRetriever(kb, KeywordEmbedder())
    top = dense.search("my bank shows two payments", "en", k=1)[0]
    assert top.chunk.id == "HC-FARES#4"


def test_hybrid_returns_k_results_from_both_sources(kb):
    hybrid = HybridRetriever(BM25Retriever(kb), DenseRetriever(kb, KeywordEmbedder()))
    hits = hybrid.search("charged twice for my ride", "en", k=3)
    assert len(hits) == 3 and hits[0].chunk.id == "HC-FARES#4"
