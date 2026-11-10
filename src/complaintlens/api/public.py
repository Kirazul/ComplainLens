"""What anyone can use without an account: send a message, follow and continue the conversation.

A conversation is private to whoever holds its tracking key (``k``), given when it starts.
Accounts, rides and bookings are in ``account.py``.
"""

from __future__ import annotations

import secrets
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import select

from complaintlens.api.state import state
from complaintlens.schemas import Channel, InboundMessage
from complaintlens.security import client_ip
from complaintlens.service import thread
from complaintlens.settings import get_settings
from complaintlens.store import StageRecord, Ticket, new_session

router = APIRouter(prefix="/api", tags=["public"])

# Customer-facing progress: pipeline stages grouped into four steps, never internal analysis.
PUBLIC_STAGES = {
    "normalize": "received",
    "pii_masking": "received",
    "language": "understood",
    "understand": "understood",
    "link": "routed",
    "respond": "answered",
}
PHASES = ["received", "understood", "routed", "answered"]
# "Answered" means a real answer was sent (or none was needed), not an acknowledgement.
ANSWERED_STATUSES = {"auto_send", "answered", "no_reply", "closed"}


class MessageIn(BaseModel):
    """A message from the website: the contact form, the live chat or a trip rating."""

    channel: Literal[Channel.WEB, Channel.CHAT, Channel.REVIEW] = Channel.WEB
    email: EmailStr
    name: str | None = Field(default=None, max_length=80)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=2, max_length=5000)
    # The ride the message is about, when the customer knows it (e.g. from "Your rides").
    ride: str | None = Field(default=None, pattern=r"^LG-\d{4,6}$")


class FollowUpIn(BaseModel):
    k: str = Field(max_length=64)
    body: str = Field(min_length=1, max_length=5000)


@router.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "ok": True,
        "company": s.company_name,
        "llm": {"enabled": s.llm_enabled, "model": s.llm_model if s.llm_enabled else None},
        "retriever": state.processor.retriever.name,
        "email": state.email_status,
        "forum": {"enabled": bool(s.channel_token)},
    }


@router.post("/messages", status_code=202)
def submit_message(
    payload: MessageIn, request: Request, background: BackgroundTasks
) -> dict[str, Any]:
    """Start a conversation: accept now, process in the background."""
    state.limiter.check(client_ip(request))
    subject = payload.subject
    if payload.ride:  # in the subject, where the pipeline (and the agent) read it with the text
        subject = f"{subject} (ride {payload.ride})" if subject else f"Ride {payload.ride}"
    inbound = InboundMessage(
        channel=payload.channel,
        sender=str(payload.email).lower(),
        sender_name=payload.name,
        subject=subject,
        body=payload.body,
    )
    ticket = state.processor.create_ticket(inbound)
    background.add_task(state.processor.run, ticket.id, inbound)
    return {"id": ticket.id, "number": ticket.number, "track_key": ticket.track_key}


def _ticket_for_key(s, ticket_id: int, key: str) -> Ticket:
    t = s.get(Ticket, ticket_id)
    if t is None or not secrets.compare_digest(t.track_key.encode(), key.encode()):
        raise HTTPException(404, "ticket not found")  # same answer: do not reveal existence
    return t


@router.get("/public/tickets/{ticket_id}")
def public_ticket(ticket_id: int, k: str) -> dict[str, Any]:
    with new_session() as s:
        t = _ticket_for_key(s, ticket_id, k)
        done = s.exec(select(StageRecord.name).where(StageRecord.ticket_id == ticket_id)).all()
        reached = {PUBLIC_STAGES[n] for n in done if n in PUBLIC_STAGES}
        if t.status not in ANSWERED_STATUSES:  # under review or escalated: stays at "routed"
            reached.discard("answered")
        return {
            "number": t.number,
            "status": t.status,
            "language": t.language,
            "received_at": t.received_at,
            "phases": [{"name": p, "done": p in reached} for p in PHASES],
            "messages": thread(s, t, for_customer=True),
        }


@router.post("/public/tickets/{ticket_id}/messages", status_code=202)
def follow_up(
    ticket_id: int, payload: FollowUpIn, request: Request, background: BackgroundTasks
) -> dict[str, bool]:
    """The customer writes again in the same conversation (chat or tracking page)."""
    with new_session() as s:
        _ticket_for_key(s, ticket_id, payload.k)
    state.limiter.check(client_ip(request))
    state.processor.add_message(ticket_id, payload.body.strip())
    background.add_task(state.processor.run, ticket_id)
    return {"accepted": True}
