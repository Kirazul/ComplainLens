"""Forum relay, mail.tm inbox, operator access and abuse limits."""

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from complaintlens import store
from complaintlens.channels import mailtm
from complaintlens.security import RateLimiter, mask_contact
from complaintlens.settings import Settings, get_settings

OPERATOR, CHANNEL = "op-secret", "relay-secret"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("EMAIL_ADDRESS", "")
    monkeypatch.setenv("RETRIEVAL", "bm25")
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR)
    monkeypatch.setenv("CHANNEL_TOKEN", CHANNEL)
    monkeypatch.setenv("MESSAGES_PER_IP_PER_HOUR", "2")
    get_settings.cache_clear()
    store.get_engine.cache_clear()
    from complaintlens.api import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    store.get_engine.cache_clear()


def post_forum(client, token=CHANNEL, **overrides):
    payload = {
        "post_id": "D_kwDO123",
        "number": 7,
        "author": "Rider42",
        "title": "Charged twice",
        "body": "I was charged twice for my ride yesterday, please refund me.",
        **overrides,
    }
    return client.post(
        "/api/channels/forum/posts", json=payload, headers={"X-Channel-Token": token}
    )


def test_forum_post_needs_the_channel_token(client):
    assert post_forum(client, token="wrong").status_code == 401


def test_forum_post_is_processed_and_its_reply_queued_then_delivered(client):
    body = post_forum(client).json()
    assert body["ticket"].startswith("LG-") and body["outbox"]
    item = body["outbox"][0]
    assert item["post_id"] == "D_kwDO123" and item["body"]
    headers = {"X-Channel-Token": CHANNEL}
    assert client.get("/api/channels/forum/outbox", headers=headers).json()
    done = client.post(
        "/api/channels/forum/delivered", json={"reply_ids": [item["reply_id"]]}, headers=headers
    ).json()
    assert done == {"delivered": 1}
    assert client.get("/api/channels/forum/outbox", headers=headers).json() == []


def test_console_is_read_only_and_masked_without_the_operator_token(client):
    client.post("/api/messages", json={"email": "rimel@example.com", "body": "My app crashes"})
    ticket = client.get("/api/tickets").json()[0]
    assert ticket["sender"] == "r••••@example.com"
    assert client.post(f"/api/tickets/{ticket['id']}/approve", json={}).status_code == 401
    assert client.get("/api/operator").json() == {"operator": False}

    auth = {"Authorization": f"Bearer {OPERATOR}"}
    assert client.get("/api/tickets", headers=auth).json()[0]["sender"] == "rimel@example.com"
    assert client.get("/api/operator", headers=auth).json() == {"operator": True}
    assert (
        client.post(f"/api/tickets/{ticket['id']}/approve", json={}, headers=auth).status_code
        == 200
    )


def test_message_submission_is_rate_limited_per_client(client):
    msg = {"email": "a@example.com", "body": "Where is my order?"}
    assert client.post("/api/messages", json=msg).status_code == 202
    assert client.post("/api/messages", json=msg).status_code == 202
    assert client.post("/api/messages", json=msg).status_code == 429


def test_public_form_cannot_impersonate_the_email_or_forum_channels(client):
    for channel in ("email", "forum"):
        r = client.post(
            "/api/messages", json={"channel": channel, "email": "a@example.com", "body": "hi"}
        )
        assert r.status_code == 422


def test_review_channel_is_accepted(client):
    r = client.post(
        "/api/messages",
        json={
            "channel": "review",
            "email": "a@example.com",
            "subject": "Trip rating: 1/5",
            "body": "The driver was rude",
        },
    )
    assert r.status_code == 202


def test_mask_name():
    from complaintlens.security import mask_name

    assert mask_name("Rimel Zouari") == "Rimel Z."
    assert mask_name("Sam") == "Sam"
    assert mask_name(None) is None


def test_mask_contact():
    assert mask_contact("rimel.zouari@example.com") == "r••••@example.com"
    assert mask_contact("forum:rider42") == "forum:rider42"
    assert mask_contact(None) is None


