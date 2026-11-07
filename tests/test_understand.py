import pytest

from complaintlens.llm import LLMOutputError, complete_json
from complaintlens.pipeline.understand import (
    Analysis,
    keyword_categories,
    lexicon_flags,
    understand_stage,
)
from complaintlens.schemas import Category, MessageType, RiskFlag, Urgency
from tests.fakes import FakeLLM

GOOD = {
    "message_type": "complaint",
    "response_required": True,
    "urgency": "24h",
    "categories": ["fare_billing"],
    "severity": 2,
    "risk_flags": [],
    "sentiment": "negative",
    "entities": [{"type": "MONEY", "text": "$18.40"}],
    "summary": "The customer was charged twice for one ride.",
    "customer_goal": "A refund of the duplicate charge.",
}


def test_complete_json_retries_once_with_the_validation_error():
    llm = FakeLLM("{not json", GOOD)
    out = complete_json(llm, "sys", "user", Analysis)
    assert out.categories == [Category.FARE_BILLING]
    assert len(llm.calls) == 2
    assert "invalid" in llm.calls[1][-1]["content"]


def test_complete_json_gives_up_after_two_bad_answers():
    with pytest.raises(LLMOutputError):
        complete_json(FakeLLM("nope", "{}"), "sys", "user", Analysis)


def test_lexicon_flags_are_bilingual():
    assert RiskFlag.SAFETY in lexicon_flags("The driver was drunk and speeding")
    assert RiskFlag.HARASSMENT_DISCRIMINATION in lexicon_flags("Le chauffeur m'a harcelée")
    assert RiskFlag.LEGAL_THREAT in lexicon_flags("Je vais contacter mon avocat")
    assert lexicon_flags("I was charged twice for one ride") == []


def test_keyword_categories_fallback():
    assert keyword_categories("I was charged twice") == [Category.FARE_BILLING]
    assert keyword_categories("hello there") == [Category.OTHER]


def test_understand_stage_uses_llm_and_lexicon_safety_net():
    # The LLM misses the safety issue; the lexicon must add it and force immediate urgency.
    answer = {**GOOD, "categories": ["driver_behaviour"], "urgency": "standard"}
    ctx = {"text_masked": "My driver was drunk and I felt unsafe", "llm": FakeLLM(answer)}
    result = understand_stage(ctx)
    analysis = ctx["analysis"]
    assert result.output["source"] == "llm"
    assert RiskFlag.SAFETY in analysis.risk_flags
    assert analysis.urgency == Urgency.IMMEDIATE
    assert "safety" in result.output["lexicon_flags_added"]


def test_understand_stage_without_llm_falls_back_to_classical_models():
    ctx = {"text_masked": "You charged me twice and nobody answers, this is a scam!"}
    result = understand_stage(ctx)
    assert result.output["source"] == "classical_fallback"
    assert ctx["analysis"].message_type in {MessageType.COMPLAINT, MessageType.REQUEST}
    assert Category.FARE_BILLING in ctx["analysis"].categories
