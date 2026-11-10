"""Email channel: read the support inbox over IMAP, reply over SMTP in the same thread.

Works with Gmail (app password) today and with any IMAP/SMTP provider later (e.g. a custom domain),
by configuration only.

Loop protection: we never process our own messages or automatic replies (RFC 3834
``Auto-Submitted``, ``X-Autoreply``, ``Precedence: bulk/auto_reply``). Without this, two automatic
systems answering each other would loop forever.
"""

from __future__ import annotations

import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from imap_tools import AND, MailBox, MailMessage, MailMessageFlags

from complaintlens.pipeline.normalize import html_to_text
from complaintlens.pipeline.respond import strip_citations
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.settings import Settings, get_settings
from complaintlens.store import Reply, Ticket

log = logging.getLogger(__name__)


@dataclass
class Fetched:
    """A new email and how to mark it handled in the mailbox.

    The caller stores the ticket first and acknowledges afterwards, so a crash in between can only
    cause a duplicate (skipped by Message-ID), never a lost message.
    """

    message: InboundMessage
    ack: Callable[[], None]


FOOTER = {
    "en": "\n\n—\nTicket {ticket} · {company} Support\nFollow your request: {track_url}\n"
    "{company} is a fictional company created for a university NLP project (ComplaintLens). "
    "Replies are produced by an AI system under human supervision.",
    "fr": "\n\n—\nTicket {ticket} · Support {company}\nSuivre votre demande : {track_url}\n"
    "{company} est une entreprise fictive créée "
    "pour un projet universitaire de TALN (ComplaintLens). Les réponses sont produites par un "
    "système d'IA sous supervision humaine.",
}


def _header(msg: MailMessage, name: str) -> str:
    values = msg.headers.get(name.lower(), ())
    return values[0].strip() if values else ""


def is_automatic(msg: MailMessage) -> bool:
    auto_submitted = _header(msg, "auto-submitted").lower()
    precedence = _header(msg, "precedence").lower()
    return (
        (auto_submitted not in ("", "no"))
        or bool(_header(msg, "x-autoreply") or _header(msg, "x-autorespond"))
        or precedence in ("bulk", "auto_reply", "list", "junk")
    )


def received_time(header_date: datetime | None, arrived: datetime | None = None) -> datetime:
    """When the message reached us: the mail server's arrival time if known, else the Date header
    if it is a real, time-zoned date (it is the sender's clock and may be missing), else now."""
    if arrived is not None:
        return arrived
    now = utcnow()
    if header_date and header_date.tzinfo and abs(now - header_date) < timedelta(days=7):
        return header_date
    return now


def to_inbound(msg: MailMessage, arrived: datetime | None = None) -> InboundMessage:
    body = msg.text or html_to_text(msg.html or "")
    return InboundMessage(
        channel=Channel.EMAIL,
        sender=msg.from_.lower(),
        sender_name=(msg.from_values.name or None) if msg.from_values else None,
        subject=msg.subject or None,
        body=body,
        received_at=received_time(msg.date, arrived),
        external_id=_header(msg, "message-id") or None,
        in_reply_to=_header(msg, "in-reply-to") or None,
    )


def should_skip(msg: MailMessage, settings: Settings) -> bool:
    if msg.from_.lower() == settings.email_address.lower() or is_automatic(msg):
        log.info("skipping automatic/own message from %s", msg.from_)
        return True
    return False


def fetch_new_messages(settings: Settings | None = None) -> list[Fetched]:
    """Unread messages to process; skipped ones (automatic replies, our own) are marked read."""
    s = settings or get_settings()
    out: list[Fetched] = []

    def mark_read(uid: str) -> Callable[[], None]:
        def ack() -> None:
            with MailBox(s.imap_host).login(s.email_address, s.email_password) as mb:
                mb.flag(uid, MailMessageFlags.SEEN, True)

        return ack

    with MailBox(s.imap_host).login(
        s.email_address, s.email_password, initial_folder="INBOX"
    ) as mb:
        for msg in mb.fetch(AND(seen=False), mark_seen=False, bulk=True):
            if should_skip(msg, s):
                mb.flag(msg.uid, MailMessageFlags.SEEN, True)
                continue
            out.append(Fetched(to_inbound(msg), mark_read(msg.uid)))
    return out


def track_url(ticket: Ticket, settings: Settings) -> str:
    lang = ticket.language if ticket.language in ("en", "fr") else "en"
    return f"{settings.public_base_url}/{lang}/track/?id={ticket.id}&k={ticket.track_key}"


def build_reply_email(ticket: Ticket, reply: Reply, settings: Settings) -> EmailMessage:
    lang = ticket.language if ticket.language in FOOTER else "en"
    subject = (ticket.subject or "Your message").strip()
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    email = EmailMessage()
    email["From"] = formataddr((f"{settings.company_name} Support", settings.email_address))
    email["To"] = ticket.sender
    email["Subject"] = f"{subject} [{ticket.number}]"
    email["Message-ID"] = make_msgid(domain=settings.email_address.split("@")[-1])
    email["Auto-Submitted"] = "auto-replied"  # tells other robots not to answer us (RFC 3834)
    if ticket.external_id:  # keep the reply in the customer's conversation thread
        email["In-Reply-To"] = ticket.external_id
        email["References"] = ticket.external_id
    footer = FOOTER[lang].format(
        ticket=ticket.number, company=settings.company_name, track_url=track_url(ticket, settings)
    )
    email.set_content(strip_citations(reply.body) + footer)
    return email


class EmailSender:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send(self, ticket: Ticket, reply: Reply) -> None:
        s = self.settings
        email = build_reply_email(ticket, reply, s)
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30) as smtp:
            smtp.login(s.email_address, s.email_password)
            smtp.send_message(email)
        log.info("sent %s reply for %s to %s", reply.kind, ticket.number, ticket.sender)
