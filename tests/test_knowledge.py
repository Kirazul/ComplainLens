import math

from complaintlens.rag.knowledge import BM25, KnowledgeBase, tokenize
from complaintlens.settings import get_settings


def kb() -> KnowledgeBase:
    return KnowledgeBase.load(get_settings().help_center_dir)


def test_tokenize_folds_accents_and_drops_stopwords():
    assert tokenize("J'ai été débité DEUX fois!") == ["j", "ai", "debite", "deux", "fois"]


def test_bm25_prefers_rarer_matching_terms_and_matches_formula():
    bm = BM25([["refund", "card"], ["card", "card", "app"], ["driver"]], k1=1.5, b=0.75)
    s = bm.scores(["refund"])
    assert s[0] > 0 and s[1] == 0 and s[2] == 0
    idf = math.log(1 + (3 - 1 + 0.5) / (1 + 0.5))
    norm = 1 + 1.5 * (1 - 0.75 + 0.75 * 2 / bm.avgdl)
    assert math.isclose(s[0], idf * 1 * 2.5 / norm)


def test_help_center_loads_both_languages_with_matching_ids():
    base = kb()
    en = {c.id for c in base.chunks if c.lang == "en"}
    fr = {c.id for c in base.chunks if c.lang == "fr"}
    assert len(en) >= 30
    assert en == fr, "every English section needs its French counterpart"


def test_search_finds_the_right_policy_in_each_language():
    base = kb()
    assert base.search("I was charged twice for the same ride", "en")[0].chunk.id == "HC-FARES#4"
    assert base.search("J'ai été débité deux fois pour la même course", "fr")[0].chunk.id == (
        "HC-FARES#4"
    )
    assert base.search("I left my phone in the car", "en")[0].chunk.article_id == "HC-LOST"
    assert base.search("my food order never arrived", "en")[0].chunk.article_id == "HC-DELIVERY"
