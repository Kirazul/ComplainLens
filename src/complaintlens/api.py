"""HTTP API used by the LunaGo website and the ComplaintLens console.

Run locally:  uv run complaintlens serve   (then open http://localhost:8000/docs)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import col, func, select

from complaintlens.channels.email import EmailSender, fetch_new_messages
from complaintlens.events import EventBus
from complaintlens.llm import default_client
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.schemas import Channel, InboundMessage
from complaintlens.service import Processor
from complaintlens.settings import get_settings
from complaintlens.store import Customer, Reply, StageRecord, Ticket, Trip, new_session

log = logging.getLogger(__name__)
EMAIL_POLL_SECONDS = 15


class State:
    """Process-wide objects created at startup (one instance)."""

    def __init__(self) -> None:
        self.processor: Processor
        self.bus: EventBus
        self.email_task: asyncio.Task[None] | None = None
        self.email_status: dict[str, Any] = {"enabled": False}


state = State()


async def email_loop() -> None:
    """Poll the support inbox; process each new email in a worker thread."""
    while True:
        try:
            messages = await asyncio.to_thread(fetch_new_messages)
            state.email_status.update(last_poll_ok=True, last_error=None)
            for message in messages:
                await asyncio.to_thread(state.processor.process, message)
        except Exception as exc:
            log.exception("email poll failed")
            state.email_status.update(last_poll_ok=False, last_error=f"{type(exc).__name__}: {exc}")
        await asyncio.sleep(EMAIL_POLL_SECONDS)


def warm_up() -> None:
    from complaintlens.pipeline.language import detect_language
    from complaintlens.pipeline.understand import _classical

    detect_language("warm up the language model")
    _classical()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state.bus = EventBus()
    state.bus.bind(asyncio.get_running_loop())
    senders = {Channel.EMAIL.value: EmailSender(settings)} if settings.email_enabled else {}
    state.processor = Processor(
        KnowledgeBase.load(settings.help_center_dir),
        default_client(),
        senders=senders,
        publish=state.bus.publish,
    )
    await asyncio.to_thread(warm_up)  # load models now, not during the first customer's message
    if settings.email_enabled:
        state.email_status = {"enabled": True, "address": settings.email_address}
        state.email_task = asyncio.create_task(email_loop())
    yield
    if state.email_task:
        state.email_task.cancel()


app = FastAPI(title="ComplaintLens API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageIn(BaseModel):
    channel: Channel = Channel.WEB
    email: EmailStr
    name: str | None = Field(default=None, max_length=80)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=2, max_length=5000)


class ApproveIn(BaseModel):
    body: str | None = Field(default=None, max_length=5000)


def _ticket_summary(t: Ticket) -> dict[str, Any]:
    analysis = t.analysis or {}
    return {
        "id": t.id,
        "number": t.number,
        "channel": t.channel,
        "sender": t.sender,
        "sender_name": t.sender_name,
        "subject": t.subject,
        "status": t.status,
        "team": t.team,
        "priority": t.priority,
        "language": t.language,
        "received_at": t.received_at,
        "message_type": analysis.get("message_type"),
        "categories": analysis.get("categories", []),
        "risk_flags": analysis.get("risk_flags", []),
        "summary": analysis.get("summary"),
        "total_ms": t.total_ms,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "ok": True,
        "company": s.company_name,
        "llm": {"enabled": s.llm_enabled, "model": s.llm_model if s.llm_enabled else None},
        "email": state.email_status,
    }


@app.post("/api/messages", status_code=202)
def submit_message(payload: MessageIn, background: BackgroundTasks) -> dict[str, Any]:
    """Website form / chat: accept the message now, process it in the background."""
    inbound = InboundMessage(
        channel=payload.channel,
        sender=str(payload.email).lower(),
        sender_name=payload.name,
        subject=payload.subject,
        body=payload.body,
    )
    background.add_task(state.processor.process, inbound)
    return {"accepted": True}


@app.get("/api/tickets")
def list_tickets(limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
    with new_session() as s:
        q = select(Ticket).order_by(col(Ticket.id).desc()).limit(min(limit, 500))
        if status:
            q = q.where(Ticket.status == status)
        return [_ticket_summary(t) for t in s.exec(q)]


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int) -> dict[str, Any]:
    with new_session() as s:
        t = s.get(Ticket, ticket_id)
        if t is None:
            raise HTTPException(404, "ticket not found")
        stages = s.exec(
            select(StageRecord).where(StageRecord.ticket_id == ticket_id).order_by(StageRecord.seq)
        ).all()
        replies = s.exec(
            select(Reply).where(Reply.ticket_id == ticket_id).order_by(col(Reply.id))
        ).all()
        customer = s.get(Customer, t.customer_id) if t.customer_id else None
        trip = s.get(Trip, t.trip_id) if t.trip_id else None
        return {
            **_ticket_summary(t),
            "body": t.body,
            "analysis": t.analysis,
            "decision": t.decision,
            "stages": [r.model_dump() for r in stages],
            "replies": [r.model_dump() for r in replies],
            "customer": customer.model_dump() if customer else None,
            "trip": trip.model_dump() if trip else None,
        }


@app.post("/api/tickets/{ticket_id}/approve")
async def approve(ticket_id: int, payload: ApproveIn) -> dict[str, Any]:
    try:
        reply = await asyncio.to_thread(state.processor.approve, ticket_id, payload.body)
    except KeyError as exc:
        raise HTTPException(404, "ticket not found") from exc
    return {"status": reply.status, "error": reply.error}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with new_session() as s:
        by_status = dict(s.exec(select(Ticket.status, func.count()).group_by(Ticket.status)).all())
        by_team = dict(s.exec(select(Ticket.team, func.count()).group_by(Ticket.team)).all())
        by_lang = dict(
            s.exec(select(Ticket.language, func.count()).group_by(Ticket.language)).all()
        )
        avg_ms = s.exec(select(func.avg(Ticket.total_ms))).one()
    return {
        "tickets": sum(by_status.values()),
        "by_status": by_status,
        "by_team": by_team,
        "by_language": by_lang,
        "avg_processing_ms": round(avg_ms or 0, 1),
    }


@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        yield ": connected\n\n"
        async for event in state.bus.subscribe():
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
