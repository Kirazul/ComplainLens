import numpy as np
from sklearn.metrics import f1_score

from complaintlens.eval.stats import bootstrap_ci, macro_f1, paired_bootstrap_test


def test_bootstrap_ci_contains_point_estimate_and_is_reproducible():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    pred = np.where(rng.random(500) < 0.8, y, 1 - y)  # ~80% accurate
    a = bootstrap_ci(y, pred, macro_f1, n_resamples=500, seed=1)
    b = bootstrap_ci(y, pred, macro_f1, n_resamples=500, seed=1)
    assert a == b
    assert a.low < a.estimate < a.high
    assert a.estimate == f1_score(y, pred, average="macro")
    assert 0.03 < a.high - a.low < 0.15  # plausible width for n=500


def test_paired_test_detects_a_real_difference():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 1000)
    good = np.where(rng.random(1000) < 0.9, y, 1 - y)
    bad = np.where(rng.random(1000) < 0.7, y, 1 - y)
    res = paired_bootstrap_test(y, good, bad, macro_f1, n_resamples=1000, seed=0)
    assert res.delta > 0.1
    assert res.p_value < 0.01


def test_paired_test_does_not_invent_a_difference():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 1000)
    a = np.where(rng.random(1000) < 0.8, y, 1 - y)
    res = paired_bootstrap_test(y, a, a.copy(), macro_f1, n_resamples=500, seed=0)
    assert res.delta == 0
    assert res.p_value == 1.0
