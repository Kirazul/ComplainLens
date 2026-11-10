"""Machine endpoints for the scheduled relay (.github/workflows/relay.yml), with the channel token.

Community forum (GitHub Discussions): the relay sends each new post here and posts our replies back
as comments; replies sent later by an agent wait in the outbox. The relay also wakes the service
every hour to collect email.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import col, select

from complaintlens.api.inbox import poll_inbox_once
from complaintlens.api.state import state
from complaintlens.channels.agentmail import verify_webhook
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.security import require_channel_token
from complaintlens.settings import get_settings
from complaintlens.store import Reply, Ticket, new_session

router = APIRouter(
    prefix="/api/channels", tags=["relay"], dependencies=[Depends(require_channel_token)]
)
# Called by AgentMail when new mail arrives; authenticated by its signature, not the channel token.
webhooks = APIRouter(prefix="/api/channels", tags=["relay"])


class ForumPostIn(BaseModel):
    post_id: str = Field(min_length=1, max_length=100)  # GitHub's discussion node ID
    number: int  # discussion number, used to build links
    author: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=8000)


class DeliveredIn(BaseModel):
    reply_ids: list[int]


def _forum_outbox(s, ticket_id: int | None = None) -> list[dict[str, Any]]:
    q = (
        select(Reply, Ticket)
        .join(Ticket, col(Ticket.id) == col(Reply.ticket_id))
        .where(Reply.status == "queued", Ticket.channel == Channel.FORUM.value)
        .order_by(col(Reply.id))
    )
    if ticket_id is not None:
        q = q.where(Ticket.id == ticket_id)
    return [
        {
            "reply_id": r.id,
            "post_id": t.external_id,
            "ticket": t.number,
            "language": t.language,
            "kind": r.kind,
            "body": r.body,
        }
        for r, t in s.exec(q).all()
    ]


@router.post("/forum/posts")
async def forum_post(payload: ForumPostIn) -> dict[str, Any]:
    """Process a new forum post now (about 5-15 s) and return what to post back."""
    inbound = InboundMessage(
        channel=Channel.FORUM,
        sender=f"forum:{payload.author.lower()}",
        sender_name=payload.author,
        subject=payload.title or None,
        body=payload.body,
        external_id=payload.post_id,
    )
    ticket = await asyncio.to_thread(state.processor.process, inbound)
    analysis = ticket.analysis or {}
    with new_session() as s:
        return {
            "ticket": ticket.number,
            "status": ticket.status,
            "team": ticket.team,
            "message_type": analysis.get("message_type"),
            "categories": analysis.get("categories", []),
            "language": ticket.language,
            "outbox": _forum_outbox(s, ticket.id),
        }


@router.post("/poll")
async def relay_poll() -> dict[str, Any]:
    """Called by the scheduled relay: collect new email now (the service may have slept)."""
    if not get_settings().email_enabled:
        return {"emails": 0, "email_enabled": False}
    return {"emails": await poll_inbox_once(), "email_enabled": True}


@router.get("/forum/outbox")
def forum_outbox() -> list[dict[str, Any]]:
    """Replies waiting to be posted (e.g. sent by an agent after the post was answered)."""
    with new_session() as s:
        return _forum_outbox(s)


@router.post("/forum/delivered")
def forum_delivered(payload: DeliveredIn) -> dict[str, int]:
    with new_session() as s:
        done = 0
        for reply_id in payload.reply_ids:
            reply = s.get(Reply, reply_id)
            if reply is not None and reply.status == "queued":
                reply.status, reply.sent_at = "sent", utcnow()
                s.add(reply)
                done += 1
        s.commit()
    state.bus.publish({"type": "reply", "status": "sent", "count": done})
    return {"delivered": done}


@webhooks.post("/email/webhook", status_code=202)
async def email_webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:
    """New mail at AgentMail: collect it now (the request also wakes a sleeping service)."""
    secret = get_settings().agentmail_webhook_secret
    if not verify_webhook(secret, dict(request.headers), await request.body()):
        raise HTTPException(401, "invalid signature")
    background.add_task(poll_inbox_once)
    return {"accepted": True}
