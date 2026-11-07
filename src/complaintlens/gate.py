"""Automation gate with a statistical guarantee (plan §6.9, research question RQ2).

Goal: automate as many messages as possible while guaranteeing that, among the automated ones,
the error rate is at most ``alpha``, with probability at least ``1 - delta`` over the calibration
data. This is selective risk control in the Learn-then-Test framework (Angelopoulos, Bates, Candès,
Jordan & Lei, 2021), assuming calibration and future messages are exchangeable.

Procedure, on a calibration set the model never trained on:
1. A FIXED grid of confidence thresholds, chosen before seeing data (0.50, 0.51, ..., 0.99).
2. For each threshold, the accepted messages have k errors out of n. Test H0: "error rate > alpha"
   with the exact binomial p-value P(Binomial(n, alpha) <= k).
3. Bonferroni: reject H0 when p <= delta / len(grid). Then, with probability >= 1 - delta, EVERY
   rejected threshold truly has error rate <= alpha, so we may pick the loosest one (the largest
   automation rate).

Why not fixed-sequence testing (walk from the strictest threshold and stop at the first failure)?
At the strictest thresholds only a few dozen messages are accepted; even with zero errors the test
cannot reject (0.95^30 = 0.21), so the walk stops immediately. Skipping those tests and continuing
would silently break the guarantee. Bonferroni over a fixed grid stays valid and works.
If no threshold passes, nothing is automated: the gate refuses rather than guesses.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import binom

GRID = tuple(round(0.50 + 0.01 * i, 2) for i in range(50))  # 0.50 .. 0.99, fixed in advance


@dataclass(frozen=True)
class GateCalibration:
    threshold: float | None  # automate when confidence >= threshold; None = never automate
    alpha: float
    delta: float
    coverage: float  # share of calibration messages that would be automated
    calibration_risk: float  # error rate among them, on calibration data
    n_calibration: int


def selective_risk(conf: np.ndarray, correct: np.ndarray, threshold: float) -> tuple[float, float]:
    """(error rate among accepted, share accepted) for ``confidence >= threshold``."""
    accepted = conf >= threshold
    n = int(accepted.sum())
    if n == 0:
        return 0.0, 0.0
    return float((~correct[accepted]).mean()), n / len(conf)


def calibrate_selective_threshold(
    conf: np.ndarray,
    correct: np.ndarray,
    alpha: float = 0.05,
    delta: float = 0.1,
    grid: tuple[float, ...] = GRID,
) -> GateCalibration:
    conf = np.asarray(conf, dtype=float)
    correct = np.asarray(correct, dtype=bool)
    level = delta / len(grid)
    passed: list[float] = []
    for t in grid:
        accepted = conf >= t
        n = int(accepted.sum())
        if n == 0:
            continue
        errors = int((~correct[accepted]).sum())
        if binom.cdf(errors, n, alpha) <= level:
            passed.append(t)
    if not passed:
        return GateCalibration(None, alpha, delta, 0.0, 0.0, len(conf))
    best = min(passed)  # loosest valid threshold = most automation
    risk, coverage = selective_risk(conf, correct, best)
    return GateCalibration(best, alpha, delta, coverage, risk, len(conf))
