"""Synthetic LunaGo records for demo customers (plan §5.1, D7). Labelled synthetic everywhere.

The first time a new contact writes in, we create a customer profile with recent rides and food
orders. The history is deterministic per contact (seeded by a hash of the address) and always
contains a few *genuine problems*, so that the reply can be checked against the record:

- last evening's ride was captured twice (a real duplicate charge);
- an earlier ride shows an authorisation hold of the same amount next to the real charge (looks
  like a double charge, but is not: the hold is released automatically);
- a cancelled ride charged a $5.00 fee although the driver was 7 minutes late (fee is waivable);
- a food order arrived 26 minutes late (policy: $5.00 credit) with one missing item.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from sqlmodel import Session, select

from complaintlens.schemas import utcnow
from complaintlens.store import Customer, Trip

DRIVERS = ["Marc D.", "Fatima B.", "Kevin T.", "Sophie L.", "Youssef A.", "Julie R.", "Omar K."]
VEHICLES = [
    "Toyota Camry · white",
    "Honda Civic · grey",
    "Hyundai Ioniq · blue",
    "Kia Niro · black",
]
PLACES = [
    "Old Port",
    "Plateau-Mont-Royal",
    "McGill University",
    "Montréal-Trudeau Airport",
    "Mile End",
    "Quartier Latin",
    "Griffintown",
    "Centre Bell",
    "Jean-Talon Market",
    "Verdun",
]
RESTAURANTS = ["Chez Lucie (poutine)", "Sushi Mile End", "Pho Lien", "Pizza Napoli Verdun"]


def _fare(rng: random.Random, km: float, minutes: float, surge: float) -> float:
    raw = 2.75 + 0.95 * km + 0.35 * minutes + 1.50  # Help Center HC-FARES#1
    return round(max(6.50, raw * surge), 2)


def _ride(
    rng: random.Random, customer_id: int, trip_id: str, at: datetime, surge: float = 1.0
) -> Trip:
    km = round(rng.uniform(2.5, 14.0), 1)
    minutes = round(km * rng.uniform(2.2, 3.2), 0)
    pickup, dropoff = rng.sample(PLACES, 2)
    total = _fare(rng, km, minutes, surge)
    return Trip(
        id=trip_id,
        customer_id=customer_id,
        kind="ride",
        started_at=at,
        pickup=pickup,
        dropoff=dropoff,
        driver_name=rng.choice(DRIVERS),
        vehicle=rng.choice(VEHICLES),
        distance_km=km,
        duration_min=minutes,
        surge=surge,
        total=total,
        payment_last4=f"{rng.randint(1000, 9999)}",
        charges=[{"amount": total, "type": "capture"}],
        details={"eta_promised_min": rng.randint(3, 8), "driver_late_min": 0},
    )


def create_demo_customer(
    session: Session, contact: str, name: str | None, language: str
) -> Customer:
    seed = int(hashlib.sha256(contact.lower().encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    customer = Customer(
        contact=contact.lower(),
        name=name.split()[0] if name and name.strip() else "",  # never invent a name
        language=language if language in ("en", "fr") else "en",
    )
    session.add(customer)
    session.flush()
    cid = customer.id
    assert cid is not None
    now = utcnow().replace(second=0, microsecond=0)
    base = 40000 + rng.randint(0, 9000)
    last4 = f"{rng.randint(1000, 9999)}"
    yesterday_evening = (now - timedelta(days=1)).replace(hour=21, minute=40)

    trips: list[Trip] = []
    # 1. Last evening: genuine duplicate charge (two captures).
    dup = _ride(rng, cid, f"LG-{base}", yesterday_evening, surge=1.3)
    dup.charges = [
        {"amount": dup.total, "type": "capture"},
        {"amount": dup.total, "type": "capture", "note": "duplicate capture (payment retry)"},
    ]
    trips.append(dup)
    # 2. Three days ago: authorisation hold next to the real charge (not a double charge).
    hold = _ride(rng, cid, f"LG-{base + 7}", now - timedelta(days=3, hours=4))
    hold.charges = [
        {"amount": hold.total, "type": "capture"},
        {"amount": hold.total, "type": "authorization_hold", "note": "released automatically"},
    ]
    trips.append(hold)
    # 3. Five days ago: cancelled after driver was 7 min late, but fee charged (waivable).
    cancelled = _ride(rng, cid, f"LG-{base + 13}", now - timedelta(days=5, hours=2))
    cancelled.status = "cancelled"
    cancelled.total = 5.00
    cancelled.charges = [{"amount": 5.00, "type": "capture", "note": "cancellation fee"}]
    cancelled.details = {
        "eta_promised_min": 4,
        "driver_late_min": 7,
        "cancellation_fee": 5.00,
        "cancelled_by": "rider",
        "cancelled_after_min": 6,
    }
    trips.append(cancelled)
    # 4. Two days ago: food order 26 minutes late with a missing item.
    items = [
        {"name": "Classic poutine", "price": 13.50},
        {"name": "Spring rolls (4)", "price": 7.25},
        {"name": "Iced tea", "price": 3.75},
    ]
    order_total = round(sum(i["price"] for i in items) + 3.99, 2)  # + delivery fee
    trips.append(
        Trip(
            id=f"LG-{base + 21}",
            customer_id=cid,
            kind="delivery",
            started_at=(now - timedelta(days=2)).replace(hour=19, minute=5),
            dropoff="home address (masked)",
            driver_name=rng.choice(DRIVERS),
            total=order_total,
            payment_last4=last4,
            charges=[{"amount": order_total, "type": "capture"}],
            details={
                "restaurant": rng.choice(RESTAURANTS),
                "items": items,
                "missing_items": ["Spring rolls (4)"],
                "late_min": 26,
                "delivery_fee": 3.99,
            },
        )
    )
    # 5-6. Ordinary rides, no issue.
    for i, days in enumerate((8, 12)):
        trips.append(_ride(rng, cid, f"LG-{base + 30 + i}", now - timedelta(days=days, hours=3)))
    for t in trips:
        t.payment_last4 = last4
    session.add_all(trips)
    session.flush()
    return customer


def get_or_create_customer(
    session: Session, contact: str, name: str | None, language: str
) -> tuple[Customer, bool]:
    existing = session.exec(select(Customer).where(Customer.contact == contact.lower())).first()
    if existing:
        return existing, False
    return create_demo_customer(session, contact, name, language), True


def customer_trips(session: Session, customer_id: int) -> list[Trip]:
    return list(
        session.exec(
            select(Trip).where(Trip.customer_id == customer_id).order_by(Trip.started_at.desc())
        )
    )
