"""Classical baselines on Complaints-on-Twitter 2019 (+ severity), plan §6.3-6.4 and spec §4E.

Protocol (fixed before looking at results):
- Task A: complaint vs. not (3,449 tweets). Task B: severity 1-4 on the 1,232 complaints.
- Stratified 10-fold cross-validation, repeated with 5 shuffle seeds (small data -> CV, spec §10).
  Duplicate tweets (same normalised text) are kept in the same fold (StratifiedGroupKFold), so a
  model is never tested on a tweet it saw in training. ``--no-grouping`` reproduces the leaky
  variant for the ablation.
- All fitted transformations (TF-IDF vocabulary/weights) live inside a sklearn Pipeline, so they are
  fit on the training folds only.
- Default hyperparameters, no tuning on test folds (no nested selection at this stage).
- Text normalisation: URLs -> [URL], @handles -> [USER] (the brand handle would otherwise leak the
  domain). Casing is kept for the char model and lower-cased by TF-IDF for the word model.
- Metrics: macro-F1 (primary; classes are imbalanced), accuracy; quadratic kappa for severity.
  Mean +- std over seeds; bootstrap 95% CI on the seed-0 out-of-fold predictions; paired bootstrap
  test between the two best models.

Usage:
    uv run python ml/scripts/baseline_complaints2019.py \
        --out reports/results/baseline_complaints2019.json
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import FeatureUnion, Pipeline

from complaintlens.data.complaints2019 import load_aligned, text_key
from complaintlens.eval.stats import (
    bootstrap_ci,
    macro_f1,
    paired_bootstrap_test,
    quadratic_kappa,
)

RAW = Path("data/raw/complaints2019")
SEEDS = [0, 1, 2, 3, 4]
N_FOLDS = 10
_URL = re.compile(r"https?://\S+")
_HANDLE = re.compile(r"@\w+")


def normalise(text: str) -> str:
    return _HANDLE.sub("[USER]", _URL.sub("[URL]", text)).strip()


def make_models(seed: int) -> dict[str, Pipeline | DummyClassifier]:
    def lr() -> LogisticRegression:
        return LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)

    word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    char = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True, lowercase=False
    )
    return {
        "majority": DummyClassifier(strategy="most_frequent"),
        "tfidf_word_lr": Pipeline([("tfidf", word), ("clf", lr())]),
        "tfidf_char_lr": Pipeline([("tfidf", char), ("clf", lr())]),
        "tfidf_word+char_lr": Pipeline(
            [
                (
                    "tfidf",
                    FeatureUnion(
                        [
                            (
                                "word",
                                TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                            ),
                            (
                                "char",
                                TfidfVectorizer(
                                    analyzer="char_wb",
                                    ngram_range=(2, 5),
                                    min_df=2,
                                    sublinear_tf=True,
                                    lowercase=False,
                                ),
                            ),
                        ]
                    ),
                ),
                ("clf", lr()),
            ]
        ),
    }


def run_task(
    texts: list[str], y: np.ndarray, groups: list[str], extra_metric: str | None, grouped: bool
) -> dict:
    per_model: dict[str, dict] = {}
    oof_seed0: dict[str, np.ndarray] = {}
    for name in make_models(0):
        scores, accs, extras = [], [], []
        for seed in SEEDS:
            model = make_models(seed)[name]
            if grouped:
                cv = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            else:
                cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            pred = cross_val_predict(
                model,
                np.array(texts, dtype=object),
                y,
                groups=groups if grouped else None,
                cv=cv,
                n_jobs=-1,
            )
            scores.append(macro_f1(y, pred))
            accs.append(accuracy_score(y, pred))
            if extra_metric == "quadratic_kappa":
                extras.append(quadratic_kappa(y, pred))
            if seed == 0:
                oof_seed0[name] = pred
        ci = bootstrap_ci(y, oof_seed0[name], macro_f1, n_resamples=1000, seed=0)
        per_model[name] = {
            "macro_f1_mean": round(float(np.mean(scores)), 4),
            "macro_f1_std": round(float(np.std(scores, ddof=1)), 4),
            "macro_f1_seed0_ci95": [round(ci.low, 4), round(ci.high, 4)],
            "accuracy_mean": round(float(np.mean(accs)), 4),
            **({"quadratic_kappa_mean": round(float(np.mean(extras)), 4)} if extras else {}),
        }
        print(
            f"  {name:20s} macro-F1 {np.mean(scores):.3f} ± {np.std(scores, ddof=1):.3f}  CI {ci}"
        )

    ranked = sorted(per_model, key=lambda m: per_model[m]["macro_f1_mean"], reverse=True)
    best, second = ranked[0], ranked[1]
    test = paired_bootstrap_test(y, oof_seed0[best], oof_seed0[second], macro_f1, 2000, seed=0)
    return {
        "models": per_model,
        "best": best,
        "paired_test_best_vs_second": {
            "a": best,
            "b": second,
            "delta_macro_f1": round(test.delta, 4),
            "p_value_one_sided": round(test.p_value, 4),
        },
    }


def git_commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--no-grouping", action="store_true", help="leaky ablation: duplicates may cross folds"
    )
    args = parser.parse_args()
    grouped = not args.no_grouping

    df = load_aligned(RAW / "complaints-data.csv", RAW / "complaint_severity_data.csv")
    texts = [normalise(t) for t in df["text"].to_list()]
    keys = [text_key(t) for t in df["text"].to_list()]
    n_dupes = len(keys) - len(set(keys))

    print(f"Task A: complaint vs. not ({len(df)} tweets, {n_dupes} duplicate texts)")
    task_a = run_task(texts, df["is_complaint"].to_numpy(), keys, None, grouped)

    comp = df.filter(df["is_complaint"] == 1)
    print(f"Task B: severity 1-4 ({len(comp)} complaints)")
    task_b = run_task(
        [normalise(t) for t in comp["text"].to_list()],
        comp["severity"].to_numpy(),
        [text_key(t) for t in comp["text"].to_list()],
        "quadratic_kappa",
        grouped,
    )

    result = {
        "experiment": "baseline_complaints2019",
        "date_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "protocol": {
            "cv": f"stratified {N_FOLDS}-fold"
            + (", duplicates grouped in one fold" if grouped else ", NOT grouped (leaky ablation)"),
            "seeds": SEEDS,
            "hyperparameters": "defaults (LR class_weight=balanced, max_iter=2000); "
            "word 1-2 grams, char_wb 2-5 grams, min_df=2, sublinear_tf",
            "normalisation": "URLs->[URL], @handles->[USER]",
            "duplicate_texts_in_data": n_dupes,
        },
        "task_a_complaint_vs_not": task_a,
        "task_b_severity_on_complaints": task_b,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
