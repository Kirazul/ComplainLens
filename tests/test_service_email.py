from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
from imap_tools import MailMessage
from sqlmodel import select

from complaintlens.channels.email import build_reply_email, is_automatic, to_inbound
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.schemas import Channel, InboundMessage
from complaintlens.service import Processor
from complaintlens.settings import Settings, get_settings
from complaintlens.store import Reply, StageRecord, Ticket, new_session
from tests.fakes import FakeLLM

ANALYSIS = {
    "message_type": "complaint",
    "response_required": True,
    "urgency": "24h",
    "categories": ["fare_billing"],
    "severity": 2,
    "risk_flags": [],
    "sentiment": "negative",
    "entities": [],
    "summary": "The customer was charged twice for last night's ride.",
    "customer_goal": "Refund of the duplicate charge.",
}


def raw_email(**headers) -> MailMessage:
    m = EmailMessage()
    m["From"] = headers.pop("from_", "Prof Omheni <prof@univ.tn>")
    m["To"] = "lunago.support@gmail.com"
    m["Subject"] = "Facturé deux fois"
    m["Message-ID"] = "<abc123@univ.tn>"
    m["Date"] = "Sat, 07 Nov 2026 20:15:00 +0000"
    for k, v in headers.items():
        m[k.replace("_", "-")] = v
    m.set_content(
        "J'ai été facturé deux fois pour ma course d'hier soir !\n\n"
        "Le sam. 7 nov. 2026, LunaGo <x@y.z> a écrit :\n> ancien message"
    )
    return MailMessage.from_bytes(m.as_bytes())


def test_email_is_converted_with_threading_headers():
    msg = to_inbound(raw_email())
    assert msg.sender == "prof@univ.tn" and msg.sender_name == "Prof Omheni"
    assert msg.external_id == "<abc123@univ.tn>"
    assert msg.received_at == datetime(2026, 11, 7, 20, 15, tzinfo=UTC)


def test_automatic_replies_are_detected_to_avoid_mail_loops():
    assert not is_automatic(raw_email())
    assert is_automatic(raw_email(Auto_Submitted="auto-replied"))
    assert is_automatic(raw_email(Precedence="bulk"))


def test_reply_email_threads_and_identifies_itself_as_automatic():
    s = Settings(email_address="lunago.support@gmail.com", company_name="LunaGo")
    ticket = Ticket(
        id=7,
        channel="email",
        sender="prof@univ.tn",
        subject="Facturé deux fois",
        body="x",
        external_id="<abc123@univ.tn>",
        language="fr",
    )
    email = build_reply_email(ticket, Reply(ticket_id=7, kind="answer", body="Bonjour"), s)
    assert email["Subject"] == "Re: Facturé deux fois [LG-000007]"
    assert email["In-Reply-To"] == "<abc123@univ.tn>"
    assert email["Auto-Submitted"] == "auto-replied"
    assert "entreprise fictive" in email.get_content()


class RecordingSender:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, ticket, reply):
        if self.fail:
            raise ConnectionError("SMTP down")
        self.sent.append((ticket.number, reply.kind, reply.body))


@pytest.fixture
def processor_factory(tmp_path):
    url = f"sqlite:///{(tmp_path / 'svc.db').as_posix()}"
    kb = KnowledgeBase.load(get_settings().help_center_dir)

    def make(llm, sender):
        events = []
        p = Processor(kb, llm, {"email": sender}, events.append, database_url=url)
        return p, events, url

    return make


def inbound(text="I was charged twice for my ride last night!"):
    return InboundMessage(
        channel=Channel.EMAIL,
        sender="prof@univ.tn",
        sender_name="Prof",
        subject="Charged twice",
        body=text,
        external_id="<m1@univ.tn>",
    )


def test_end_to_end_refund_case_sends_ack_and_keeps_draft_for_approval(processor_factory):
    draft = {
        "reply": "Hello Prof, you were charged twice [F4]. I have asked Billing to refund the "
        "duplicate; refunds take 5 to 10 business days [HC-FARES#4].",
        "citations": ["F4", "HC-FARES#4"],
        "proposed_action": "refund",
        "action_amount": None,
        "confidence": 0.9,
    }
    sender = RecordingSender()
    p, events, url = processor_factory(FakeLLM(ANALYSIS, draft), sender)
    ticket = p.process(inbound())

    assert ticket.status == "awaiting_approval" and ticket.team == "Billing"
    assert ticket.trip_id is not None
    assert [kind for _, kind, _ in sender.sent] == ["acknowledgement"]
    with new_session(url) as s:
        q = select(StageRecord).where(StageRecord.ticket_id == ticket.id).order_by(StageRecord.seq)
        stages = s.exec(q).all()
        assert [r.name for r in stages] == [
            "normalize",
            "pii_masking",
            "language",
            "understand",
            "link",
            "respond",
        ]
        replies = s.exec(select(Reply).where(Reply.ticket_id == ticket.id)).all()
        assert {(r.kind, r.status) for r in replies} == {
            ("answer", "draft"),
            ("acknowledgement", "sent"),
        }
    assert {e["type"] for e in events} >= {"ticket_created", "stage", "ticket_updated"}

    approved = p.agent_reply(ticket.id, author="Rimel")
    assert approved.status == "sent" and approved.author == "Rimel"
    assert sender.sent[-1][1] == "answer"


def test_llm_failure_never_loses_the_message(processor_factory):
    sender = RecordingSender()
    p, _, _ = processor_factory(FakeLLM("garbage", "still garbage"), sender)
    ticket = p.process(inbound())
    assert ticket.status == "awaiting_approval"
    assert "pipeline error" in ticket.decision["reasons"][0]
    assert sender.sent and sender.sent[0][1] == "acknowledgement"


def test_failed_smtp_send_is_recorded(processor_factory):
    p, _, url = processor_factory(None, RecordingSender(fail=True))
    ticket = p.process(inbound("How do cancellation fees work?"))
    with new_session(url) as s:
        reply = s.exec(select(Reply).where(Reply.ticket_id == ticket.id)).first()
        assert reply.status == "failed" and "SMTP down" in reply.error
