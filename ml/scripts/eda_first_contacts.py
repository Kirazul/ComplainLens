"""Exploratory statistics for a brand's first contacts (output of complaintlens.data.twcs).

Every number goes to a JSON file in reports/results/, so the report can cite it (plan §11).

Usage:
    uv run python ml/scripts/eda_first_contacts.py data/interim/uber_first_contacts.parquet \
        --out reports/results/eda_uber_first_contacts.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl


def describe(df: pl.DataFrame) -> dict:
    words = df["text"].str.split(" ").list.len()
    daily = (
        df.group_by(pl.col("created_at").dt.date().alias("day"))
        .len()
        .sort("day")
        .with_columns(pl.col("day").cast(pl.Utf8))
    )
    delay_min = df["reply_delay_s"].drop_nulls() / 60
    exact_dupes = len(df) - df["text"].str.to_lowercase().n_unique()

    def q(s: pl.Series, p: float) -> float | None:
        v = s.quantile(p)
        return None if v is None else round(float(v), 1)

    return {
        "conversations": len(df),
        "date_min": str(df["created_at"].min()),
        "date_max": str(df["created_at"].max()),
        "share_answered_by_brand": round(float(df["brand_replied"].mean()), 4),
        "customer_tweets_per_contact": df["n_customer_tweets"]
        .value_counts()
        .sort("n_customer_tweets")
        .head(6)
        .to_dicts(),
        "words": {"median": q(words, 0.5), "p90": q(words, 0.9), "max": int(words.max())},
        "reply_delay_minutes": {
            "median": q(delay_min, 0.5),
            "p90": q(delay_min, 0.9),
        },
        "exact_duplicate_texts": exact_dupes,
        "busiest_days": daily.sort("len", descending=True).head(10).to_dicts(),
        "daily_volume": daily.to_dicts(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    stats = describe(pl.read_parquet(args.parquet))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {k: v for k, v in stats.items() if k != "daily_volume"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
