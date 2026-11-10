"""Stage 5: link the message to the customer and, for a ride problem, to the ride (plan §6.5).

Customer: exact match on the sender (email address or forum login). No account is needed to write
in; a first-time sender becomes a guest customer (demo_data.py).

Ride: only a complaint about a ride (a charge, a driver, a lost item, a cancellation, safety,
accessibility), or a message that quotes a ride ID, needs one. The ride is identified by its ID
(LG-12345) and only if that ride is on the customer's own account: never guessed from "last
night" or an amount. Without a valid ID the reply asks for it (respond.py). Questions, feedback
and app or account problems need no ride.

Once the ride is known, its record is checked against what the customer says (amount, date,
problem), and the facts given to the reply writer are computed here by code, never by the LLM.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from complaintlens.demo_data import customer_trips, get_or_create_customer
from complaintlens.pipeline.base import Context
from complaintlens.schemas import Category, MessageType, StageResult, as_utc
from complaintlens.store import Trip

# Complaint topics that concern one particular ride.
RIDE_TOPICS = {
    Category.FARE_BILLING,
    Category.DRIVER_BEHAVIOUR,
    Category.SAFETY_INCIDENT,
    Category.LOST_ITEM,
    Category.CANCELLATION_NO_SHOW,
    Category.ACCESSIBILITY,
}

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
    "route": re.compile(
        r"detour|longer route|long way|wrong way|d[ée]tour|plus long|mauvais chemin", re.I
    ),
}


def _amounts(text: str) -> set[float]:
    out = set()
    for groups in _MONEY.findall(text):
        for g in groups:
            if g:
                out.add(round(float(g.replace(",", ".")), 2))
    return out


def _charge_amounts(trip: Trip) -> set[float]:
    return {round(c["amount"], 2) for c in trip.charges} | {round(trip.total, 2)}


def ride_refs(text: str) -> list[str]:
    """Ride IDs quoted in the text, normalised ("lg12345" -> "LG-12345"), in order."""
    return list(dict.fromkeys(f"LG-{m}" for m in _TRIP_REF.findall(text)))


def checks(trip: Trip, text: str, now: datetime) -> list[dict[str, object]]:
    """What the customer says, checked against the ride's record (shown to the agent)."""
    out: list[dict[str, object]] = []
    now, started = as_utc(now), as_utc(trip.started_at)
    quoted = _amounts(text)
    if quoted & _charge_amounts(trip):
        out.append({"ok": True, "text": "the amount quoted matches a charge"})
    elif quoted:
        out.append({"ok": False, "text": "the amount quoted matches no charge"})
    for pattern, days in _RELATIVE_DAYS:
        if match := pattern.search(text):
            same = started.date() == (now - timedelta(days=days)).date()
            verdict = "matches" if same else "does not match"
            out.append({"ok": same, "text": f"'{match.group()}' {verdict} the ride's date"})
            break
    d = trip.details
    described = [
        ("double", len(trip.charges) > 1, "two charge lines on record"),
        ("cancel", trip.status == "cancelled", "the ride was cancelled"),
        ("late", d.get("driver_late_min", 0) > 0, "the driver was late"),
        ("route", bool(d.get("suggested_km")), "a longer route than suggested"),
    ]
    for signal, on_record, label in described:
        if _SIGNALS[signal].search(text):
            out.append(
                {
                    "ok": on_record,
                    "text": f"{label}: {'on record' if on_record else 'not on record'}",
                }
            )
    return out


def _money(x: float) -> str:
    return f"${x:,.2f}"


def trip_facts(trip: Trip) -> list[dict[str, str]]:
    """Plain-language facts about the record, numbered F1, F2... for citation."""
    when = trip.started_at.strftime("%Y-%m-%d at %H:%M")
    facts: list[str] = [
        f"Ride {trip.id} on {when} from {trip.pickup} to {trip.dropoff}, "
        f"driver {trip.driver_name} ({trip.vehicle}); status: {trip.status}."
    ]
    if trip.status == "completed":
        surge = f" with surge x{trip.surge:g}" if trip.surge > 1 else ""
        facts.append(f"Fare charged for the ride: {_money(trip.total)}{surge}.")
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
    if d.get("suggested_km"):
        facts.append(
            f"Route driven: {trip.distance_km:g} km; suggested route: {d['suggested_km']:g} km. "
            f"The fare for the suggested route would have been {_money(d['suggested_fare'])}."
        )
    return [{"id": f"F{i}", "text": t} for i, t in enumerate(facts, start=1)]


def link_stage(ctx: Context) -> StageResult:
    session, msg = ctx["session"], ctx["message"]
    analysis = ctx.get("analysis")
    customer, created = get_or_create_customer(
        session, msg.sender, msg.sender_name, ctx.get("language", "en")
    )
    text = ctx["text"]
    refs = ride_refs(text)
    complaint = analysis is not None and analysis.message_type == MessageType.COMPLAINT
    about_ride = bool(refs) or (complaint and bool(set(analysis.categories) & RIDE_TOPICS))
    rides = {t.id: t for t in customer_trips(session, customer.id)} if about_ride else {}
    trip = next((rides[r] for r in refs if r in rides), None)
    not_theirs = [r for r in refs if r not in rides]
    ctx.update(
        customer=customer,
        trip=trip,
        about_ride=about_ride,
        ride_not_found=not_theirs[0] if about_ride and trip is None and not_theirs else None,
        facts=trip_facts(trip) if trip else [],
    )
    if trip and (unmatched := sorted(_amounts(text) - _charge_amounts(trip))):
        # Never let the reply state the record's amount as if the customer had agreed with it.
        ctx["facts"].append(
            {
                "id": f"F{len(ctx['facts']) + 1}",
                "text": f"The customer mentions {', '.join(_money(a) for a in unmatched)}, which "
                "matches no payment line on this record: confirm the amount with the customer "
                "before promising anything about it.",
            }
        )
    if trip is not None or not about_ride:
        note = None
    elif ctx["ride_not_found"]:
        note = f"{ctx['ride_not_found']} is not on this customer's account: the reply asks again"
    else:
        note = "no ride ID given: the reply asks for it"
    return StageResult(
        name="link",
        output={
            "customer": {
                "id": customer.id,
                "name": customer.name,
                "new_demo_profile": created,
                "has_account": bool(customer.password_hash),
                "rides": len(rides),
            },
            "about_ride": about_ride,
            "ride_ids_quoted": refs,
            "trip": trip.id if trip else None,
            "checks": checks(trip, text, msg.received_at) if trip else [],
            "facts": ctx["facts"],
        },
        confidence=1.0 if trip else None,
        note=note,
    )


link_stage.stage_name = "link"  # type: ignore[attr-defined]
