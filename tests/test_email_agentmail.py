"""The AgentMail email channel: receive, acknowledge, thread follow-ups, reply, webhook."""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import httpx

from complaintlens.channels import agentmail
from complaintlens.channels.email import Fetched
from complaintlens.schemas import Channel, InboundMessage
from complaintlens.settings import Settings
from complaintlens.store import CustomerMessage, Reply, Ticket, new_session
from tests.conftest import sign_in

INBOX = "lunagocare@agentmail.to"
SETTINGS = Settings(email_inbox="agentmail", email_address=INBOX, agentmail_api_key="am_test")


def mock_agentmail(monkeypatch, messages: dict[str, dict]) -> list[tuple[str, str, dict]]:
    """AgentMail double: lists `messages`, serves each by ID, records patches and replies."""
    calls: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, path, body))
        if request.method == "GET" and path.endswith("/messages"):
            return httpx.Response(
                200, json={"count": len(messages), "messages": list(messages.values())}
            )
        for message_id, message in messages.items():
            if path.endswith(message_id):
                if request.method == "GET":
                    return httpx.Response(200, json=message)
                return httpx.Response(200, json={})
        if path.endswith("/reply"):
            return httpx.Response(200, json={"message_id": "<r1>", "thread_id": "t1"})
        return httpx.Response(404)

    monkeypatch.setattr(
        agentmail,
        "_client",
        lambda s: httpx.Client(
            base_url="https://agentmail.test/v0", transport=httpx.MockTransport(handler)
        ),
    )
    return calls


def message(message_id, sender, subject, text, labels=("received", "unread"), thread="t1"):
    return {
        "message_id": message_id,
        "thread_id": thread,
        "from": sender,
        "subject": subject,
        "text": text + "\n\nOn Monday, LunaGo wrote:\n> older text",
        "extracted_text": text,
        "labels": list(labels),
        "timestamp": "2026-11-10T18:33:50.180Z",
    }


def test_new_mail_is_fetched_and_robots_are_skipped(monkeypatch):
    calls = mock_agentmail(
        monkeypatch,
        {
            "<a@x>": message("<a@x>", "Prof Omheni <prof@univ.tn>", "Ride", "Where is my ride?"),
            "<b@x>": message(
                "<b@x>", f"LunaGo <{INBOX}>", "Self", "ours", labels=("sent", "received")
            ),
            "<c@x>": message("<c@x>", "Prof <prof@univ.tn>", "Automatic reply: away", "away"),
            "<d@x>": message(
                "<d@x>", "x <y@z.com>", "Old", "done", labels=("received", "processed")
            ),
        },
    )
    fetched = agentmail.fetch_new_messages(SETTINGS)
    assert [f.message.sender for f in fetched] == ["prof@univ.tn"]
    inbound = fetched[0].message
    assert inbound.body == "Where is my ride?"  # the quoted history is left out
    assert inbound.sender_name == "Prof Omheni" and inbound.thread_id == "t1"
    patched = [c for c in calls if c[0] == "PATCH"]
    assert len(patched) == 2  # our own message and the automatic reply, marked at once
    fetched[0].ack()
    assert [c for c in calls if c[0] == "PATCH"][-1][2]["add_labels"] == ["processed"]


def test_reply_answers_the_latest_customer_email_without_citations(client, monkeypatch):
    calls = mock_agentmail(monkeypatch, {})
    with new_session() as s:
        ticket = Ticket(
            channel="email",
            sender="prof@univ.tn",
            body="hi",
            external_id="<first@x>",
            language="en",
        )
        s.add(ticket)
        s.commit()
        s.add(CustomerMessage(ticket_id=ticket.id, body="LG-12345", external_id="<second@x>"))
        s.commit()
    reply = Reply(ticket_id=ticket.id, kind="answer", body="Refunds take 5 days [HC-FARES#4].")
    agentmail.AgentMailSender(SETTINGS).send(ticket, reply)
    method, path, body = calls[-1]
    assert method == "POST" and path.endswith("<second@x>/reply")
    assert "Refunds take 5 days." in body["text"] and "[HC-" not in body["text"]
    assert ticket.number in body["text"]  # the footer names the ticket


def test_email_reply_in_the_same_thread_joins_the_ticket(client, monkeypatch):
    from complaintlens.api import inbox as poller

    batches = [
        [
            InboundMessage(
                channel=Channel.EMAIL,
                sender="sam@example.com",
                body="My ride was late",
                external_id="<1>",
                thread_id="t9",
            )
        ],
        [
            InboundMessage(
                channel=Channel.EMAIL,
                sender="sam@example.com",
                body="It was LG-12345",
                external_id="<2>",
                thread_id="t9",
            )
        ],
    ]
    monkeypatch.setattr(
        poller.agentmail_inbox,
        "fetch_new_messages",
        lambda: [Fetched(m, lambda: None) for m in batches.pop(0)],
    )
    assert asyncio.run(poller.poll_inbox_once()) == 1
    assert asyncio.run(poller.poll_inbox_once()) == 1
    tickets = client.get("/api/tickets", headers=sign_in(client)).json()
    assert len(tickets) == 1 and tickets[0]["messages"] == 2


def sign(secret: str, msg_id: str, stamp: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def test_webhook_signature_is_checked():
    secret = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
    body = b'{"type":"message.received"}'
    now = str(int(time.time()))
    headers = {
        "svix-id": "msg_1",
        "svix-timestamp": now,
        "svix-signature": sign(secret, "msg_1", now, body),
    }
    assert agentmail.verify_webhook(secret, headers, body)
    assert not agentmail.verify_webhook(secret, headers, body + b"x")  # tampered
    old = str(int(time.time()) - 3600)
    stale = {**headers, "svix-timestamp": old, "svix-signature": sign(secret, "msg_1", old, body)}
    assert not agentmail.verify_webhook(secret, stale, body)  # replayed
    assert not agentmail.verify_webhook("", headers, body)  # not configured


def test_webhook_endpoint_rejects_unsigned_calls(client):
    assert (
        client.post("/api/channels/email/webhook", json={"type": "message.received"}).status_code
        == 401
    )


def test_ride_id_in_an_email_follow_up_reaches_the_ride_check(tmp_path):
    # Regression (live, 2026-11-10): the follow-up was joined after the first email's signature,
    # so cleaning the joined text cut it off and "LG-99999" never reached the ride check.
    from complaintlens.rag.knowledge import KnowledgeBase
    from complaintlens.service import Processor
    from complaintlens.settings import get_settings

    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    p = Processor(KnowledgeBase.load(get_settings().help_center_dir), None, database_url=url)
    first = InboundMessage(
        channel=Channel.EMAIL,
        sender="sam@example.com",
        body="How do I get back something I left in a car?\n\n--\nSam",
        external_id="<1>",
        thread_id="t1",
    )
    ticket = p.process(first)
    p.add_message(ticket.id, "It was ride LG-99999.\n\n--\nSam", external_id="<2>")
    again = p.run(ticket.id)
    with new_session(url) as s:
        from sqlmodel import select

        from complaintlens.store import StageRecord

        link = s.exec(
            select(StageRecord).where(StageRecord.ticket_id == again.id, StageRecord.name == "link")
        ).one()
    assert link.output["ride_ids_quoted"] == ["LG-99999"]
    assert again.status == "needs_info"  # not on this customer's account: asked again


def test_agentmail_footer_is_removed():
    inbound = agentmail.to_inbound(
        message("<z@x>", "a <a@b.co>", "Hi", "My ride\n\n-- \nSent via AgentMail")
    )
    assert inbound.body == "My ride"
