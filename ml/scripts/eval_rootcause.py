"""Evaluate probable-cause detection in a controlled simulation (RQ5).

Real complaint data has no metadata with a known cause, so causes are planted in synthetic ticket
metadata with realistic marginals (OS, app version, city zone, vehicle, payment, time of day).
For each trial: 5,000 baseline tickets; an incident of n tickets (20 / 50 / 100) in which a share
`purity` (0.5 / 0.8) carries 1-2 planted field values and the rest is normal traffic. Success is
measured as precision@k, with k = number of planted values. Null incidents (no cause) measure false
discoveries. Baseline: the most frequent values inside the incident. 200 trials per condition.

Usage:
    uv run python ml/scripts/eval_rootcause.py --out reports/results/rootcause_simulation.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from complaintlens.rootcause import most_frequent_values, probable_causes

FIELDS = {
    "os": (["ios", "android"], [0.65, 0.35]),
    "app_version": (["5.0", "5.1", "5.2"], [0.2, 0.35, 0.45]),
    "zone": (
        ["plateau", "mile_end", "old_port", "verdun", "griffintown", "airport", "cdn", "rosemont"],
        [0.18, 0.12, 0.15, 0.1, 0.1, 0.12, 0.13, 0.1],
    ),
    "vehicle": (["standard", "xl", "access", "eats_courier"], [0.55, 0.15, 0.05, 0.25]),
    "payment": (["card", "paypal", "cash"], [0.7, 0.2, 0.1]),
    "hour": (["night", "morning", "afternoon", "evening"], [0.2, 0.25, 0.25, 0.3]),
}
SIZES = [20, 50, 100]
PURITIES = [0.5, 0.8]
TRIALS = 200


def ticket(rng: random.Random) -> dict[str, str]:
    return {f: rng.choices(values, weights)[0] for f, (values, weights) in FIELDS.items()}


def trial(rng: random.Random, size: int, purity: float) -> tuple[list, list, set]:
    baseline = [ticket(rng) for _ in range(5000)]
    planted_fields = rng.sample(list(FIELDS), rng.choice([1, 2]))
    planted = {f: rng.choice(FIELDS[f][0]) for f in planted_fields}
    caused = round(size * purity)
    incident = [ticket(rng) | planted for _ in range(caused)] + [
        ticket(rng) for _ in range(size - caused)
    ]
    return incident, baseline, set(planted.items())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(0)
    fields = list(FIELDS)
    results: dict = {"protocol": __doc__.split("Usage:")[0].strip(), "conditions": []}
    for size in SIZES:
        for purity in PURITIES:
            ours, naive = [], []
            for _ in range(TRIALS):
                incident, baseline, planted = trial(rng, size, purity)
                k = len(planted)
                found = [(c.field, c.value) for c in probable_causes(incident, baseline, fields)]
                ours.append(len(set(found[:k]) & planted) / k)
                naive.append(len(set(most_frequent_values(incident, fields)[:k]) & planted) / k)
            row = {
                "incident_size": size,
                "purity": purity,
                "precision_at_k_ours": round(float(np.mean(ours)), 3),
                "precision_at_k_most_frequent": round(float(np.mean(naive)), 3),
            }
            results["conditions"].append(row)
            print(row)
    nulls = 0
    for _ in range(TRIALS):
        incident = [ticket(rng) for _ in range(50)]
        baseline = [ticket(rng) for _ in range(5000)]
        nulls += bool(probable_causes(incident, baseline, fields))
    results["null_incidents_with_any_cause"] = round(nulls / TRIALS, 3)
    print("null incidents reporting a cause:", results["null_incidents_with_any_cause"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
