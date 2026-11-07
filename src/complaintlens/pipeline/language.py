"""Stage 3: language identification (plan §6.2).

py3langid (4.6 MB, langid.py retrained) instead of lingua (170 MB): it fits a slim free server and
a slow connection; the plan compares both by text length in the evaluation.

Rule: if the full 97-language model says EN or FR, keep it. Otherwise, very short texts (where any
identifier is unreliable) fall back to the more likely of EN/FR; longer texts are ``other`` and get
routed to a human.
"""

from __future__ import annotations

from functools import cache

from py3langid.langid import MODEL_FILE, LanguageIdentifier

from complaintlens.pipeline.base import Context
from complaintlens.schemas import StageResult

SUPPORTED = ("en", "fr")
SHORT_TEXT_WORDS = 6


@cache
def _identifiers() -> tuple[LanguageIdentifier, LanguageIdentifier]:
    full = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
    restricted = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
    restricted.set_languages(list(SUPPORTED))
    return full, restricted


def detect_language(text: str) -> tuple[str, float]:
    full, restricted = _identifiers()
    lang, prob = full.classify(text)
    if lang in SUPPORTED:
        return lang, float(prob)
    if len(text.split()) < SHORT_TEXT_WORDS:
        lang, prob = restricted.classify(text)
        return lang, float(prob)
    return "other", float(prob)


def language_stage(ctx: Context) -> StageResult:
    lang, prob = detect_language(ctx["text_masked"])
    ctx["language"] = lang
    return StageResult(
        name="language",
        output={"language": lang},
        confidence=round(prob, 3),
        note="unsupported language: will be routed to a human" if lang == "other" else None,
    )


language_stage.stage_name = "language"  # type: ignore[attr-defined]
