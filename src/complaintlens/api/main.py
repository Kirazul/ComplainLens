"""The application: startup (models, knowledge base, first account, email poller), middleware
and the routers (see ``complaintlens.api``)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from complaintlens import annotation, auth
from complaintlens.api import account, inbox, public, relay, research, staff
from complaintlens.api.state import state
from complaintlens.channels.email import EmailSender
from complaintlens.events import EventBus
from complaintlens.llm import default_client
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.rag.retrieval import build_retriever
from complaintlens.schemas import Channel
from complaintlens.security import RateLimiter
from complaintlens.service import Processor
from complaintlens.settings import get_settings
from complaintlens.store import new_session

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def warm_up() -> None:
    """Load the models now, not during the first customer's message."""
    from complaintlens.pipeline.language import detect_language
    from complaintlens.pipeline.understand import _classical

    detect_language("warm up the language model")
    _classical()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state.bus = EventBus()
    state.bus.bind(asyncio.get_running_loop())
    state.limiter = RateLimiter(
        per_key=settings.messages_per_ip_per_hour, window=3600, total=settings.messages_per_day
    )
    state.login_limiter = RateLimiter(per_key=10, window=900, total=2000, what="sign-in attempts")
    senders = {Channel.EMAIL.value: EmailSender(settings)} if settings.email_can_send else {}
    kb = KnowledgeBase.load(settings.help_center_dir)
    retriever = await asyncio.to_thread(build_retriever, kb)
    state.processor = Processor(
        kb, default_client(), senders=senders, publish=state.bus.publish, retriever=retriever
    )
    await asyncio.to_thread(warm_up)
    auth.ensure_admin()
    with new_session() as s:  # gold-set items for the annotation page
        for path in sorted(research.GOLD_DIR.glob("*.jsonl")):
            annotation.load_items(s, path)
    if settings.email_enabled:
        state.email_status = {
            "enabled": True,
            "address": settings.email_address,
            "sends_replies": settings.email_can_send,
        }
        state.email_task = asyncio.create_task(inbox.email_loop())
    yield
    if state.email_task:
        state.email_task.cancel()


app = FastAPI(title="ComplaintLens API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def track_activity(request: Request, call_next):
    state.last_activity = time.monotonic()  # keeps the email poller running (see inbox.py)
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


for module in (public, account, staff, research, relay):
    app.include_router(module.router)
