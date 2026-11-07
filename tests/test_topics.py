import math

from complaintlens.topics import ctfidf_top_terms, npmi_coherence, topic_diversity

DOCS = (
    [{"refund", "charged", "twice"}] * 20
    + [{"driver", "rude", "late"}] * 20
    + [{"refund", "driver"}] * 5
)
LABELS = [0] * 20 + [1] * 20 + [1] * 5


def test_ctfidf_describes_each_cluster_by_its_own_words():
    top = ctfidf_top_terms(DOCS, LABELS, top_n=2, min_df=1)
    assert set(top[0]) <= {"charged", "twice", "refund"}
    assert set(top[1]) <= {"rude", "late", "driver"}


def test_npmi_is_one_for_words_that_always_cooccur_and_negative_for_strangers():
    assert math.isclose(npmi_coherence([["charged", "twice"]], DOCS), 1.0)
    assert npmi_coherence([["twice", "rude"]], DOCS) == -1.0


def test_topic_diversity():
    assert topic_diversity([["a", "b"], ["c", "d"]]) == 1.0
    assert topic_diversity([["a", "b"], ["a", "b"]]) == 0.5
