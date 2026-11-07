"""Silver-label Uber messages from the TRAIN or VALIDATION period with the configured LLM.

Never touches the test period (the gold set comes from it). Resumable: rerun the same command after
a quota stop and it continues. The model ID is recorded on every row (spec §4H).

Usage:
    uv run python ml/scripts/silver_label.py --split train --n 5000 --out data/silver/uber_train.jsonl
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_gold_sample import DATA, SPLITS

from complaintlens.data.complaints2019 import text_key
from complaintlens.llm import default_client
from complaintlens.silver import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["train", "validation"], required=True)
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    client = default_client()
    if client is None:
        sys.exit("No LLM configured: set LLM_API_KEY (or LLM_BASE_URL for Ollama) in .env")
    start, end = SPLITS[args.split]
    df = pl.read_parquet(DATA).filter(
        (pl.col("created_at") >= start) & (pl.col("created_at") < end)
    )
    seen: set[str] = set()
    messages = []
    for r in df.iter_rows(named=True):
        key = text_key(r["text"])
        if key and key not in seen:
            seen.add(key)
            messages.append({"id": str(r["conversation_id"]), "text": r["text"]})
    sample = random.Random(2026).sample(messages, min(args.n, len(messages)))
    print(
        f"{args.split}: {len(messages)} unique messages, labelling {len(sample)} with {client.model}"
    )
    print(run(client, sample, args.out, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
