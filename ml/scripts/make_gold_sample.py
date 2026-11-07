"""Draw the English gold-set sample from the TEST period of the real Uber stream (plan §5.2, §8).

Time split, fixed here before any model is trained on Uber data:
  train:      2017-10-01 .. 2017-11-15
  validation: 2017-11-16 .. 2017-11-23
  test:       2017-11-24 .. 2017-12-02
The gold set (human labels) is sampled from the test period only, so no labelled test message can
leak into training or prompt design. Near-duplicates are removed (normalised-text key), messages
shorter than 3 words are kept (they are real traffic) but empty ones are dropped.

The first 50 items (random) form the PILOT, labelled by both annotators to measure agreement before
the full set is split between them.

Usage:
    uv run python ml/scripts/make_gold_sample.py --n 1000 --out eval/gold/gold_en_items.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from complaintlens.data.complaints2019 import text_key

DATA = Path("data/interim/uber_first_contacts.parquet")
SPLITS = {
    "train": (datetime(2017, 10, 1, tzinfo=UTC), datetime(2017, 11, 16, tzinfo=UTC)),
    "validation": (datetime(2017, 11, 16, tzinfo=UTC), datetime(2017, 11, 24, tzinfo=UTC)),
    "test": (datetime(2017, 11, 24, tzinfo=UTC), datetime(2017, 12, 3, tzinfo=UTC)),
}
PILOT = 50
SOURCE = "Customer Support on Twitter (@Uber_Support), CC BY-NC-SA 4.0, brand masked"
SEED = 2026


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    start, end = SPLITS["test"]
    df = pl.read_parquet(DATA).filter(
        (pl.col("created_at") >= start)
        & (pl.col("created_at") < end)
        & (pl.col("text").str.len_chars() > 0)
    )
    seen: set[str] = set()
    rows = []
    for r in df.iter_rows(named=True):
        key = text_key(r["text"])
        if key and key not in seen:
            seen.add(key)
            rows.append(r)
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(args.n, len(rows)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for i, r in enumerate(sample):
            item = {
                "id": f"en-{i + 1:04d}",
                "set": "pilot" if i < PILOT else "gold_en",
                "lang": "en",
                "text": r["text"],
                "conversation_id": r["conversation_id"],
                "created_at": r["created_at"].isoformat(),
                "source": SOURCE,
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"test period: {len(df)} messages, {len(rows)} after dedup")
    print(f"wrote {len(sample)} -> {args.out}")


if __name__ == "__main__":
    main()
