"""HTTP API used by the LunaGo website and the ComplaintLens console.

Run locally:  uv run complaintlens serve   (then open http://localhost:8000/docs)
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import col, func, select

from complaintlens import annotation
from complaintlens.channels import email as imap_inbox
from complaintlens.channels import mailtm as mailtm_inbox
from complaintlens.channels.email import EmailSender
from complaintlens.events import EventBus
from complaintlens.llm import default_client
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.rag.retrieval import build_retriever
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.security import (
    RateLimiter,
    client_ip,
    is_operator,
    mask_contact,
    require_channel_token,
    require_operator,
)
from complaintlens.service import Processor
from complaintlens.settings import ROOT, get_settings
from complaintlens.store import Customer, Reply, StageRecord, Ticket, Trip, new_session

log = logging.getLogger(__name__)
EMAIL_POLL_SECONDS = 15
# The host puts the service to sleep after 10 idle minutes (no network traffic) and wakes it on
# the next request. Polling the inbox forever would keep it awake (and spend the free credit), so
# the inbox is polled only while the API has been used recently; a scheduled relay
# (.github/workflows/relay.yml) wakes it every hour to collect mail even when nobody visits.
ACTIVE_WINDOW_SECONDS = 600


class State:
    """Process-wide objects created at startup (one instance)."""

    def __init__(self) -> None:
        self.processor: Processor
        self.bus: EventBus
        self.email_task: asyncio.Task[None] | None = None
        self.email_status: dict[str, Any] = {"enabled": False}
        self.limiter: RateLimiter
        self.last_activity = time.monotonic()


state = State()


async def poll_inbox_once() -> int:
    """Fetch new emails and process each one in a worker thread; returns how many."""
    inbox = mailtm_inbox if get_settings().email_inbox == "mailtm" else imap_inbox
    try:
        messages = await asyncio.to_thread(inbox.fetch_new_messages)
        state.email_status.update(last_poll_ok=True, last_error=None)
    except Exception as exc:
        log.exception("email poll failed")
        state.email_status.update(last_poll_ok=False, last_error=f"{type(exc).__name__}: {exc}")
        return 0
    for message in messages:
        await asyncio.to_thread(state.processor.process, message)
    return len(messages)


async def email_loop() -> None:
    """Poll the support inbox every few seconds while the API is in use."""
    while True:
        if time.monotonic() - state.last_activity < ACTIVE_WINDOW_SECONDS:
            await poll_inbox_once()
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
    state.limiter = RateLimiter(
        per_key=settings.messages_per_ip_per_hour, window=3600, total=settings.messages_per_day
    )
    state.bus.bind(asyncio.get_running_loop())
    senders = {Channel.EMAIL.value: EmailSender(settings)} if settings.email_can_send else {}
    kb = KnowledgeBase.load(settings.help_center_dir)
    retriever = await asyncio.to_thread(build_retriever, kb)
    state.processor = Processor(
        kb,
        default_client(),
        senders=senders,
        publish=state.bus.publish,
        retriever=retriever,
    )
    await asyncio.to_thread(warm_up)  # load models now, not during the first customer's message
    with new_session() as s:  # gold-set items for the annotation page
        for path in sorted(GOLD_DIR.glob("*.jsonl")):
            annotation.load_items(s, path)
    if settings.email_enabled:
        state.email_status = {
            "enabled": True,
            "address": settings.email_address,
            "sends_replies": settings.email_can_send,
        }
        state.email_task = asyncio.create_task(email_loop())
    yield
    if state.email_task:
        state.email_task.cancel()


app = FastAPI(title="ComplaintLens API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def track_activity(request: Request, call_next):
    state.last_activity = time.monotonic()
    return await call_next(request)


class MessageIn(BaseModel):
    """A message from the website: the contact form, the live chat or a trip rating."""

    channel: Literal[Channel.WEB, Channel.CHAT, Channel.REVIEW] = Channel.WEB
    email: EmailStr
    name: str | None = Field(default=None, max_length=80)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=2, max_length=5000)


class ApproveIn(BaseModel):
    body: str | None = Field(default=None, max_length=5000)


def _ticket_summary(t: Ticket, operator: bool) -> dict[str, Any]:
    analysis = t.analysis or {}
    return {
        "id": t.id,
        "number": t.number,
        "channel": t.channel,
        "sender": t.sender if operator else mask_contact(t.sender),
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
        "retriever": state.processor.retriever.name,
        "email": state.email_status,
        "forum": {"enabled": bool(s.channel_token)},
    }


@app.get("/api/operator")
def operator_check(request: Request) -> dict[str, bool]:
    """Lets the console know whether its saved operator token is valid."""
    return {"operator": is_operator(request)}


@app.post("/api/messages", status_code=202)
def submit_message(
    payload: MessageIn, request: Request, background: BackgroundTasks
) -> dict[str, Any]:
    """Website form, chat or trip rating: accept now, process in the background."""
    state.limiter.check(client_ip(request))
    inbound = InboundMessage(
        channel=payload.channel,
        sender=str(payload.email).lower(),
        sender_name=payload.name,
        subject=payload.subject,
        body=payload.body,
    )
    ticket = state.processor.create_ticket(inbound)
    background.add_task(state.processor.run, ticket.id, inbound)
    return {"id": ticket.id, "number": ticket.number, "track_key": ticket.track_key}


# Customer-facing view of a ticket: progress and sent replies only, never internal analysis.
PUBLIC_STAGES = {
    "normalize": "received",
    "pii_masking": "received",
    "language": "understood",
    "understand": "understood",
    "link": "routed",
    "respond": "answered",
}


ANSWERED_STATUSES = {"auto_send", "answered", "no_reply", "closed"}


@app.get("/api/public/tickets/{ticket_id}")
def public_ticket(ticket_id: int, k: str) -> dict[str, Any]:
    with new_session() as s:
        t = s.get(Ticket, ticket_id)
        if t is None or not secrets.compare_digest(t.track_key, k):
            raise HTTPException(404, "ticket not found")  # same answer: do not reveal existence
        done = s.exec(select(StageRecord.name).where(StageRecord.ticket_id == ticket_id)).all()
        replies = s.exec(
            select(Reply)
            .where(Reply.ticket_id == ticket_id, Reply.status == "sent")
            .order_by(col(Reply.id))
        ).all()
        phases = ["received", "understood", "routed", "answered"]
        reached = {PUBLIC_STAGES[n] for n in done if n in PUBLIC_STAGES}
        # "Answered" means a real answer was sent (or none was needed), not an acknowledgement:
        # a ticket under review or escalated stays at "routed".
        if t.status not in ANSWERED_STATUSES:
            reached.discard("answered")
        return {
            "number": t.number,
            "status": t.status,
            "language": t.language,
            "received_at": t.received_at,
            "team": t.team,
            "phases": [{"name": p, "done": p in reached} for p in phases],
            "replies": [{"kind": r.kind, "body": r.body, "sent_at": r.sent_at} for r in replies],
        }


# Community forum (GitHub Discussions). A GitHub Actions workflow relays each new post here and
# posts our replies back as comments; replies approved later wait in the outbox.
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


@app.post("/api/channels/forum/posts", dependencies=[Depends(require_channel_token)])
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


@app.post("/api/channels/poll", dependencies=[Depends(require_channel_token)])
async def relay_poll() -> dict[str, Any]:
    """Called by the scheduled relay: collect new email now (the service may have slept)."""
    if not get_settings().email_enabled:
        return {"emails": 0, "email_enabled": False}
    return {"emails": await poll_inbox_once(), "email_enabled": True}


@app.get("/api/channels/forum/outbox", dependencies=[Depends(require_channel_token)])
def forum_outbox() -> list[dict[str, Any]]:
    """Replies waiting to be posted (e.g. approved by an agent after the post was answered)."""
    with new_session() as s:
        return _forum_outbox(s)


@app.post("/api/channels/forum/delivered", dependencies=[Depends(require_channel_token)])
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


GOLD_DIR = ROOT / "eval" / "gold"


class AnnotateIn(BaseModel):
    item_id: str
    annotator: str = Field(min_length=2, max_length=40)
    labels: annotation.Labels


class NewItemIn(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    lang: str = Field(pattern="^(en|fr)$")


@app.get("/api/annotate/next")
def annotate_next(annotator: str, set: str = "pilot") -> dict[str, Any]:
    if set not in annotation.SETS:
        raise HTTPException(400, f"set must be one of {annotation.SETS}")
    with new_session() as s:
        item = annotation.next_item(s, annotator.lower(), set)
        return {
            "item": item.model_dump() if item else None,
            "progress": annotation.progress(s),
        }


@app.post("/api/annotate", dependencies=[Depends(require_operator)])
def annotate_save(payload: AnnotateIn) -> dict[str, Any]:
    with new_session() as s:
        from complaintlens.store import AnnotationItem

        if s.get(AnnotationItem, payload.item_id) is None:
            raise HTTPException(404, "item not found")
        annotation.save(s, payload.item_id, payload.annotator.lower(), payload.labels)
        return {"saved": True, "progress": annotation.progress(s)}


@app.post("/api/annotate/items", status_code=201, dependencies=[Depends(require_operator)])
def annotate_add_item(payload: NewItemIn) -> dict[str, Any]:
    """Author a gold message (used for the French set: no licensed French data exists)."""
    from complaintlens.store import AnnotationItem

    with new_session() as s:
        prefix = f"{payload.lang}-authored-"
        count = s.exec(
            select(func.count())
            .select_from(AnnotationItem)
            .where(col(AnnotationItem.id).startswith(prefix))
        ).one()
        item = AnnotationItem(
            id=f"{prefix}{count + 1:04d}",
            set=f"gold_{payload.lang}",
            lang=payload.lang,
            text=payload.text.strip(),
            meta={"source": "authored by the team (fictional, no personal data)"},
        )
        s.add(item)
        s.commit()
        return item.model_dump()


@app.get("/api/annotate/agreement")
def annotate_agreement(set: str = "pilot") -> dict[str, Any]:
    with new_session() as s:
        return annotation.agreement(s, set)


RESULTS_DIR = ROOT / "reports" / "results"


def _result(name: str) -> dict[str, Any]:
    path = RESULTS_DIR / name
    if not path.exists():
        raise HTTPException(404, f"{name} not generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/insights")
def insights() -> dict[str, Any]:
    """Daily volume, detected incidents and problem clusters of the real Uber stream."""
    return _result("insights_uber.json")


@app.get("/api/experiments")
def experiments() -> list[dict[str, Any]]:
    """Headline numbers of the report, each with the results file that produced it."""
    rows: list[dict[str, Any]] = []

    def add(question: str, claim: str, value: str, source: str) -> None:
        rows.append({"question": question, "claim": claim, "value": value, "source": source})

    if (RESULTS_DIR / "baseline_complaints2019.json").exists():
        b = _result("baseline_complaints2019.json")
        best = b["task_a_complaint_vs_not"]["models"]["tfidf_word+char_lr"]
        sev = b["task_b_severity_on_complaints"]["models"]["tfidf_word+char_lr"]
        add(
            "RQ1",
            "Complaint vs. not, macro-F1 (published non-neural best: 79.0)",
            f"{best['macro_f1_mean'] * 100:.1f} ± {best['macro_f1_std'] * 100:.1f}",
            "baseline_complaints2019.json",
        )
        add(
            "RQ1",
            "Severity 1-4, macro-F1 (published LR-BOW: 43.5)",
            f"{sev['macro_f1_mean'] * 100:.1f} ± {sev['macro_f1_std'] * 100:.1f}",
            "baseline_complaints2019.json",
        )
    if (RESULTS_DIR / "gate_complaints2019.json").exists():
        g = _result("gate_complaints2019.json")["methods"]["gate_alpha_0.1"]
        add(
            "RQ2",
            "Messages automated at a guaranteed 10% error bound",
            f"{g['automation_rate_mean'] * 100:.1f}% (violations: {g['violations_of_alpha']})",
            "gate_complaints2019.json",
        )
    if (RESULTS_DIR / "retrieval_helpcenter.json").exists():
        r = _result("retrieval_helpcenter.json")["retrievers"]
        dense = next(v for k, v in r.items() if k.startswith("dense"))
        add(
            "RQ3",
            "Help Center retrieval MRR@10, dense vs. BM25 (development set)",
            f"{dense['mrr@10']:.2f} vs. {r['bm25']['mrr@10']:.2f}",
            "retrieval_helpcenter.json",
        )
    if (RESULTS_DIR / "trends_uber.json").exists():
        t = _result("trends_uber.json")
        z = t["methods"]["zscore"]["injection_recall_test"]["20"]["mean"]
        c = t["methods"]["count_threshold"]["injection_recall_test"]["20"]["mean"]
        add(
            "RQ4",
            "Recall on injected 20-message bursts, z-score vs. count threshold",
            f"{z:.2f} vs. {c:.2f}",
            "trends_uber.json",
        )
        add(
            "RQ4",
            "Delay before the 14 Nov 2017 promotion-crash alert",
            f"{t['real_event_hourly']['delay_hours']} h",
            "trends_uber.json",
        )
    if (RESULTS_DIR / "rootcause_simulation.json").exists():
        rc = next(
            c
            for c in _result("rootcause_simulation.json")["conditions"]
            if c["incident_size"] == 50 and c["purity"] == 0.5
        )
        add(
            "RQ5",
            "Probable cause precision@k, mixed incident of 50 tickets",
            f"{rc['precision_at_k_ours']:.2f} vs. {rc['precision_at_k_most_frequent']:.2f}",
            "rootcause_simulation.json",
        )
    return rows


@app.get("/api/help")
def help_center(lang: str = "en") -> list[dict[str, Any]]:
    kb = state.processor.kb
    lang = lang if lang in ("en", "fr") else "en"
    articles: dict[str, dict[str, Any]] = {}
    for c in kb.chunks:
        if c.lang != lang:
            continue
        art = articles.setdefault(
            c.article_id, {"id": c.article_id, "title": c.title, "sections": []}
        )
        art["sections"].append({"id": c.id, "heading": c.heading, "text": c.text})
    return list(articles.values())


@app.get("/api/tickets")
def list_tickets(
    request: Request, limit: int = 100, status: str | None = None
) -> list[dict[str, Any]]:
    operator = is_operator(request)
    with new_session() as s:
        q = select(Ticket).order_by(col(Ticket.id).desc()).limit(min(limit, 500))
        if status:
            q = q.where(Ticket.status == status)
        return [_ticket_summary(t, operator) for t in s.exec(q)]


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int, request: Request) -> dict[str, Any]:
    operator = is_operator(request)
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
        customer_view = customer.model_dump() if customer else None
        if customer_view and not operator:
            customer_view["contact"] = mask_contact(customer_view["contact"])
        return {
            **_ticket_summary(t, operator),
            "body": t.body,
            "analysis": t.analysis,
            "decision": t.decision,
            "stages": [r.model_dump() for r in stages],
            "replies": [r.model_dump() for r in replies],
            "customer": customer_view,
            "trip": trip.model_dump() if trip else None,
        }


@app.post("/api/tickets/{ticket_id}/approve", dependencies=[Depends(require_operator)])
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
