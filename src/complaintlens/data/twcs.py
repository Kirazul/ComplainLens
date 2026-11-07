"""Prepare the *Customer Support on Twitter* (TWCS) dataset for one brand.

Raw TWCS has one row per tweet. Customers often split one complaint over several tweets, and
conversations are linked through ``in_response_to_tweet_id``. This module turns the raw tweets
into one row per conversation opened by a customer ("first contact"), which is the unit our
system receives in production: what the customer said before any agent answered, plus the
agent's first real reply (used later as a human reference for reply evaluation).

Design decisions (see docs/plan.md §5.3 and §6.1):
- Brand names and handles are masked to ``[COMPANY]`` so models learn the complaint, not the brand
  (otherwise they cannot transfer to our fictional company).
- Other @handles become ``[USER]`` (TWCS already anonymises customers as numbers).
- URLs become ``[URL]``; emojis, casing and accents are kept on purpose (they carry meaning).
- Agent signatures such as ``^AB`` are removed from replies.

Usage:
    python -m complaintlens.data.twcs twcs.csv --brand Uber_Support --out first_contacts.parquet
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import polars as pl

_URL = re.compile(r"https?://\S+")
_HANDLE = re.compile(r"@\w+")
# Agent signatures look like "^AB", "-AB" or "<en dash>AB"; the en dash below is intentional.
_SIGNATURE = re.compile(r"\s*[\^\-–]\s*[A-Z]{1,3}\s*$")  # noqa: RUF001
_SPACES = re.compile(r"[ \t]+")
_BRAND_SUFFIXES = ("_support", "support", "help", "cares", "care")

MAX_JUMP_ROUNDS = 64  # pointer jumping: 64 rounds cover threads up to 2**64 deep


def brand_terms(brand: str) -> list[str]:
    """Return the strings that identify a brand, longest first (e.g. Uber_Support -> Uber)."""
    terms = {brand}
    lowered = brand.lower()
    for suffix in _BRAND_SUFFIXES:
        if lowered.endswith(suffix) and len(brand) > len(suffix):
            terms.add(brand[: -len(suffix)].rstrip("_"))
    return sorted(terms, key=len, reverse=True)


def _brand_pattern(brand: str) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(t) for t in brand_terms(brand))
    return re.compile(rf"(?<!\w)@?(?:{alternatives})", re.IGNORECASE)


def mask_text(text: str, brand: str) -> str:
    """Mask URLs, the brand and other @handles; keep everything else as written."""
    text = _URL.sub("[URL]", text)
    text = _brand_pattern(brand).sub("[COMPANY]", text)
    text = _HANDLE.sub("[USER]", text)
    return "\n".join(_SPACES.sub(" ", line).strip() for line in text.splitlines()).strip()


def strip_agent_signature(text: str) -> str:
    """Remove a trailing agent signature like '^AB' or '-JR'."""
    return _SIGNATURE.sub("", text).strip()


def read_twcs(path: str | Path) -> pl.DataFrame:
    """Read the raw TWCS CSV with explicit types."""
    return pl.read_csv(
        path,
        schema_overrides={
            "tweet_id": pl.Int64,
            "author_id": pl.Utf8,
            "inbound": pl.Boolean,
            "created_at": pl.Utf8,
            "text": pl.Utf8,
            "response_tweet_id": pl.Utf8,
            "in_response_to_tweet_id": pl.Int64,
        },
    )


def _with_roots(tweets: pl.DataFrame) -> pl.DataFrame:
    """Add a ``root`` column: the earliest ancestor of each tweet that exists in the data.

    Uses pointer jumping: every round, each tweet jumps to its ancestor's ancestor, so the
    distance covered doubles and a thread of depth d resolves in about log2(d) rounds. (Real TWCS
    threads exceed 300 replies, so walking one parent per round is too slow.) A parent that is
    missing from the data ends the chain.
    """
    present = tweets.select(
        pl.col("tweet_id").alias("in_response_to_tweet_id"), pl.lit(True).alias("_ok")
    )
    state = (
        tweets.select("tweet_id", "in_response_to_tweet_id")
        .join(present, on="in_response_to_tweet_id", how="left")
        .select(
            "tweet_id",
            pl.when(pl.col("_ok"))
            .then(pl.col("in_response_to_tweet_id"))
            .otherwise(pl.col("tweet_id"))
            .alias("anc"),
        )
    )
    for _ in range(MAX_JUMP_ROUNDS):
        jumped = state.join(state.rename({"tweet_id": "anc", "anc": "_anc2"}), on="anc", how="left")
        if (jumped["_anc2"] == jumped["anc"]).all():
            break
        state = jumped.select("tweet_id", pl.col("_anc2").alias("anc"))
    else:
        raise ValueError("Reply links did not converge (cycle in in_response_to_tweet_id?)")
    return tweets.join(state.select("tweet_id", pl.col("anc").alias("root")), on="tweet_id")


def build_first_contacts(tweets: pl.DataFrame, brand: str) -> pl.DataFrame:
    """One row per conversation a customer opened with ``brand``.

    Columns: conversation_id, created_at, customer_id, text (customer tweets written before the
    brand's first reply, masked, joined by newlines), n_customer_tweets, brand_replied,
    first_reply (masked, signature removed), reply_delay_s.
    """
    df = _with_roots(
        tweets.with_columns(
            pl.col("created_at").str.to_datetime("%a %b %d %H:%M:%S %z %Y", time_zone="UTC")
        )
    )

    roots = df.filter(pl.col("tweet_id") == pl.col("root")).select(
        pl.col("root"),
        pl.col("author_id").alias("customer_id"),
        pl.col("inbound").alias("_root_inbound"),
        pl.col("created_at").alias("_root_time"),
        pl.col("text").alias("_root_text"),
    )
    replies = (
        df.filter(pl.col("author_id") == brand)
        .sort("created_at")
        .group_by("root", maintain_order=True)
        .first()
        .select("root", pl.col("created_at").alias("_reply_time"), pl.col("text").alias("_reply"))
    )
    mention = rf"(?i)@{re.escape(brand)}\b"
    convs = roots.join(replies, on="root", how="left").filter(
        pl.col("_root_inbound")
        & (pl.col("_reply_time").is_not_null() | pl.col("_root_text").str.contains(mention))
    )

    customer_tweets = (
        df.join(convs.select("root", "customer_id", "_reply_time"), on="root", how="inner")
        .filter(
            (pl.col("author_id") == pl.col("customer_id"))
            & pl.col("inbound")
            & (pl.col("_reply_time").is_null() | (pl.col("created_at") < pl.col("_reply_time")))
        )
        .sort("created_at")
        .with_columns(pl.col("text").map_elements(lambda t: mask_text(t, brand), pl.Utf8))
        .group_by("root", maintain_order=True)
        .agg(pl.col("text").str.join("\n"), pl.len().alias("n_customer_tweets"))
    )

    return (
        convs.join(customer_tweets, on="root", how="inner")
        .with_columns(
            pl.col("_reply")
            .map_elements(lambda t: mask_text(strip_agent_signature(t), brand), pl.Utf8)
            .alias("first_reply"),
            pl.col("_reply_time").is_not_null().alias("brand_replied"),
            (pl.col("_reply_time") - pl.col("_root_time"))
            .dt.total_seconds()
            .alias("reply_delay_s"),
        )
        .select(
            pl.col("root").alias("conversation_id"),
            pl.col("_root_time").alias("created_at"),
            "customer_id",
            "text",
            pl.col("n_customer_tweets").cast(pl.Int64),
            "brand_replied",
            "first_reply",
            "reply_delay_s",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("csv", type=Path, help="path to the raw twcs.csv")
    parser.add_argument("--brand", required=True, help="support handle, e.g. Uber_Support")
    parser.add_argument("--out", type=Path, required=True, help="output .parquet path")
    args = parser.parse_args()

    out = build_first_contacts(read_twcs(args.csv), brand=args.brand)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(args.out)
    replied = out["brand_replied"].mean() or 0.0
    print(f"{len(out):,} conversations for @{args.brand} ({replied:.1%} answered) -> {args.out}")


if __name__ == "__main__":
    main()
