"""Core data types shared by every part of ComplaintLens (single source of truth, plan §11)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    """SQLite gives back naive datetimes; every time we store is UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class Channel(StrEnum):
    EMAIL = "email"  # the support inbox
    WEB = "web"  # the contact form on the website
    CHAT = "chat"  # the live chat on the website
    REVIEW = "review"  # an in-app trip rating with a comment
    FORUM = "forum"  # a public post on the community forum (GitHub Discussions)


class MessageType(StrEnum):
    COMPLAINT = "complaint"
    REQUEST = "request"
    FEEDBACK = "feedback"
    PRAISE = "praise"
    SPAM = "spam_or_irrelevant"


class Urgency(StrEnum):
    IMMEDIATE = "immediate"
    WITHIN_24H = "24h"
    STANDARD = "standard"


class Category(StrEnum):
    FARE_BILLING = "fare_billing"
    DRIVER_BEHAVIOUR = "driver_behaviour"
    SAFETY_INCIDENT = "safety_incident"
    LOST_ITEM = "lost_item"
    CANCELLATION_NO_SHOW = "cancellation_no_show"
    DELIVERY_ORDER = "delivery_order"
    APP_TECHNICAL = "app_technical"
    ACCOUNT_ACCESS = "account_access"
    PROMOTIONS_CREDITS = "promotions_credits"
    ACCESSIBILITY = "accessibility"
    OTHER = "other"


class RiskFlag(StrEnum):
    SAFETY = "safety"
    INJURY = "injury"
    HARASSMENT_DISCRIMINATION = "harassment_discrimination"
    LEGAL_THREAT = "legal_threat"
    FRAUD_ACCOUNT_TAKEOVER = "fraud_account_takeover"
    MEDIA_THREAT = "media_threat"
    VULNERABLE_PERSON = "vulnerable_person"


class Action(StrEnum):
    AUTO_SEND = "auto_send"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"
    NO_REPLY = "no_reply"


class InboundMessage(BaseModel):
    """A customer message as received, whatever the channel."""

    channel: Channel
    sender: str  # email address, or "forum:<login>" for forum posts
    sender_name: str | None = None
    subject: str | None = None
    body: str
    received_at: datetime = Field(default_factory=utcnow)
    external_id: str | None = None  # e.g. the email Message-ID or the forum post ID
    in_reply_to: str | None = None  # e.g. the email In-Reply-To header


class StageResult(BaseModel):
    """What one pipeline stage did: shown stage by stage in the console's X-ray view."""

    name: str
    status: str = "ok"  # ok | skipped | error
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    ms: float = 0.0
    note: str | None = None
