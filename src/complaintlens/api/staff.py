"""The console (support staff): sign-in, the team, the inbox, conversations and live events.

Everything here needs a signed-in account (``Authorization: Bearer <token>``); the team pages
need an administrator. See ``complaintlens.auth``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import col, delete, func, select

from complaintlens import auth
from complaintlens.api.state import state
from complaintlens.auth import Admin, CurrentUser, current_user, require_admin
from complaintlens.schemas import as_utc
from complaintlens.security import client_ip
from complaintlens.service import thread
from complaintlens.store import (
    Customer,
    CustomerMessage,
    LoginSession,
    Reply,
    StageRecord,
    Ticket,
    Trip,
    User,
    new_session,
)

router = APIRouter(prefix="/api", tags=["staff"])
signed_in = [Depends(current_user)]


# --- sign-in -----------------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


@router.post("/auth/login")
def login(payload: LoginIn, request: Request) -> dict[str, Any]:
    state.login_limiter.check(client_ip(request))
    with new_session() as s:
        user = auth.authenticate(s, payload.username, payload.password)
        if user is None:
            raise HTTPException(401, "wrong username or password")
        return {"token": auth.start_session(s, user), "user": auth.public_user(user)}


@router.post("/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    if token := auth.bearer(request):
        with new_session() as s:
            auth.end_session(s, token)
    return {"signed_out": True}


@router.get("/auth/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return auth.public_user(user)


@router.post("/auth/password")
def change_password(payload: PasswordIn, user: CurrentUser) -> dict[str, Any]:
    """Change your own password. Other browsers are signed out; this one gets a new token."""
    auth.check_password(payload.new)
    with new_session() as s:
        account = s.get(User, user.id)
        assert account is not None
        if not auth.verify_password(payload.current, account.password_hash):
            raise HTTPException(403, "the current password is wrong")
        auth.set_password(s, account, payload.new)
        return {"token": auth.start_session(s, account)}


# --- team (administrators) ---------------------------------------------------------------------


class NewUserIn(BaseModel):
    username: str = Field(max_length=32)
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(max_length=200)
    role: Literal["agent", "admin"] = "agent"


class ResetIn(BaseModel):
    password: str = Field(max_length=200)


def _member(u: User) -> dict[str, Any]:
    return {**auth.public_user(u), "created_at": u.created_at}


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users() -> list[dict[str, Any]]:
    with new_session() as s:
        return [_member(u) for u in s.exec(select(User).order_by(col(User.id)))]


@router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
def add_user(payload: NewUserIn) -> dict[str, Any]:
    username = auth.check_new_account(payload.username, payload.password)
    with new_session() as s:
        if s.exec(select(User).where(User.username == username)).first():
            raise HTTPException(409, "this username is taken")
        user = User(
            username=username,
            name=payload.name.strip(),
            role=payload.role,
            password_hash=auth.hash_password(payload.password),
        )
        s.add(user)
        s.commit()
        return _member(user)


@router.post("/users/{user_id}/password", dependencies=[Depends(require_admin)])
def reset_password(user_id: int, payload: ResetIn) -> dict[str, bool]:
    auth.check_password(payload.password)
    with new_session() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "no such account")
        auth.set_password(s, user, payload.password)
    return {"reset": True}


@router.delete("/users/{user_id}")
def remove_user(user_id: int, admin: Admin) -> dict[str, bool]:
    if user_id == admin.id:
        raise HTTPException(400, "you cannot remove your own account")
    with new_session() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "no such account")
        s.exec(delete(LoginSession).where(LoginSession.user_id == user_id))
        s.delete(user)
        s.commit()
    return {"removed": True}


# --- inbox and conversations -------------------------------------------------------------------


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class StatusIn(BaseModel):
    resolved: bool


def _summary(t: Ticket, messages: int = 1) -> dict[str, Any]:
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
        "received_at": as_utc(t.received_at),
        "updated_at": as_utc(t.updated_at or t.received_at),
        "messages": messages,  # from the customer, the first one included
        "message_type": analysis.get("message_type"),
        "categories": analysis.get("categories", []),
        "risk_flags": analysis.get("risk_flags", []),
        "summary": analysis.get("summary"),
        "total_ms": t.total_ms,
    }


@router.get("/tickets", dependencies=signed_in)
def list_tickets(limit: int = 200) -> list[dict[str, Any]]:
    """Most recent activity first."""
    with new_session() as s:
        latest = func.coalesce(Ticket.updated_at, Ticket.received_at)
        tickets = s.exec(select(Ticket).order_by(latest.desc()).limit(min(limit, 500))).all()
        counts = dict(
            s.exec(
                select(CustomerMessage.ticket_id, func.count())
                .where(col(CustomerMessage.ticket_id).in_([t.id for t in tickets]))
                .group_by(CustomerMessage.ticket_id)
            ).all()
        )
        return [_summary(t, 1 + counts.get(t.id, 0)) for t in tickets]


@router.get("/tickets/{ticket_id}", dependencies=signed_in)
def get_ticket(ticket_id: int) -> dict[str, Any]:
    with new_session() as s:
        t = s.get(Ticket, ticket_id)
        if t is None:
            raise HTTPException(404, "ticket not found")
        stages = s.exec(
            select(StageRecord).where(StageRecord.ticket_id == ticket_id).order_by(StageRecord.seq)
        ).all()
        draft = s.exec(
            select(Reply).where(
                Reply.ticket_id == ticket_id, Reply.kind == "answer", Reply.status == "draft"
            )
        ).first()
        customer = s.get(Customer, t.customer_id) if t.customer_id else None
        trip = s.get(Trip, t.trip_id) if t.trip_id else None
        conversation = thread(s, t, for_customer=False)
        return {
            **_summary(t, sum(1 for m in conversation if m["from"] == "customer")),
            "body": t.body,
            "analysis": t.analysis,
            "decision": t.decision,
            "stages": [r.model_dump() for r in stages],
            "thread": conversation,
            "draft": draft.model_dump() if draft else None,
            "customer": customer.model_dump() if customer else None,
            "trip": trip.model_dump() if trip else None,
        }


@router.post("/tickets/{ticket_id}/reply")
async def reply(ticket_id: int, payload: ReplyIn, user: CurrentUser) -> dict[str, Any]:
    """Send a reply as this agent (the AI suggestion, edited or not, or their own words)."""
    try:
        sent = await asyncio.to_thread(
            state.processor.agent_reply, ticket_id, payload.body.strip(), user.name
        )
    except KeyError as exc:
        raise HTTPException(404, "ticket not found") from exc
    return {"status": sent.status, "error": sent.error}


@router.post("/tickets/{ticket_id}/status", dependencies=signed_in)
async def set_status(ticket_id: int, payload: StatusIn) -> dict[str, str]:
    try:
        ticket = await asyncio.to_thread(state.processor.set_status, ticket_id, payload.resolved)
    except KeyError as exc:
        raise HTTPException(404, "ticket not found") from exc
    return {"status": ticket.status}


@router.get("/stats", dependencies=signed_in)
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


@router.get("/events", dependencies=signed_in)
async def events(request: Request) -> StreamingResponse:
    """Live updates (Server-Sent Events). The console reads them with fetch(), so the session
    token travels in the Authorization header, never in a URL (URLs end up in logs)."""

    async def stream() -> AsyncIterator[str]:
        yield ": connected\n\n"
        async for event in state.bus.subscribe():
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
