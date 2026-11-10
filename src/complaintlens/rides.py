"""LunaGo's rides (simulated company data, labelled synthetic everywhere).

Customers book a ride on the website: from one place in the city to another, now or later. The
price is quoted upfront with the Help Center formula (HC-FARES#1). A ride's state follows the
clock: scheduled until its start time, on its way for its duration, then completed (or
cancelled, by the customer before it starts).

As in real life, some rides go wrong. The outcome is fixed at booking (seeded by the ride ID, so
it never changes) and shows on the receipt once the ride is over:
- about 1 in 8: the payment is captured twice (a payment retry);
- about 1 in 8: the driver takes a much longer route, so the final price exceeds the upfront
  price (policy HC-DRIVER#2: the fare is adjusted to the suggested route).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from complaintlens.schemas import as_utc, utcnow
from complaintlens.store import Customer, Trip

# Places in the city and their coordinates (latitude, longitude): distances stay realistic.
PLACES: dict[str, tuple[float, float]] = {
    "Airport": (45.4706, -73.7408),
    "Central Station": (45.4996, -73.5664),
    "Old Town": (45.5075, -73.5540),
    "University": (45.5048, -73.5772),
    "Stadium": (45.5580, -73.5519),
    "Market": (45.5363, -73.6147),
    "Hospital": (45.4970, -73.5880),
    "Park": (45.5220, -73.5800),
    "Shopping Mall": (45.4580, -73.5700),
    "Harbour": (45.4920, -73.5450),
}
DRIVERS = ["Marc D.", "Fatima B.", "Kevin T.", "Sophie L.", "Youssef A.", "Julie R.", "Omar K."]
VEHICLES = [
    "Toyota Camry · white",
    "Honda Civic · grey",
    "Hyundai Ioniq · blue",
    "Kia Niro · black",
]
ROAD_FACTOR = 1.35  # streets are longer than the straight line
CITY_KMH = 24.0
MAX_DAYS_AHEAD = 7


def fare(km: float, minutes: float, surge: float = 1.0) -> float:
    """Help Center HC-FARES#1: $2.75 base + $0.95/km + $0.35/min + $1.50 booking fee, min $6.50."""
    return round(max(6.50, (2.75 + 0.95 * km + 0.35 * minutes + 1.50) * surge), 2)


def route(pickup: str, dropoff: str) -> tuple[float, float]:
    """Suggested route between two places: (km, minutes)."""
    (lat1, lon1), (lat2, lon2) = PLACES[pickup], PLACES[dropoff]
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    km = round(6371 * 2 * math.asin(math.sqrt(h)) * ROAD_FACTOR, 1)
    return km, round(km / CITY_KMH * 60 + 3)  # + pickup and drop-off time


def quote(pickup: str, dropoff: str) -> dict[str, float]:
    km, minutes = route(pickup, dropoff)
    return {"distance_km": km, "duration_min": minutes, "price": fare(km, minutes)}


def make_ride(
    rng: random.Random,
    customer_id: int,
    ride_id: str,
    at: datetime,
    pickup: str,
    dropoff: str,
    last4: str,
) -> Trip:
    """A completed ride on the suggested route, charged its upfront price."""
    km, minutes = route(pickup, dropoff)
    total = fare(km, minutes)
    return Trip(
        id=ride_id,
        customer_id=customer_id,
        kind="ride",
        started_at=at,
        pickup=pickup,
        dropoff=dropoff,
        driver_name=rng.choice(DRIVERS),
        vehicle=rng.choice(VEHICLES),
        distance_km=km,
        duration_min=minutes,
        total=total,
        payment_last4=last4,
        charges=[{"amount": total, "type": "capture"}],
        details={"upfront_price": total, "eta_promised_min": rng.randint(3, 8)},
    )


def add_double_charge(trip: Trip) -> None:
    trip.charges = [
        {"amount": trip.total, "type": "capture"},
        {"amount": trip.total, "type": "capture", "note": "duplicate capture (payment retry)"},
    ]


def add_detour(trip: Trip) -> None:
    """The driver took a longer route: charged for it, the suggested route kept on record."""
    suggested_km, suggested_min = trip.distance_km, trip.duration_min
    trip.distance_km = round(suggested_km * 1.6, 1)
    trip.duration_min = round(suggested_min * 1.5)
    trip.total = fare(trip.distance_km, trip.duration_min)
    trip.charges = [{"amount": trip.total, "type": "capture"}]
    trip.details = {
        **trip.details,
        "suggested_km": suggested_km,
        "suggested_fare": fare(suggested_km, suggested_min),
    }


def new_ride_id(session: Session, rng: random.Random) -> str:
    while True:
        ride_id = f"LG-{rng.randint(10000, 99999)}"
        if session.get(Trip, ride_id) is None:
            return ride_id


def book(session: Session, customer: Customer, pickup: str, dropoff: str, at: datetime) -> Trip:
    if pickup not in PLACES or dropoff not in PLACES or pickup == dropoff:
        raise ValueError("choose two different places")
    now = utcnow()
    at = as_utc(at)
    if at < now - timedelta(minutes=5) or at > now + timedelta(days=MAX_DAYS_AHEAD):
        raise ValueError(f"choose a time between now and {MAX_DAYS_AHEAD} days from now")
    ride_id = new_ride_id(session, random.Random())
    rng = random.Random(ride_id)  # the outcome is fixed by the ride ID
    last4 = customer_card(session, customer)
    trip = make_ride(rng, customer.id, ride_id, max(at, now), pickup, dropoff, last4)
    outcome = rng.random()
    if outcome < 0.125:
        add_double_charge(trip)
    elif outcome < 0.25:
        add_detour(trip)
    session.add(trip)
    session.commit()
    return trip


def cancel(session: Session, trip: Trip) -> None:
    """Free before the ride starts (HC-CANCEL#1)."""
    if state(trip) != "scheduled":
        raise ValueError("only a scheduled ride can be cancelled")
    trip.status, trip.total, trip.charges = "cancelled", 0.0, []
    session.add(trip)
    session.commit()


def customer_card(session: Session, customer: Customer) -> str:
    """The customer's card: the one on their rides, or a new one (seeded by the account)."""
    first = session.exec(select(Trip).where(Trip.customer_id == customer.id)).first()
    if first and first.payment_last4:
        return first.payment_last4
    return f"{random.Random(customer.contact).randint(1000, 9999)}"


def state(trip: Trip, now: datetime | None = None) -> str:
    """scheduled | in_progress | completed | cancelled, by the clock."""
    if trip.status == "cancelled":
        return "cancelled"
    now, start = now or utcnow(), as_utc(trip.started_at)
    if now < start:
        return "scheduled"
    if now < start + timedelta(minutes=trip.duration_min or 0):
        return "in_progress"
    return "completed"


def receipt(trip: Trip) -> dict[str, Any]:
    """A ride as the customer sees it. Charges appear once the ride is over."""
    current = state(trip)
    over = current in ("completed", "cancelled")
    return {
        "id": trip.id,
        "state": current,
        "started_at": as_utc(trip.started_at),
        "pickup": trip.pickup,
        "dropoff": trip.dropoff,
        "driver": trip.driver_name,
        "vehicle": trip.vehicle,
        "distance_km": trip.distance_km if over else None,
        "upfront_price": trip.details.get("upfront_price", trip.total),
        "total": trip.total if over else None,
        "card": trip.payment_last4,
        "charges": [
            {"amount": c["amount"], "pending": c["type"] == "authorization_hold"}
            for c in trip.charges
        ]
        if over
        else [],
    }
