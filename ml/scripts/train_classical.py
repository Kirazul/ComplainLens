"""Train the production classical models on all of Complaints-on-Twitter 2019 and save them.

The configuration is exactly the one evaluated in ``baseline_complaints2019.py`` (TF-IDF word 1-2
+ char_wb 2-5 grams, logistic regression, class_weight=balanced); its cross-validated scores are
in reports/results/baseline_complaints2019.json. Training on all labelled data after evaluating with
cross-validation is the standard final step: the CV numbers estimate this model's quality.

Usage:
    uv run python ml/scripts/train_classical.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_complaints2019 import RAW, make_models, normalise

from complaintlens.data.complaints2019 import load_aligned
from complaintlens.settings import get_settings

BEST = "tfidf_word+char_lr"


def main() -> None:
    df = load_aligned(RAW / "complaints-data.csv", RAW / "complaint_severity_data.csv")
    texts = [normalise(t) for t in df["text"].to_list()]

    complaint = make_models(seed=0)[BEST].fit(texts, df["is_complaint"].to_numpy())
    comp = df.filter(df["is_complaint"] == 1)
    severity = make_models(seed=0)[BEST].fit(
        [normalise(t) for t in comp["text"].to_list()], comp["severity"].to_numpy()
    )

    cv = json.loads(Path("reports/results/baseline_complaints2019.json").read_text("utf-8"))
    bundle = {
        "complaint": complaint,
        "severity": severity,
        "meta": {
            "trained_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "sklearn": sklearn.__version__,
            "data": "Complaints-on-Twitter 2019 + severity (3,449 / 1,232 tweets)",
            "config": BEST,
            "cv_macro_f1": {
                "complaint": cv["task_a_complaint_vs_not"]["models"][BEST]["macro_f1_mean"],
                "severity": cv["task_b_severity_on_complaints"]["models"][BEST]["macro_f1_mean"],
            },
        },
    }
    out = get_settings().models_dir / "classical.joblib"
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)
    print(f"saved {out} ({out.stat().st_size / 1e6:.1f} MB): {bundle['meta']['cv_macro_f1']}")


if __name__ == "__main__":
    main()
