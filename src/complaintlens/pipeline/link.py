"""Stage 5: link the message to the customer and to the ride/order it is about (plan §6.5).

Customer: exact match on the sender (email address / chat ID). Demo mode creates a profile for a
first-time sender (demo_data.py).

Trip: a transparent score, so every link can be explained in the console:
  +10 trip number quoted · +4 amount matches a charge · +3 date matches ("yesterday", "hier soir")
  +3 kind matches the category (food -> delivery, driver -> ride) · +3 the problem described is
  visible in the record ("charged twice" and two charges) · + up to 1 for recency.
Below ``MIN_SCORE``, or without specific evidence (the kind of trip alone is not evidence), we do
not guess: the reply will ask which trip the customer means.

Facts given to the reply writer are computed here by code from the record, never by the LLM.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from complaintlens.demo_data import customer_trips, get_or_create_customer
from complaintlens.pipeline.base import Context
from complaintlens.schemas import Category, StageResult
from complaintlens.store import Trip

MIN_SCORE = 3.0
_TRIP_REF = re.compile(r"\bLG-?(\d{4,6})\b", re.IGNORECASE)
_MONEY = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s?\$|\$\s?(\d+(?:[.,]\d{1,2})?)|(\d+[.,]\d{2})")
_RELATIVE_DAYS = [
    (re.compile(r"\b(yesterday|last night|hier)\b", re.I), 1),
    (
        re.compile(
            r"\b(today|this (morning|afternoon|evening)|tonight|aujourd'hui|ce (matin|soir))\b",
            re.I,
        ),
        0,
    ),
    (re.compile(r"\b(two days ago|day before yesterday|avant-hier)\b", re.I), 2),
]
_SIGNALS = {
    "double": re.compile(
        r"twice|two charges|double|charged 2|deux fois|doublement|deux d[ée]bits", re.I
    ),
    "cancel": re.compile(r"cancel|annul", re.I),
    "late": re.compile(r"\blate\b|took (forever|ages)|retard", re.I),
    "missing": re.compile(r"missing|forgot|never (got|received)|manqu|oubli|pas re[çc]u", re.I),
}
_DELIVERY_CATEGORIES = {Category.DELIVERY_ORDER}
_RIDE_CATEGORIES = {
    Category.DRIVER_BEHAVIOUR,
    Category.SAFETY_INCIDENT,
    Category.LOST_ITEM,
    Category.CANCELLATION_NO_SHOW,
    Category.ACCESSIBILITY,
}


def _amounts(text: str) -> set[float]:
    out = set()
    for groups in _MONEY.findall(text):
        for g in groups:
            if g:
                out.add(round(float(g.replace(",", ".")), 2))
    return out


def _utc(dt: datetime) -> datetime:
    """SQLite drops time zones on read; all our datetimes are stored in UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def score_trip(
    trip: Trip, text: str, categories: list[Category], now: datetime
) -> tuple[float, list[str]]:
    score, why = 0.0, []
    now, started = _utc(now), _utc(trip.started_at)
    refs = {f"LG-{m}" for m in _TRIP_REF.findall(text)}
    if trip.id.upper() in refs:
        score += 10
        why.append("trip number quoted (+10)")
    charge_amounts = {round(c["amount"], 2) for c in trip.charges} | {round(trip.total, 2)}
    if _amounts(text) & charge_amounts:
        score += 4
        why.append("amount matches a charge (+4)")
    for pattern, days in _RELATIVE_DAYS:
        if pattern.search(text) and started.date() == (now - timedelta(days=days)).date():
            score += 3
            why.append(f"date matches '{pattern.search(text).group()}' (+3)")
            break
    cats = set(categories)
    if (cats & _DELIVERY_CATEGORIES and trip.kind == "delivery") or (
        cats & _RIDE_CATEGORIES and trip.kind == "ride"
    ):
        score += 3
        why.append(f"{trip.kind} matches the category (+3)")
    if _SIGNALS["double"].search(text) and len(trip.charges) > 1:
        score += 3
        why.append("two charge lines on record, as described (+3)")
    if _SIGNALS["cancel"].search(text) and trip.status == "cancelled":
        score += 3
        why.append("cancelled trip, as described (+3)")
    if trip.kind == "delivery" and (
        (_SIGNALS["late"].search(text) and trip.details.get("late_min", 0) > 0)
        or (_SIGNALS["missing"].search(text) and trip.details.get("missing_items"))
    ):
        score += 3
        why.append("delivery problem visible in the record (+3)")
    age_days = max((now - started).total_seconds() / 86400, 0)
    score += round(1 / (1 + age_days), 2)
    return round(score, 2), why


