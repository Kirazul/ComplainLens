"""Load *Complaints on Twitter* (Preoțiuc-Pietro et al., ACL 2019) with severity labels
(Jin & Aletras, NAACL 2021).

The two releases describe the same 3,449 tweets **in the same row order**, but the severity release
cannot be joined by ID or by exact text:
- tweet IDs were corrupted by a spreadsheet (``2.26E+16``);
- text was lower-cased and re-tokenised, mentions/links replaced by ``<user>``/``<url>``, HTML
  entities decoded, and words with a curly apostrophe (U+2019) dropped ("they're" -> "they").

We therefore align by row position and *verify* every pair: identical complaint label and a
text-similarity ratio above a threshold. We keep the *original* text, whose casing and punctuation
carry intensity ("NEVER AGAIN!!!").
"""

from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from pathlib import Path

import polars as pl

SEVERITY_NAMES = {
    0: "not_complaint",
    1: "no_explicit_reproach",
    2: "disapproval",
    3: "accusation",
    4: "blame",
}
MIN_SIMILARITY = 0.8
_SPREADSHEET_ERRORS = frozenset({"#NAME?", "#VALUE!", "#REF!", "#N/A", "#DIV/0!"})

_HANDLE = re.compile(r"@\w+")
_URL = re.compile(r"https?://\S+")
_PLACEHOLDER = re.compile(r"<(?:user|url)>")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def text_key(text: str) -> str:
    """Normalise a tweet from either release to a comparable lowercase alphanumeric string."""
    text = html.unescape(text).lower()
    text = _PLACEHOLDER.sub(" ", _URL.sub(" ", _HANDLE.sub(" ", text)))
    return _NON_ALNUM.sub("", text)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, text_key(a), text_key(b), autojunk=False).ratio()


def load_original(path: str | Path) -> pl.DataFrame:
    return pl.read_csv(
        path,
        has_header=False,
        new_columns=["tweet_id", "text", "is_complaint", "domain"],
        schema_overrides={"tweet_id": pl.Utf8, "text": pl.Utf8, "is_complaint": pl.Int8},
    )


def load_severity(path: str | Path) -> pl.DataFrame:
    return pl.read_csv(
        path,
        has_header=False,
        new_columns=["tweet_id_float", "text_lower", "is_complaint", "severity", "domain"],
        schema_overrides={
            "tweet_id_float": pl.Utf8,
            "text_lower": pl.Utf8,
            "is_complaint": pl.Int8,
            "severity": pl.Int8,
        },
    )


def load_aligned(original_path: str | Path, severity_path: str | Path) -> pl.DataFrame:
    """Original tweets with their severity label (0-4) and the alignment similarity.

    Raises ``ValueError`` if the files differ in length or in any complaint label, or if any row's
    text similarity is below ``MIN_SIMILARITY`` (meaning the row order assumption is broken).
    """
    orig = load_original(original_path)
    sev = load_severity(severity_path)
    if len(orig) != len(sev):
        raise ValueError(f"Row counts differ: {len(orig)} vs {len(sev)}")
    if not (orig["is_complaint"] == sev["is_complaint"]).all():
        raise ValueError("Complaint labels differ between releases; row order is not shared")

    # One row of the severity release holds a spreadsheet error ("#NAME?") instead of text, because
    # the tweet looked like a formula. Such rows cannot be text-verified; their similarity is null.
    sims = [
        None if b in _SPREADSHEET_ERRORS else similarity(a, b)
        for a, b in zip(orig["text"], sev["text_lower"], strict=True)
    ]
    worst = min(s for s in sims if s is not None)
    if worst < MIN_SIMILARITY:
        raise ValueError(f"Lowest text similarity {worst:.2f} < {MIN_SIMILARITY}; check alignment")

    return orig.with_columns(
        sev["severity"],
        sev["severity"].replace_strict(SEVERITY_NAMES, return_dtype=pl.Utf8).alias("severity_name"),
        pl.Series("align_similarity", sims, dtype=pl.Float64),
    )
