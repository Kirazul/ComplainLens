import pytest

from complaintlens.pipeline.respond import Draft, priority, respond_stage, route, verify
from complaintlens.pipeline.understand import Analysis
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.schemas import RiskFlag
from complaintlens.settings import get_settings
from complaintlens.store import Customer
from tests.fakes import FakeLLM


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(get_settings().help_center_dir)


def make_analysis(**over):
    base = dict(
        message_type="complaint",
        response_required=True,
        urgency="24h",
        categories=["fare_billing"],
        severity=2,
        risk_flags=[],
        sentiment="negative",
        summary="The customer was charged twice for one ride.",
        customer_goal="Get the duplicate charge refunded.",
    )
    return Analysis(**(base | over))


FACTS = [
    {"id": "F1", "text": "Ride LG-40001 on 2026-11-06 at 21:40, status: completed."},
    {
        "id": "F3",
        "text": "The customer was really charged 2 times; the duplicate amount is $18.40.",
    },
]


def ctx_for(kb, analysis, llm=None, lang="en"):
    return {
        "analysis": analysis,
        "language": lang,
        "ticket_number": "LG-000042",
        "customer": Customer(contact="a@b.c", name="Alex"),
        "facts": FACTS,
        "kb": kb,
        "llm": llm,
        "text_masked": "I was charged twice for my ride last night!",
    }


def test_verify_accepts_supported_numbers_and_rejects_invented_ones(kb):
    hits = kb.search("charged twice refund", "en")
    good = Draft(
        reply="You were charged twice; the duplicate is $18.40 [F3]. Refunds take 5 to 10 "
        "business days [HC-FARES#4].",
        citations=["F3", "HC-FARES#4"],
        confidence=0.9,
    )
    v = verify(good, hits, FACTS)
    assert v["supported"] is True and v["numbers_checked"] == 3  # distinct: 18.40, 5, 10

    bad = good.model_copy(update={"reply": good.reply.replace("5 to 10", "7")})
    v = verify(bad, hits, FACTS)
    assert v["supported"] is False and v["unsupported_numbers"] == [7.0]

    # Known limitation (documented): a wrong number that happens to appear in a cited source
    # ("charged 2 times" in F3) passes number matching; claim-level NLI verification addresses it.
    lucky = good.model_copy(update={"reply": good.reply.replace("5 to 10", "2")})
    assert verify(lucky, hits, FACTS)["supported"] is True

    fake_cite = good.model_copy(update={"citations": ["HC-NOPE#1"]})
    assert verify(fake_cite, hits, FACTS)["unknown_citations"] == ["HC-NOPE#1"]


def test_route_and_priority_are_transparent():
    a = make_analysis(risk_flags=["safety"], urgency="immediate", severity=3)
    assert route(a) == "Safety"
    score, parts = priority(a, money_involved=False)
    assert score == sum(parts.values()) == 50 + 15 + 10 + 0 + 5


def test_safety_message_is_escalated_with_template_and_no_llm_call(kb):
    llm = FakeLLM()  # no answers queued: any LLM call would fail the test
    ctx = ctx_for(kb, make_analysis(risk_flags=[RiskFlag.SAFETY], urgency="immediate"), llm, "fr")
    respond_stage(ctx)
    assert ctx["decision"]["action"] == "escalated"
    assert "911" in ctx["reply"]["body"] and "LG-000042" in ctx["reply"]["body"]
    assert ctx["reply"]["body"].startswith("Bonjour Alex")
    assert llm.calls == []


def test_refund_draft_waits_for_human_approval(kb):
    llm = FakeLLM(
        {
            "reply": "Hello Alex, you were charged twice: the duplicate is $18.40 [F3]. I have "
            "asked Billing to refund it; refunds take 5 to 10 business days [HC-FARES#4].",
            "citations": ["F3", "HC-FARES#4"],
            "proposed_action": "refund",
            "action_amount": 18.40,
            "confidence": 0.92,
        }
    )
    ctx = ctx_for(kb, make_analysis(), llm)
    result = respond_stage(ctx)
    assert ctx["decision"]["action"] == "awaiting_approval"
    assert "money involved" in ctx["decision"]["reasons"][0]
    assert result.output["verification"]["supported"] is True
    assert result.output["retrieved"][0]["id"] == "HC-FARES#4"


def test_verified_confident_information_answer_is_auto_sent(kb):
    llm = FakeLLM(
        {
            "reply": "Hello Alex, cancelling is free within 2 minutes; after that a $5.00 fee "
            "applies [HC-CANCEL#1].",
            "citations": ["HC-CANCEL#1"],
            "proposed_action": "none",
            "confidence": 0.9,
        }
    )
    analysis = make_analysis(
        message_type="request",
        categories=["cancellation_no_show"],
        severity=None,
        summary="The customer asks how cancellation fees work.",
        customer_goal="Understand the cancellation fee.",
    )
    ctx = ctx_for(kb, analysis, llm)
    ctx["text_masked"] = "How do cancellation fees work?"
    respond_stage(ctx)
    assert ctx["decision"]["action"] == "auto_send"


def test_hallucinated_number_blocks_auto_send(kb):
    llm = FakeLLM(
        {
            "reply": "Hello Alex, cancelling is free within 10 minutes [HC-CANCEL#1].",
            "citations": ["HC-CANCEL#1"],
            "proposed_action": "none",
            "confidence": 0.95,
        }
    )
    ctx = ctx_for(
        kb, make_analysis(message_type="request", categories=["cancellation_no_show"]), llm
    )
    ctx["text_masked"] = "How do cancellation fees work?"
    respond_stage(ctx)
    assert ctx["decision"]["action"] == "awaiting_approval"
    assert "verification failed" in ctx["decision"]["reasons"][0]


def test_templates_never_invent_a_name_and_translate_team_names():
    from complaintlens.pipeline.respond import render

    fr = render("review", "fr", name="", team="Billing", ticket="LG-000001")
    assert fr.startswith("Bonjour,\n") and "équipe Facturation" in fr
    en = render("review", "en", name="Alex", team="Billing", ticket="LG-000001")
    assert en.startswith("Hello Alex,\n") and "Billing team" in en


def test_venting_and_spam_get_no_reply(kb):
    ctx = ctx_for(kb, make_analysis(response_required=False, urgency=None), FakeLLM())
    respond_stage(ctx)
    assert ctx["decision"]["action"] == "no_reply" and ctx["reply"] is None
