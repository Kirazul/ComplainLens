"""Email channel through AgentMail (https://agentmail.to): receive and reply over HTTPS.

Why AgentMail: it sends and receives over an HTTPS API, so it works on hosts that block the email
ports (our free Railway plan does), and its free plan (100 emails a day) needs no domain. The
inbox is ``lunagocare@agentmail.to``.

- Receiving: new mail is listed by the API; a message is acknowledged (label ``processed``) only
  after its ticket is stored, so a crash can only cause a duplicate (skipped by message ID), never
  a lost message. AgentMail calls our webhook as soon as mail arrives, which wakes the service.
- Replying: the answer is sent as a reply in the customer's email thread, so their mail client
  shows one conversation; a customer's reply in that thread joins the same ticket.
- Loop protection: our own messages and automatic replies are never processed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import time
from datetime import datetime
from email.utils import parseaddr
from urllib.parse import quote

import httpx
from sqlmodel import col, select

from complaintlens.channels.email import FOOTER, Fetched, track_url
from complaintlens.pipeline.normalize import html_to_text
from complaintlens.pipeline.respond import strip_citations
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.settings import Settings, get_settings
from complaintlens.store import CustomerMessage, Reply, Ticket, new_session

log = logging.getLogger(__name__)
PROCESSED = "processed"
_AUTOMATIC = re.compile(
    r"^(auto(matic)?[ -]?reply|out of (the )?office|absence|undeliverable|delivery status"
    r"|r[ée]ponse automatique|absent)",
    re.IGNORECASE,
)
# The footer AgentMail's free plan adds to emails sent from AgentMail inboxes (e.g. our tests).
_AGENTMAIL_FOOTER = re.compile(r"\s*--\s*\n?\s*Sent via AgentMail\s*$", re.IGNORECASE)
_ROBOT_SENDERS = re.compile(r"mailer-daemon|postmaster|no-?reply", re.IGNORECASE)


def _client(s: Settings) -> httpx.Client:
    return httpx.Client(
        base_url=s.agentmail_api,
        headers={"Authorization": f"Bearer {s.agentmail_api_key}"},
        timeout=30,
    )


def _path(s: Settings, message_id: str = "") -> str:
    base = f"/inboxes/{quote(s.email_address, safe='@')}/messages"
    return f"{base}/{quote(message_id, safe='')}" if message_id else base


def is_automatic(message: dict, settings: Settings) -> bool:
    sender = parseaddr(message.get("from", ""))[1].lower()
    labels = set(message.get("labels", []))
    return (
        sender == settings.email_address.lower()
        or "sent" in labels
        or bool(_ROBOT_SENDERS.search(sender))
        or bool(_AUTOMATIC.search(message.get("subject") or ""))
    )


def to_inbound(message: dict) -> InboundMessage:
    name, address = parseaddr(message.get("from", ""))
    body = (
        message.get("extracted_text")
        or message.get("text")
        or html_to_text(message.get("extracted_html") or message.get("html") or "")
    )
    body = _AGENTMAIL_FOOTER.sub("", body)
    stamp = message.get("timestamp") or message.get("created_at")
    received = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else utcnow()
    return InboundMessage(
        channel=Channel.EMAIL,
        sender=address.lower(),
        sender_name=name or None,
        subject=message.get("subject") or None,
        body=body.strip(),
        received_at=received,
        external_id=message["message_id"],
        thread_id=message.get("thread_id"),
    )


def fetch_new_messages(settings: Settings | None = None) -> list[Fetched]:
    """Received messages not processed yet; automatic ones are marked processed at once."""
    s = settings or get_settings()
    out: list[Fetched] = []
    with _client(s) as client:
        listed = client.get(_path(s), params={"limit": 50})
        listed.raise_for_status()
        for summary in listed.json().get("messages", []):
            labels = set(summary.get("labels", []))
            if "received" not in labels or PROCESSED in labels:
                continue
            message_id = summary["message_id"]
            if is_automatic(summary, s):
                _mark_processed(s, message_id)
                continue
            full = client.get(_path(s, message_id))
            full.raise_for_status()
            out.append(Fetched(to_inbound(full.json()), _acknowledge(s, message_id)))
    return out


def _mark_processed(s: Settings, message_id: str) -> None:
    with _client(s) as client:
        client.patch(
            _path(s, message_id), json={"add_labels": [PROCESSED], "remove_labels": ["unread"]}
        ).raise_for_status()


def _acknowledge(s: Settings, message_id: str):
    return lambda: _mark_processed(s, message_id)


def reply_text(ticket: Ticket, reply: Reply, settings: Settings) -> str:
    lang = ticket.language if ticket.language in FOOTER else "en"
    footer = FOOTER[lang].format(
        ticket=ticket.number, company=settings.company_name, track_url=track_url(ticket, settings)
    )
    return strip_citations(reply.body) + footer


class AgentMailSender:
    """Sends a ticket's reply as an answer to the customer's latest email in the thread."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send(self, ticket: Ticket, reply: Reply) -> None:
        s = self.settings
        with new_session() as session:
            latest = session.exec(
                select(CustomerMessage.external_id)
                .where(
                    CustomerMessage.ticket_id == ticket.id,
                    col(CustomerMessage.external_id).is_not(None),
                )
                .order_by(col(CustomerMessage.id).desc())
            ).first()
        target = latest or ticket.external_id
        if not target:
            raise ValueError("no email to reply to")
        with _client(s) as client:
            r = client.post(
                f"{_path(s, target)}/reply", json={"text": reply_text(ticket, reply, s)}
            )
            r.raise_for_status()
        log.info("sent %s reply for %s by email", reply.kind, ticket.number)


def verify_webhook(secret: str, headers: dict[str, str], body: bytes, tolerance: int = 300) -> bool:
    """Check a webhook's signature (Svix scheme, used by AgentMail): HMAC-SHA256 of
    ``id.timestamp.body`` with the base64 secret after ``whsec_``, within 5 minutes."""
    msg_id = headers.get("svix-id") or headers.get("webhook-id")
    stamp = headers.get("svix-timestamp") or headers.get("webhook-timestamp")
    signatures = headers.get("svix-signature") or headers.get("webhook-signature")
    if not (secret and msg_id and stamp and signatures):
        return False
    try:
        if abs(time.time() - int(stamp)) > tolerance:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except ValueError:
        return False
    signed = f"{msg_id}.{stamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(
        hmac.compare_digest(expected, part.split(",", 1)[1])
        for part in signatures.split()
        if part.startswith("v1,")
    )
