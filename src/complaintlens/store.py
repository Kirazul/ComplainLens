"""Database tables (SQLModel). SQLite locally, Postgres in production: same code, ``DATABASE_URL``.

Company side (LunaGo, fictional, synthetic): Customer, Trip (a ride).
ComplaintLens side: Ticket, CustomerMessage (the customer's follow-ups in the same conversation),
StageRecord (one per pipeline stage: the X-ray trace), Reply (what LunaGo sent or drafted).
Staff side: User, LoginSession (console sign-in). Customer accounts: Customer.password_hash,
CustomerSession (website sign-in).

New columns on existing tables are added at startup (``_add_missing_columns``): the deployed
database keeps its data across releases without a migration tool.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from functools import cache
from typing import Any

from sqlalchemy import JSON, Column, inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine

from complaintlens.schemas import utcnow
from complaintlens.settings import get_settings


class Customer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact: str = Field(index=True, unique=True)  # email address, or "forum:<login>"
    name: str
    language: str = "en"
    is_demo: bool = True  # profile generated automatically for a first-time sender
    created_at: datetime = Field(default_factory=utcnow)
    # Set when the customer creates an account on the website; None for a guest who only wrote in.
    password_hash: str | None = None


class Trip(SQLModel, table=True):
    """A ride, with its charges (synthetic demo data)."""

    id: str = Field(primary_key=True)  # e.g. "LG-48213"
    customer_id: int = Field(foreign_key="customer.id", index=True)
    kind: str = "ride"  # always "ride" (older databases may hold food orders: ignored)
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
    # Longer route: {"suggested_km": 6.2, "suggested_fare": 14.1}
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
    thread_id: str | None = Field(default=None, index=True)  # email conversation (AgentMail)
    in_reply_to: str | None = None
    # processing | auto_send | awaiting_approval | escalated | no_reply | answered | closed
    status: str = "new"
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
    # Last time the customer or the team wrote (the inbox is sorted by it). None on old rows.
    updated_at: datetime | None = Field(default_factory=utcnow)

    @property
    def number(self) -> str:
        return f"LG-{self.id:06d}" if self.id else "LG-??????"


class CustomerMessage(SQLModel, table=True):
    """A follow-up from the customer in an existing conversation (the first message is
    ``Ticket.body``)."""

    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id", index=True)
    body: str
    received_at: datetime = Field(default_factory=utcnow)
    external_id: str | None = Field(default=None, index=True)  # the email's Message-ID, if any


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
    status: str = "draft"  # draft | queued | sent | failed
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: datetime | None = None
    error: str | None = None
    author: str | None = None  # the agent who sent it; None = sent automatically


class User(SQLModel, table=True):
    """A support agent or administrator who signs in to the console."""

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    name: str
    role: str = "agent"  # agent | admin (admins also manage the team)
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class LoginSession(SQLModel, table=True):
    """A signed-in browser. Only a hash of the token is stored."""

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


class CustomerSession(SQLModel, table=True):
    """A browser signed in to a customer account on the website (separate from staff)."""

    token_hash: str = Field(primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    expires_at: datetime


class AnnotationItem(SQLModel, table=True):
    """A message to label for the gold sets (eval/gold/*.jsonl, or authored in the console)."""

    id: str = Field(primary_key=True)  # e.g. "en-0001", "fr-0012"
    set: str = Field(index=True)  # pilot | gold_en | gold_fr
    lang: str
    text: str
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Annotation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(foreign_key="annotationitem.id", index=True)
    annotator: str = Field(index=True)
    labels: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


@cache
def get_engine(url: str | None = None):
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        from pathlib import Path

        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine) -> None:
    """Add columns that a newer release declares to tables created by an older one (nullable,
    so existing rows stay valid). Renames and removals are not handled: avoid them."""
    existing = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not existing.has_table(table.name):
                continue
            present = {c["name"] for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name not in present:
                    kind = column.type.compile(dialect=engine.dialect)
                    conn.execute(
                        text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')
                    )


def new_session(url: str | None = None) -> Session:
    return Session(get_engine(url), expire_on_commit=False)
