"""Problem discovery: describe and score clusters of complaints (plan §6.6).

- c-TF-IDF (class-based TF-IDF, as in BERTopic): a word describes a cluster if it is frequent in
  the cluster and rare across clusters:
      score(t, c) = tf(t, c) / |c|  *  log(1 + A / f(t))
  where tf(t, c) counts documents of cluster c containing t, |c| is the cluster size, f(t) is the
  number of documents containing t overall, and A is the average cluster size.
- NPMI coherence (Bouma, 2009; used by Röder et al., 2015): do a topic's top words really occur in
  the same documents? NPMI(a, b) = log(P(a,b) / (P(a) P(b))) / -log P(a,b), averaged over pairs;
  +1 = always together, 0 = independent, -1 = never together.
- Topic diversity (Dieng et al., 2020): share of unique words among all topics' top words; low
  diversity means several topics repeat the same words.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from itertools import combinations


def ctfidf_top_terms(
    doc_terms: Sequence[set[str]], labels: Sequence[int], top_n: int = 10, min_df: int = 5
) -> dict[int, list[str]]:
    df: Counter[str] = Counter(t for d in doc_terms for t in d)
    clusters: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        if label >= 0:  # -1 = noise / unassigned
            clusters.setdefault(label, []).append(i)
    avg_size = sum(len(v) for v in clusters.values()) / max(len(clusters), 1)
    out: dict[int, list[str]] = {}
    for c, members in clusters.items():
        tf: Counter[str] = Counter(t for i in members for t in doc_terms[i])
        scored = {
            t: (n / len(members)) * math.log(1 + avg_size / df[t])
            for t, n in tf.items()
            if df[t] >= min_df
        }
        out[c] = sorted(scored, key=lambda t: -scored[t])[:top_n]
    return out


def npmi_coherence(topics: Sequence[Sequence[str]], doc_terms: Sequence[set[str]]) -> float:
    vocab = {w for t in topics for w in t}
    index: dict[str, set[int]] = {w: set() for w in vocab}
    for i, d in enumerate(doc_terms):
        for w in d & vocab:
            index[w].add(i)
    n = len(doc_terms)
    scores = []
    for topic in topics:
        for a, b in combinations(topic, 2):
            pa, pb = len(index[a]) / n, len(index[b]) / n
            pab = len(index[a] & index[b]) / n
            if pab == 0:
                scores.append(-1.0)
            elif pab == 1:
                scores.append(1.0)
            else:
                scores.append(math.log(pab / (pa * pb)) / -math.log(pab))
    return sum(scores) / len(scores) if scores else 0.0


def topic_diversity(topics: Sequence[Sequence[str]]) -> float:
    words = [w for t in topics for w in t]
    return len(set(words)) / len(words) if words else 0.0
