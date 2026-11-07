"""Emerging-issue detection (plan §6.7, research question RQ4).

Method: bursty terms -> incidents.
1. Each message contributes each of its terms once (document frequency per time bin).
2. For term t in bin i, the expected count is its *rate* over the previous ``window`` bins times the
   number of messages in bin i. Using rates (not raw counts) means a busy day with the usual mix of
   topics does not alarm; only a change in *what* people write about does.
3. Poisson z-score: z = (count - expected) / sqrt(expected + 1). The +1 keeps new terms (expected
   near 0) from producing infinite scores on a handful of messages; ``min_count`` adds a floor.
4. Terms that burst in the same bin and appear in the same messages are grouped into one incident
   (Jaccard overlap of their message sets), so "krispy", "kreme", "doughnuts" read as one problem.

Baseline (what dashboards usually do): a fixed threshold on raw counts.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from complaintlens.rag.knowledge import tokenize

PLACEHOLDERS = {"company", "user", "url", "email", "phone", "card"}
_NOT_WORD = re.compile(r"^\d+$")


def doc_terms(text: str) -> set[str]:
    """The distinct informative terms of one message."""
    return {
        t
        for t in tokenize(text)
        if len(t) >= 3 and t not in PLACEHOLDERS and not _NOT_WORD.match(t)
    }


@dataclass(frozen=True)
class Alert:
    bin: int
    term: str
    count: int
    expected: float
    z: float


@dataclass
class Incident:
    bin: int
    terms: list[str]
    messages: int
    z_max: float
    alerts: list[Alert] = field(default_factory=list)


def detect_bursts(
    counts: Sequence[Counter[str]],
    n_docs: Sequence[int],
    window: int = 7,
    z_threshold: float = 4.0,
    min_count: int = 10,
    min_lift: float = 2.0,
) -> list[Alert]:
    """Alerts for terms whose share of messages jumps above their recent share."""
    alerts: list[Alert] = []
    for i in range(window, len(counts)):
        past_docs = sum(n_docs[i - window : i])
        if past_docs == 0 or n_docs[i] == 0:
            continue
        past: Counter[str] = Counter()
        for j in range(i - window, i):
            past.update(counts[j])
        for term, c in counts[i].items():
            if c < min_count:
                continue
            expected = past[term] / past_docs * n_docs[i]
            if c < min_lift * expected:
                continue
            z = (c - expected) / math.sqrt(expected + 1.0)
            if z >= z_threshold:
                alerts.append(Alert(i, term, c, round(expected, 2), round(z, 2)))
    return alerts


def count_threshold_alerts(counts: Sequence[Counter[str]], threshold: int) -> list[Alert]:
    """Baseline: alert whenever a term appears in at least ``threshold`` messages in a bin."""
    return [
        Alert(i, term, c, 0.0, 0.0)
        for i, bin_counts in enumerate(counts)
        for term, c in bin_counts.items()
        if c >= threshold
    ]


def group_incidents(
    alerts: Iterable[Alert],
    docs_by_bin: Sequence[set[str]] | dict[int, Sequence[set[str]]],
    min_jaccard: float = 0.3,
) -> list[Incident]:
    """Merge alerts of the same bin whose terms occur in largely the same messages.

    ``docs_by_bin`` is either the term sets of the messages of one bin (when all alerts share a
    bin) or a mapping bin -> list of term sets.
    """
    by_bin: dict[int, list[Alert]] = {}
    for a in alerts:
        by_bin.setdefault(a.bin, []).append(a)
    incidents: list[Incident] = []
    for b, bin_alerts in sorted(by_bin.items()):
        docs = docs_by_bin[b] if isinstance(docs_by_bin, dict) else docs_by_bin
        occurrences = {a.term: {k for k, d in enumerate(docs) if a.term in d} for a in bin_alerts}
        groups: list[list[Alert]] = []
        for a in sorted(bin_alerts, key=lambda x: -x.z):
            for g in groups:
                anchor = occurrences[g[0].term]
                mine = occurrences[a.term]
                union = anchor | mine
                if union and len(anchor & mine) / len(union) >= min_jaccard:
                    g.append(a)
                    break
            else:
                groups.append([a])
        for g in groups:
            msgs = set().union(*(occurrences[a.term] for a in g))
            incidents.append(Incident(b, [a.term for a in g], len(msgs), max(a.z for a in g), g))
    return incidents
