"""LunaGo customers (simulated company data, plan §5.1, D7). Labelled synthetic everywhere.

- Anyone can write in without an account: a first-time sender becomes a *guest* customer with no
  rides (a ride question then gets "which ride ID?", and an ID that is not theirs is not found).
- Creating an account on the website gives a starter history of past rides, deterministic per
  email address, with a few *genuine problems* so complaints can be checked against the record:
  - last evening's ride was captured twice (a real duplicate charge);
  - an earlier ride shows an authorisation hold next to the real charge (looks like a double
    charge, but is not: the hold is released automatically);
  - a cancelled ride was charged a $5.00 fee although the driver was 7 minutes late (waivable);
  - a ride two days ago took a much longer route than the suggested one (HC-DRIVER#2).
- New rides are booked on the website (``rides.py``).
"""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta

from sqlmodel import Session, select

from complaintlens.rides import PLACES, add_detour, add_double_charge, make_ride
from complaintlens.schemas import utcnow
from complaintlens.store import Customer, Trip


def get_or_create_customer(
    session: Session, contact: str, name: str | None, language: str
) -> tuple[Customer, bool]:
    """The customer behind an email address (or forum login); a guest if never seen before."""
    existing = session.exec(select(Customer).where(Customer.contact == contact.lower())).first()
    if existing:
        return existing, False
    customer = Customer(
        contact=contact.lower(),
        name=name.split()[0] if name and name.strip() else "",  # never invent a name
        language=language if language in ("en", "fr") else "en",
    )
    session.add(customer)
    session.flush()
    return customer, True


def add_starter_rides(session: Session, customer: Customer) -> None:
    """Past rides for a new account (see the module docstring)."""
    rng = random.Random(int(hashlib.sha256(customer.contact.encode()).hexdigest()[:8], 16))
    cid = customer.id
    assert cid is not None
    now = utcnow().replace(second=0, microsecond=0)
    base = 40000 + rng.randint(0, 9000)
    last4 = f"{rng.randint(1000, 9999)}"
    places = list(PLACES)

    def ride(offset: int, when, pickup: str | None = None, dropoff: str | None = None) -> Trip:
        a, b = rng.sample(places, 2)
        ride_id = f"LG-{base + offset}"
        while session.get(Trip, ride_id) is not None:  # another account took this number
            ride_id = f"LG-{rng.randint(10000, 99999)}"
        return make_ride(rng, cid, ride_id, when, pickup or a, dropoff or b, last4)

    # 1. Last evening: a genuine duplicate charge (two captures).
    dup = ride(0, (now - timedelta(days=1)).replace(hour=21, minute=40), "Stadium", "Shopping Mall")
    add_double_charge(dup)
    # 2. Three days ago: an authorisation hold next to the real charge (not a double charge).
    hold = ride(7, now - timedelta(days=3, hours=4))
    hold.charges = [
        {"amount": hold.total, "type": "capture"},
        {"amount": hold.total, "type": "authorization_hold", "note": "released automatically"},
    ]
    # 3. Five days ago: cancelled after the driver was 7 minutes late, but a fee was charged.
    cancelled = ride(13, now - timedelta(days=5, hours=2))
    cancelled.status, cancelled.total = "cancelled", 5.00
    cancelled.charges = [{"amount": 5.00, "type": "capture", "note": "cancellation fee"}]
    cancelled.details = {
        **cancelled.details,
        "eta_promised_min": 4,
        "driver_late_min": 7,
        "cancellation_fee": 5.00,
        "cancelled_by": "rider",
        "cancelled_after_min": 6,
    }
    # 4. Two days ago: a much longer route than the suggested one.
    detour = ride(21, (now - timedelta(days=2)).replace(hour=19, minute=5), "Old Town", "Market")
    add_detour(detour)
    # 5-6. Ordinary rides.
    normal = [ride(30 + i, now - timedelta(days=d, hours=3)) for i, d in enumerate((8, 12))]
    session.add_all([dup, hold, cancelled, detour, *normal])
    session.flush()


def customer_trips(session: Session, customer_id: int) -> list[Trip]:
    """Most recent first. "ride" also skips food orders that databases from before LunaGo became
    rides-only may hold."""
    return list(
        session.exec(
            select(Trip)
            .where(Trip.customer_id == customer_id, Trip.kind == "ride")
            .order_by(Trip.started_at.desc())
        )
    )
