import numpy as np

from complaintlens.gate import calibrate_selective_threshold, selective_risk


def synthetic(n, seed):
    """Confidence c ~ U(0.5, 1); error probability (1 - c) / 4, so confident predictions are
    mostly right, but the raw confidence is NOT calibrated (the gate must not rely on it)."""
    rng = np.random.default_rng(seed)
    conf = rng.uniform(0.5, 1.0, n)
    correct = rng.random(n) >= (1 - conf) / 4
    return conf, correct


def test_selective_risk_and_coverage():
    conf = np.array([0.95, 0.9, 0.6, 0.55])
    correct = np.array([True, False, True, True])
    risk, coverage = selective_risk(conf, correct, threshold=0.8)
    assert risk == 0.5 and coverage == 0.5


def test_calibrated_threshold_controls_error_on_new_data():
    alpha, delta = 0.05, 0.1
    violations = refusals = 0
    for seed in range(40):
        cal = synthetic(2000, seed)
        cal_result = calibrate_selective_threshold(*cal, alpha=alpha, delta=delta)
        if cal_result.threshold is None:  # an unlucky sample: refusing is allowed (and safe)
            refusals += 1
            continue
        test_conf, test_correct = synthetic(20000, 1000 + seed)
        risk, coverage = selective_risk(test_conf, test_correct, cal_result.threshold)
        violations += risk > alpha
        assert coverage > 0
    assert refusals <= 4
    # Guarantee: P(risk > alpha) <= delta. Allow sampling slack over 40 repetitions.
    assert violations / 40 <= delta + 0.1


def test_too_little_evidence_means_no_automation():
    # Errors close to alpha everywhere: 2,000 points cannot prove risk <= 5%, so refuse.
    rng = np.random.default_rng(0)
    conf = rng.uniform(0.5, 1.0, 2000)
    correct = rng.random(2000) >= 0.05
    assert calibrate_selective_threshold(conf, correct, alpha=0.05, delta=0.1).threshold is None


def test_bad_model_is_never_automated():
    conf = np.full(500, 0.99)
    correct = np.zeros(500, dtype=bool)  # confidently wrong
    result = calibrate_selective_threshold(conf, correct, alpha=0.05, delta=0.1)
    assert result.threshold is None and result.coverage == 0.0
