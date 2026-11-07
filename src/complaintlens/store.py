"""Database tables (SQLModel). SQLite locally, Postgres in production: same code, ``DATABASE_URL``.

Company side (LunaGo, fictional, synthetic): Customer, Trip (rides and food orders).
ComplaintLens side: Ticket, StageRecord (one per pipeline stage: the X-ray trace), Reply.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from functools import cache
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

from complaintlens.schemas import utcnow
from complaintlens.settings import get_settings


class Customer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact: str = Field(index=True, unique=True)  # email address or chat/Telegram ID
    name: str
    language: str = "en"
    is_demo: bool = True  # profile generated automatically for a first-time sender
    created_at: datetime = Field(default_factory=utcnow)


class Trip(SQLModel, table=True):
    """A ride or a food order, with its charges (synthetic demo data)."""

    id: str = Field(primary_key=True)  # e.g. "LG-48213"
    customer_id: int = Field(foreign_key="customer.id", index=True)
    kind: str  # ride | delivery
    started_at: datetime
    status: str = "completed"  # completed | cancelled
    pickup: str = ""
    dropoff: str = ""
    driver_name: str = ""
    vehicle: str = ""
    distance_km: float = 0.0
    duration_min: float = 0.0
    surge: float = 1.0
    total: float = 0.0
    payment_last4: str = ""
    # [{"amount": 18.4, "type": "capture" | "authorization_hold", "note": "..."}]
    charges: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    # Ride: {"eta_promised_min": 4, "driver_late_min": 7, "cancellation_fee": 5.0, ...}
    # Delivery: {"restaurant": "...", "items": [...], "missing_items": [...], "late_min": 26}
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel: str
    sender: str = Field(index=True)
    sender_name: str | None = None
    subject: str | None = None
    body: str
    received_at: datetime = Field(default_factory=utcnow)
    external_id: str | None = Field(default=None, index=True)  # email Message-ID
    in_reply_to: str | None = None
    status: str = "new"  # new|processing|auto_sent|awaiting_approval|escalated|no_reply|closed
    language: str | None = None
    team: str | None = None
    priority: int | None = None
    analysis: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    decision: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    customer_id: int | None = Field(default=None, foreign_key="customer.id")
    trip_id: str | None = None
    total_ms: float | None = None
    # Secret for the customer's tracking link: only someone with the link can see the ticket.
    track_key: str = Field(default_factory=lambda: secrets.token_urlsafe(9))

    @property
    def number(self) -> str:
        return f"LG-{self.id:06d}" if self.id else "LG-??????"


class StageRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id", index=True)
    seq: int
    name: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    confidence: float | None = None
    ms: float = 0.0
    note: str | None = None


class Reply(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id", index=True)
    kind: str  # answer | acknowledgement | escalation
    body: str
    citations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    verification: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "draft"  # draft | sent | failed
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: datetime | None = None
    error: str | None = None


@cache
def get_engine(url: str | None = None):
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        from pathlib import Path

        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    SQLModel.metadata.create_all(engine)
    return engine


def new_session(url: str | None = None) -> Session:
    return Session(get_engine(url), expire_on_commit=False)
