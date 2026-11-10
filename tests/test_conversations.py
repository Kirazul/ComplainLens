"""A ticket is a conversation: follow-ups, agent replies, resolve and reopen."""

import pytest

from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.schemas import Channel, InboundMessage
from complaintlens.service import Processor
from complaintlens.settings import get_settings
from tests.fakes import FakeLLM

# --- over HTTP, offline (no LLM: every answer waits for an agent) ------------------------------


def start_chat(client, body="I left my phone in the car last night, can you help me find it?"):
    r = client.post(
        "/api/messages", json={"email": "sam@example.com", "body": body, "channel": "chat"}
    )
    return r.json()


def public(client, ticket):
    return client.get(
        f"/api/public/tickets/{ticket['id']}", params={"k": ticket["track_key"]}
    ).json()


def test_follow_up_joins_the_same_conversation(client, staff):
    ticket = start_chat(client)
    r = client.post(
        f"/api/public/tickets/{ticket['id']}/messages",
        json={"k": ticket["track_key"], "body": "It is a black phone in a blue case."},
    )
    assert r.status_code == 202
    view = public(client, ticket)
    said = [(m["from"], m.get("kind")) for m in view["messages"]]
    # The acknowledgement is sent once, not after every message.
    assert said == [("customer", None), ("lunago", "acknowledgement"), ("customer", None)]
    assert len(client.get("/api/tickets", headers=staff).json()) == 1
    detail = client.get(f"/api/tickets/{ticket['id']}", headers=staff).json()
    assert detail["messages"] == 2
    assert len(detail["stages"]) == 6  # the trace of the latest run only
    understood = next(s for s in detail["stages"] if s["name"] == "normalize")
    assert understood["output"]["chars_received"] > len("It is a black phone in a blue case.")


def test_follow_up_needs_the_tracking_key(client):
    ticket = start_chat(client)
    r = client.post(
        f"/api/public/tickets/{ticket['id']}/messages", json={"k": "guess", "body": "hello"}
    )
    assert r.status_code == 404


def test_agent_reply_reaches_the_customer_with_the_agent_name(client, staff):
    ticket = start_chat(client)
    sent = client.post(
        f"/api/tickets/{ticket['id']}/reply",
        json={"body": "Sorry Sam, I have waived the fee [HC-CANCEL#2]."},
        headers=staff,
    )
    assert sent.json() == {"status": "sent", "error": None}
    last = public(client, ticket)["messages"][-1]
    assert last["author"] == "Administrator"
    assert last["body"] == "Sorry Sam, I have waived the fee."  # citations are for agents
    detail = client.get(f"/api/tickets/{ticket['id']}", headers=staff).json()
    assert detail["status"] == "answered" and "[HC-CANCEL#2]" in detail["thread"][-1]["body"]


def test_resolve_and_reopen(client, staff):
    ticket = start_chat(client)
    url = f"/api/tickets/{ticket['id']}/status"
    assert client.post(url, json={"resolved": True}, headers=staff).json() == {"status": "closed"}
    reopened = client.post(url, json={"resolved": False}, headers=staff).json()
    assert reopened == {"status": "awaiting_approval"}


# --- the conversation rules, with a fake LLM ---------------------------------------------------

ANALYSIS = {
    "message_type": "request",
    "response_required": True,
    "urgency": "standard",
    "categories": ["cancellation_no_show"],
    "severity": None,
    "risk_flags": [],
    "sentiment": "neutral",
    "entities": [],
    "summary": "The customer asks how cancellation fees work.",
    "customer_goal": "Understand cancellation fees.",
}
ANSWER = {
    "reply": "Hello, a fee applies after 2 minutes [HC-CANCEL#1].",
    "citations": ["HC-CANCEL#1"],
    "proposed_action": "none",
    "action_amount": None,
    "confidence": 0.95,
}


@pytest.fixture
def processor(tmp_path):
    def make(*answers):
        url = f"sqlite:///{(tmp_path / 'conv.db').as_posix()}"
        kb = KnowledgeBase.load(get_settings().help_center_dir)
        llm = FakeLLM(*answers)
        return Processor(kb, llm, database_url=url), llm

    return make


def question(text="How do cancellation fees work? My email is sam.lee@example.com"):
    return InboundMessage(channel=Channel.CHAT, sender="sam@example.com", body=text)


def test_follow_up_is_answered_in_context_with_personal_data_masked(processor):
    p, llm = processor(ANALYSIS, ANSWER, ANALYSIS, ANSWER)
    ticket = p.process(question())
    assert ticket.status == "auto_send"
    p.add_message(ticket.id, "And if the driver is late?")
    p.run(ticket.id)
    prompt = llm.calls[-1][-1]["content"]
    assert "CONVERSATION SO FAR" in prompt and "And if the driver is late?" in prompt
    assert "sam.lee@example.com" not in prompt  # masked before it reaches the LLM


def test_once_an_agent_replied_the_ai_only_drafts(processor):
    p, _ = processor(ANALYSIS, ANSWER, ANALYSIS, ANSWER)
    ticket = p.process(question())
    p.agent_reply(ticket.id, "Let me check this for you.", author="Rimel")
    p.add_message(ticket.id, "Thanks, any news?")
    again = p.run(ticket.id)
    assert again.status == "awaiting_approval"
    assert "an agent is handling this conversation" in again.decision["reasons"]


def test_an_escalated_conversation_stays_escalated(processor):
    risky = {**ANALYSIS, "risk_flags": ["safety"], "message_type": "complaint", "severity": 3}
    p, _ = processor(risky, ANALYSIS, ANSWER)
    ticket = p.process(question("The driver was drunk and I felt unsafe."))
    assert ticket.status == "escalated"
    p.add_message(ticket.id, "Also, how do cancellation fees work?")
    assert p.run(ticket.id).status == "escalated"
