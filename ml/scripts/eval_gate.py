"""Evaluate the guaranteed automation gate on real labelled data (RQ2).

Task: complaint vs. not (Complaints-on-Twitter 2019, 3,449 expert labels).
For each of 10 seeds: split 60/20/20 into train / calibration / test, with duplicate tweets kept in
one part. Train the TF-IDF word+char logistic regression on train, calibrate the gate on
calibration (alpha in 2/5/10 %, delta = 10 %), and measure on the untouched test part:
automation rate (coverage), error rate among automated messages (selective risk), and how often
that error exceeds alpha (guarantee violations; should be <= delta in the long run).
Baselines: fixed confidence thresholds 0.8 and 0.9 (no guarantee).

Usage:
    uv run python ml/scripts/eval_gate.py --out reports/results/gate_complaints2019.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_complaints2019 import RAW, make_models, normalise

from complaintlens.data.complaints2019 import load_aligned, text_key
from complaintlens.gate import calibrate_selective_threshold, selective_risk

SEEDS = range(10)
ALPHAS = [0.02, 0.05, 0.10]
DELTA = 0.10
FIXED = [0.8, 0.9]


def split(groups: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    idx = np.arange(len(groups))
    outer = GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=seed)
    train, rest = next(outer.split(idx, groups=groups))
    inner = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=seed)
    cal_rel, test_rel = next(inner.split(rest, groups=groups[rest]))
    return train, rest[cal_rel], rest[test_rel]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    df = load_aligned(RAW / "complaints-data.csv", RAW / "complaint_severity_data.csv")
    texts = np.array([normalise(t) for t in df["text"].to_list()], dtype=object)
    y = df["is_complaint"].to_numpy()
    groups = np.array([text_key(t) for t in df["text"].to_list()])

    rows: dict[str, list[tuple[float, float]]] = {f"gate_alpha_{a}": [] for a in ALPHAS}
    rows |= {f"fixed_{t}": [] for t in FIXED}
    refusals = {a: 0 for a in ALPHAS}
    accuracy = []
    for seed in SEEDS:
        train, cal, test = split(groups, seed)
        model = make_models(seed)["tfidf_word+char_lr"].fit(texts[train], y[train])
        p_cal, p_test = model.predict_proba(texts[cal]), model.predict_proba(texts[test])
        conf_cal, conf_test = p_cal.max(1), p_test.max(1)
        ok_cal = p_cal.argmax(1) == y[cal]
        ok_test = p_test.argmax(1) == y[test]
        accuracy.append(float(ok_test.mean()))
        for a in ALPHAS:
            g = calibrate_selective_threshold(conf_cal, ok_cal, alpha=a, delta=DELTA)
            if g.threshold is None:
                refusals[a] += 1
                rows[f"gate_alpha_{a}"].append((0.0, 0.0))
            else:
                rows[f"gate_alpha_{a}"].append(selective_risk(conf_test, ok_test, g.threshold))
        for t in FIXED:
            rows[f"fixed_{t}"].append(selective_risk(conf_test, ok_test, t))

    results = {
        "protocol": __doc__.split("Usage:")[0].strip(),
        "test_accuracy_all_messages": round(float(np.mean(accuracy)), 3),
        "methods": {},
    }
    for name, values in rows.items():
        risks = np.array([r for r, _ in values])
        covs = np.array([c for _, c in values])
        entry = {
            "automation_rate_mean": round(float(covs.mean()), 3),
            "automation_rate_range": [round(float(covs.min()), 3), round(float(covs.max()), 3)],
            "error_among_automated_mean": round(float(risks.mean()), 4),
            "error_among_automated_max": round(float(risks.max()), 4),
        }
        if name.startswith("gate"):
            a = float(name.rsplit("_", 1)[1])
            entry["violations_of_alpha"] = int((risks > a).sum())
            entry["refusals"] = refusals[a]
        results["methods"][name] = entry
        print(f"{name:18s} {entry}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
