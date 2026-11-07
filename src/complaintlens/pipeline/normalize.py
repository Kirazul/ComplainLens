"""Stage 1: normalise the raw message (plan §6.1).

Email bodies contain much more than the customer's new text: the quoted earlier conversation,
signatures and "Sent from my iPhone" lines. Classifying those would mix old and new content, so we
keep only what the customer wrote this time. Casing, punctuation, accents and emojis are kept: they
carry meaning (spec §4C).
"""

from __future__ import annotations

import html
import re
import unicodedata

from complaintlens.pipeline.base import Context
from complaintlens.schemas import Channel, StageResult

# A line that starts the quoted part of a reply: everything from here on is old content.
_QUOTE_HEADERS = [
    re.compile(r"^On .{3,200}wrote:\s*$", re.IGNORECASE),  # Gmail/Apple, English
    re.compile(r"^Le .{3,200}a [ée]crit\s?:\s*$", re.IGNORECASE),  # Gmail/Apple, French
    re.compile(r"^-{2,}\s*(Original Message|Message d'origine)\s*-{2,}\s*$", re.IGNORECASE),
    re.compile(r"^(From|De)\s?:\s.+$", re.IGNORECASE),  # Outlook header block
    re.compile(r"^_{10,}\s*$"),  # Outlook separator line
]
_SIGNATURE_DELIMITER = re.compile(r"^--\s?$")
_MOBILE_SIGNATURE = re.compile(
    r"^(Sent from my|Envoy[ée] de mon|Get Outlook for|Obtenir Outlook pour)\b.*$", re.IGNORECASE
)
_BLANK_RUN = re.compile(r"\n{3,}")


def clean_email_body(body: str) -> str:
    """Keep only the new text the customer wrote in an email."""
    text = unicodedata.normalize("NFKC", body).replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if any(p.match(stripped) for p in _QUOTE_HEADERS) or _SIGNATURE_DELIMITER.match(line):
            break
        if stripped.startswith(">") or _MOBILE_SIGNATURE.match(stripped):
            continue
        kept.append(line.rstrip())
    return _BLANK_RUN.sub("\n\n", "\n".join(kept)).strip()


def html_to_text(markup: str) -> str:
    """Minimal HTML -> text for emails that have no plain-text part."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def normalize_stage(ctx: Context) -> StageResult:
    msg = ctx["message"]
    body = msg.body
    if msg.channel == Channel.EMAIL:
        body = clean_email_body(body)
    else:
        body = unicodedata.normalize("NFKC", body).strip()
    subject = (msg.subject or "").strip()
    # A meaningful subject ("Charged twice") is part of the complaint; "Re:" alone is not.
    meaningful_subject = re.sub(r"^((re|fw|fwd|tr)\s*:\s*)+", "", subject, flags=re.IGNORECASE)
    ctx["text"] = f"{meaningful_subject}\n\n{body}".strip() if meaningful_subject else body
    return StageResult(
        name="normalize",
        output={
            "chars_received": len(msg.body),
            "chars_kept": len(body),
            "subject": meaningful_subject or None,
        },
        note="kept only the customer's new text" if len(body) < len(msg.body) else None,
    )


normalize_stage.stage_name = "normalize"  # type: ignore[attr-defined]