def test_rate_limiter_daily_cap():
    limiter = RateLimiter(per_key=10, window=3600, total=2)
    limiter.check("a")
    limiter.check("b")
    with pytest.raises(HTTPException) as exc:
        limiter.check("c")
    assert exc.value.status_code == 429


RAW = (
    b"From: Prof <prof@univ.tn>\r\nTo: lunagocare@fldubai.com\r\nSubject: Refund\r\n"
    b"Message-ID: <m1@univ.tn>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
    b"I was charged twice.\r\n"
)
AUTO = RAW.replace(b"Subject: Refund", b"Subject: Away\r\nAuto-Submitted: auto-replied")


def test_mailtm_inbox_fetches_unseen_mail_and_skips_auto_replies(monkeypatch):
    patched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/token":
            return httpx.Response(200, json={"token": "t"})
        if path == "/messages":
            members = [
                {"id": "1", "seen": False, "createdAt": "2026-11-10T07:23:44+00:00"},
                {"id": "2", "seen": False},
                {"id": "3", "seen": True},
            ]
            return httpx.Response(200, json={"hydra:member": members})
        if path.endswith("/download"):
            return httpx.Response(200, content=RAW if "/1/" in path else AUTO)
        if request.method == "PATCH":
            patched.append(path)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    monkeypatch.setattr(
        mailtm,
        "_client",
        lambda s: httpx.Client(
            base_url="https://mail.test", transport=httpx.MockTransport(handler)
        ),
    )
    monkeypatch.setattr(mailtm, "_tokens", {})
    s = Settings(email_inbox="mailtm", email_address="lunagocare@fldubai.com", email_password="p")
    fetched = mailtm.fetch_new_messages(s)
    assert [f.message.sender for f in fetched] == ["prof@univ.tn"]
    message = fetched[0].message
    assert message.subject == "Refund" and "charged twice" in message.body
    # No Date header in RAW: the server's arrival time is used, never a made-up date.
    assert message.received_at.isoformat() == "2026-11-10T07:23:44+00:00"
    assert patched == ["/messages/2"]  # the auto-reply is marked seen at once
    fetched[0].ack()
    assert patched == ["/messages/2", "/messages/1"]  # the real one only once acknowledged


def test_received_time_falls_back_to_now_for_missing_or_naive_dates():
    from datetime import UTC, datetime

    from complaintlens.channels.email import received_time

    assert received_time(datetime(1900, 1, 1)).year >= 2026  # imap_tools' "no Date header"
    recent = datetime.now(UTC)
    assert received_time(recent) == recent


def test_channel_token_comparison_tolerates_non_ascii_headers(client):
    r = client.get(
        "/api/channels/forum/outbox", headers={"X-Channel-Token": "jeton-é".encode("latin-1")}
    )
    assert r.status_code == 401


def test_email_poller_stores_before_acknowledging_and_skips_duplicates(client, monkeypatch):
    import asyncio

    from complaintlens import api
    from complaintlens.channels.email import Fetched
    from complaintlens.schemas import Channel, InboundMessage

    acks: list[str] = []

    def inbox(_settings=None):
        message = InboundMessage(
            channel=Channel.EMAIL,
            sender="prof@univ.tn",
            body="My order never came",
            external_id="<m1>",
        )
        return [Fetched(message, lambda: acks.append("m1"))]

    monkeypatch.setattr(api.imap_inbox, "fetch_new_messages", inbox)
    monkeypatch.setattr(api.mailtm_inbox, "fetch_new_messages", inbox)
    assert asyncio.run(api.poll_inbox_once()) == 1
    assert (
        asyncio.run(api.poll_inbox_once()) == 0
    )  # same Message-ID: acknowledged, not re-processed
    assert acks == ["m1", "m1"]
    auth = {"Authorization": f"Bearer {OPERATOR}"}
    tickets = client.get("/api/tickets", headers=auth).json()
    assert [t["sender"] for t in tickets] == ["prof@univ.tn"]
