import random
from collections import Counter

from complaintlens.trends import (
    Alert,
    count_threshold_alerts,
    detect_bursts,
    doc_terms,
    group_incidents,
)


def stream(days=20, per_day=200, seed=0):
    """Background traffic: 'refund' ~5% and 'driver' ~20% of messages, stable over time."""
    rng = random.Random(seed)
    out = []
    for _ in range(days):
        docs = []
        for _ in range(per_day):
            words = ["hello"]
            if rng.random() < 0.05:
                words.append("refund")
            if rng.random() < 0.20:
                words.append("driver")
            docs.append(set(words))
        out.append(docs)
    return out


def test_doc_terms_counts_each_term_once_per_message_and_skips_placeholders():
    assert doc_terms("[COMPANY] the app crashed, crashed again! [URL]") == {
        "app",
        "crashed",
        "again",
    }


def test_injected_burst_is_detected_on_the_right_day_and_term():
    days = stream()
    for _ in range(40):  # day 15: 40 extra messages about 'refund'
        days[15].append({"refund", "hello"})
    alerts = detect_bursts(
        [Counter(t for d in day for t in d) for day in days], [len(d) for d in days]
    )
    hits = [a for a in alerts if a.term == "refund"]
    assert [a.bin for a in hits] == [15]


def test_busy_day_alone_does_not_alarm_because_rates_are_used():
    days = stream()
    days[12] = days[12] * 3  # three times the usual volume, same mix of topics
    alerts = detect_bursts(
        [Counter(t for d in day for t in d) for day in days], [len(d) for d in days]
    )
    assert [a for a in alerts if a.bin == 12] == []
    # The naive baseline fires on raw counts.
    naive = count_threshold_alerts(
        [Counter(t for d in day for t in d) for day in days], threshold=100
    )
    assert any(a.bin == 12 for a in naive)


def test_terms_in_different_but_similar_messages_merge_with_embeddings():
    # Real case (14 Nov 2017): "doughnuts" and "#krispykreme" almost never share a message, but
    # the messages mean the same thing. Word overlap cannot merge them; message embeddings can.
    import numpy as np

    alerts = [
        Alert(bin=0, term="doughnuts", count=50, expected=1.0, z=40.0),
        Alert(bin=0, term="krispykreme", count=50, expected=1.0, z=39.0),
        Alert(bin=0, term="surge", count=30, expected=5.0, z=8.0),
    ]
    docs = [{"doughnuts"}] * 50 + [{"krispykreme"}] * 50 + [{"surge"}] * 30
    promo, pricing = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    vectors = np.array([promo] * 100 + [pricing] * 30)
    words_only = group_incidents(alerts, {0: docs})
    assert len(words_only) == 3
    semantic = group_incidents(alerts, {0: docs}, vectors_by_bin={0: vectors})
    assert sorted(sorted(i.terms) for i in semantic) == [["doughnuts", "krispykreme"], ["surge"]]


def test_cobursting_terms_in_the_same_messages_form_one_incident():
    alerts = [
        Alert(bin=3, term="krispy", count=100, expected=1.0, z=50.0),
        Alert(bin=3, term="doughnuts", count=90, expected=1.0, z=45.0),
        Alert(bin=3, term="surge", count=30, expected=5.0, z=8.0),
    ]
    docs = [{"krispy", "doughnuts"}] * 80 + [{"surge"}] * 30
    incidents = group_incidents(alerts, docs)
    assert sorted(sorted(i.terms) for i in incidents) == [["doughnuts", "krispy"], ["surge"]]
