"""Stage 2: mask personal data before storage and before any external API call (plan §6.1, §14).

v1 handles structured PII with patterns: emails, phone numbers (North American and French
formats) and payment-card numbers validated with the Luhn checksum (so order numbers and amounts
are not masked). Person names need a model: GLiNER-PII is added in a later stage and evaluated with
recall per type, as the plan requires.
"""

from __future__ import annotations

import re

from complaintlens.pipeline.base import Context
from complaintlens.schemas import StageResult

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PHONE = re.compile(
    r"(?<![\w])(?:"
    r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}"  # French: 06 12 34 56 78 / +33 6 12 34 56 78
    r"|(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"  # North America
    r")(?![\w])"
)


def luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def mask_pii(text: str) -> tuple[str, list[dict[str, str]]]:
    """Return the masked text and the list of masked items (type + placeholder, never the value)."""
    found: list[dict[str, str]] = []
    counters: dict[str, int] = {}

    def placeholder(kind: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        tag = f"[{kind}_{counters[kind]}]"
        found.append({"type": kind, "placeholder": tag})
        return tag

    text = _EMAIL.sub(lambda m: placeholder("EMAIL"), text)

    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group())
        return placeholder("CARD") if 13 <= len(digits) <= 19 and luhn_ok(digits) else m.group()

    text = _CARD.sub(card, text)
    text = _PHONE.sub(lambda m: placeholder("PHONE"), text)
    return text, found


def pii_stage(ctx: Context) -> StageResult:
    masked, found = mask_pii(ctx["text"])
    ctx["text_masked"] = masked
    counts: dict[str, int] = {}
    for item in found:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    return StageResult(name="pii_masking", output={"masked": counts, "text": masked})


pii_stage.stage_name = "pii_masking"  # type: ignore[attr-defined]