def _money(x: float) -> str:
    return f"${x:,.2f}"


def trip_facts(trip: Trip) -> list[dict[str, str]]:
    """Plain-language facts about the record, numbered F1, F2... for citation."""
    when = trip.started_at.strftime("%Y-%m-%d at %H:%M")
    facts: list[str] = []
    if trip.kind == "ride":
        facts.append(
            f"Ride {trip.id} on {when} from {trip.pickup} to {trip.dropoff}, "
            f"driver {trip.driver_name} ({trip.vehicle}); status: {trip.status}."
        )
        if trip.status == "completed":
            surge = f" with surge x{trip.surge:g}" if trip.surge > 1 else ""
            facts.append(f"Fare charged for the ride: {_money(trip.total)}{surge}.")
    else:
        d = trip.details
        items = ", ".join(f"{i['name']} ({_money(i['price'])})" for i in d.get("items", []))
        facts.append(
            f"Food order {trip.id} on {when} from {d.get('restaurant')}: {items}; "
            f"delivery fee {_money(d.get('delivery_fee', 0))}; total {_money(trip.total)}."
        )
    lines = ", ".join(
        f"{_money(c['amount'])} ({c['type'].replace('_', ' ')}"
        + (f": {c['note']}" if c.get("note") else "")
        + ")"
        for c in trip.charges
    )
    facts.append(f"Payment lines on the card ending {trip.payment_last4}: {lines}.")
    captures = [c for c in trip.charges if c["type"] == "capture"]
    if len(captures) > 1:
        facts.append(
            f"The customer was really charged {len(captures)} times; the duplicate amount is "
            f"{_money(captures[-1]['amount'])}."
        )
    if any(c["type"] == "authorization_hold" for c in trip.charges):
        facts.append("One payment line is a temporary authorization hold, not a real charge.")
    d = trip.details
    if trip.status == "cancelled" and d.get("cancellation_fee"):
        facts.append(
            f"Cancelled by the {d.get('cancelled_by')} {d.get('cancelled_after_min')} minutes "
            f"after acceptance; a {_money(d['cancellation_fee'])} cancellation fee was charged; "
            f"the driver was {d.get('driver_late_min')} minutes later than the promised arrival "
            "time."
        )
    if trip.kind == "delivery":
        if d.get("late_min"):
            facts.append(
                f"The order arrived {d['late_min']} minutes after the latest estimated time."
            )
        missing = d.get("missing_items") or []
        prices = {i["name"]: i["price"] for i in d.get("items", [])}
        for m in missing:
            facts.append(
                f"Item reported missing by the restaurant check: {m} ({_money(prices.get(m, 0))})."
            )
    return [{"id": f"F{i}", "text": t} for i, t in enumerate(facts, start=1)]


def _is_weak(reason: str) -> bool:
    """'ride matches the category' is a tie-breaker, not evidence that this is the trip."""
    return "matches the category" in reason


def link_stage(ctx: Context) -> StageResult:
    session, msg = ctx["session"], ctx["message"]
    analysis = ctx.get("analysis")
    customer, created = get_or_create_customer(
        session, msg.sender, msg.sender_name, ctx.get("language", "en")
    )
    trips = customer_trips(session, customer.id)
    text = ctx["text"]
    categories = list(analysis.categories) if analysis else []
    entity_text = " ".join(e.text for e in analysis.entities) if analysis else ""
    scored = sorted(
        ((t, *score_trip(t, f"{text} {entity_text}", categories, msg.received_at)) for t in trips),
        key=lambda x: -x[1],
    )
    # A link needs specific evidence (trip number, amount, date or a matching problem in the
    # record); the trip kind and recency only break ties. Otherwise we ask instead of guessing.
    best = (
        scored[0]
        if scored and scored[0][1] >= MIN_SCORE and any(not _is_weak(w) for w in scored[0][2])
        else None
    )
    ctx["customer"] = customer
    ctx["trip"] = best[0] if best else None
    ctx["facts"] = trip_facts(best[0]) if best else []
    return StageResult(
        name="link",
        output={
            "customer": {"id": customer.id, "name": customer.name, "new_demo_profile": created},
            "trip": best[0].id if best else None,
            "why": best[2] if best else [],
            "candidates": [{"trip": t.id, "kind": t.kind, "score": s} for t, s, _ in scored[:4]],
            "facts": ctx["facts"],
        },
        confidence=min(best[1] / 10, 1.0) if best else 0.0,
        note=None if best else "no trip matched with confidence: the reply will ask which one",
    )


link_stage.stage_name = "link"  # type: ignore[attr-defined]
