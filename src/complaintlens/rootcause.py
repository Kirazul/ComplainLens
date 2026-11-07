"""Probable-cause hypotheses for an incident (plan §6.7, RQ5).

Question: which metadata values (app version, OS, city zone, vehicle, payment method, hour...) are
over-represented among an incident's tickets compared with normal traffic?

For each field = value: a 2x2 table (incident vs. baseline x has value vs. not), the lift
    lift = P(value | incident) / P(value | baseline)
and a one-sided Fisher exact test of over-representation. Many values are tested at once, so the
p-values are corrected with Benjamini-Hochberg (false discovery rate): without it, some values look
significant by chance. Results are *hypotheses*: over-representation is correlation, not proof.

Baseline ranking: the most frequent values inside the incident (what a dashboard shows), which
confuses "common everywhere" (e.g. iOS) with "specific to this incident".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import fisher_exact

Record = Mapping[str, str]


@dataclass(frozen=True)
class Cause:
    field: str
    value: str
    incident_share: float
    baseline_share: float
    lift: float
    p_value: float
    q_value: float  # Benjamini-Hochberg adjusted


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(adjusted, 1.0)
    return out.tolist()


def probable_causes(
    incident: Sequence[Record],
    baseline: Sequence[Record],
    fields: Sequence[str],
    q_max: float = 0.05,
    min_count: int = 3,
) -> list[Cause]:
    """Over-represented field values, significant after FDR correction, sorted by lift."""
    rows: list[tuple[str, str, int, int]] = []
    for f in fields:
        inc = Counter(r[f] for r in incident if f in r)
        base = Counter(r[f] for r in baseline if f in r)
        for value, a in inc.items():
            if a >= min_count:
                rows.append((f, value, a, base.get(value, 0)))
    n_inc, n_base = len(incident), len(baseline)
    p_values = []
    for _, _, a, b in rows:
        table = [[a, n_inc - a], [b, n_base - b]]
        p_values.append(fisher_exact(table, alternative="greater").pvalue)
    q_values = benjamini_hochberg(p_values)
    causes = []
    for (f, value, a, b), p, q in zip(rows, p_values, q_values, strict=True):
        inc_share, base_share = a / n_inc, (b + 0.5) / (n_base + 1)  # +0.5: unseen in baseline
        if q <= q_max:
            causes.append(
                Cause(
                    f,
                    value,
                    round(inc_share, 4),
                    round(b / n_base, 4) if n_base else 0.0,
                    round(inc_share / base_share, 2),
                    float(p),
                    float(q),
                )
            )
    return sorted(causes, key=lambda c: (-c.lift, c.q_value))


def most_frequent_values(
    incident: Sequence[Record], fields: Sequence[str]
) -> list[tuple[str, str]]:
    """Baseline: values ranked by their count inside the incident."""
    counts = Counter((f, r[f]) for r in incident for f in fields if f in r)
    return [fv for fv, _ in counts.most_common()]
