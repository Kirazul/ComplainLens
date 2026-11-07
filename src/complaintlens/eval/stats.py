"""Uncertainty and significance for classification results (plan §8, spec §10).

- ``bootstrap_ci``: percentile bootstrap 95% confidence interval of a metric, resampling test items.
- ``paired_bootstrap_test``: is system A better than system B *on the same items*? Resamples items
  jointly for both systems (paired), as recommended by Dror et al. (2018), "The Hitchhiker's Guide
  to Testing Statistical Significance in NLP". The p-value is one-sided: H0 says A is not better.

Both take a seed, so every reported interval is reproducible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import cohen_kappa_score, f1_score

Metric = Callable[[np.ndarray, np.ndarray], float]


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(f1_score(y_true, y_pred, average="macro", zero_division=0))


def quadratic_kappa(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Quadratic-weighted Cohen's kappa: for ordinal labels such as severity 1-4."""
    return float(cohen_kappa_score(y_true, y_pred, weights="quadratic"))


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float

    def __str__(self) -> str:
        return f"{self.estimate:.3f} [{self.low:.3f}, {self.high:.3f}]"


@dataclass(frozen=True)
class PairedResult:
    delta: float  # metric(A) - metric(B) on the full test set
    p_value: float  # one-sided, H0: A is not better than B


def bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric: Metric,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Interval:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    rng = np.random.default_rng(seed)
    n = len(y_true)
    scores = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, n)
        scores[i] = metric(y_true[idx], y_pred[idx])
    low, high = np.quantile(scores, [alpha / 2, 1 - alpha / 2])
    return Interval(metric(y_true, y_pred), float(low), float(high))


def paired_bootstrap_test(
    y_true: np.ndarray,
    pred_a: np.ndarray,
    pred_b: np.ndarray,
    metric: Metric,
    n_resamples: int = 1000,
    seed: int = 0,
) -> PairedResult:
    """Paired bootstrap (Berg-Kirkpatrick et al., 2012).

    The p-value is the share of resamples in which A's advantage shrinks by at least the observed
    delta, i.e. falls to zero or below once centred.
    """
    y_true, pred_a, pred_b = map(np.asarray, (y_true, pred_a, pred_b))
    delta = metric(y_true, pred_a) - metric(y_true, pred_b)
    if delta <= 0:
        return PairedResult(delta, 1.0)
    rng = np.random.default_rng(seed)
    n = len(y_true)
    exceed = 0
    for _ in range(n_resamples):
        idx = rng.integers(0, n, n)
        d = metric(y_true[idx], pred_a[idx]) - metric(y_true[idx], pred_b[idx])
        if d >= 2 * delta:  # centred resample: (d - delta) >= delta
            exceed += 1
    return PairedResult(delta, (exceed + 1) / (n_resamples + 1))
