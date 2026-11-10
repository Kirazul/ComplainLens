"""Customer accounts on the LunaGo website: sign-up, sign-in, rides, bookings, conversations.

A new account gets a starter history of past rides (``demo_data.add_starter_rides``); new rides
are booked here (``rides.py``). Writing to support does not need an account, but a ride problem
is answered only with the ride's ID, which customers find here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import col, select

from complaintlens import auth, rides
from complaintlens.api.state import state
from complaintlens.auth import CurrentCustomer
from complaintlens.demo_data import add_starter_rides, customer_trips, get_or_create_customer
from complaintlens.schemas import as_utc
from complaintlens.security import client_ip
from complaintlens.store import Customer, Ticket, Trip, new_session

router = APIRouter(prefix="/api", tags=["account"])


class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(max_length=200)
    lang: str = Field(default="en", pattern="^(en|fr)$")


class SigninIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class QuoteIn(BaseModel):
    pickup: str = Field(max_length=60)
    dropoff: str = Field(max_length=60)


class BookIn(QuoteIn):
    at: datetime  # when the ride starts (now, or up to 7 days ahead)


def _me(c: Customer) -> dict[str, Any]:
    return {"email": c.contact, "name": c.name, "language": c.language}


@router.post("/account/signup", status_code=201)
def signup(payload: SignupIn, request: Request) -> dict[str, Any]:
    state.login_limiter.check(client_ip(request))
    auth.check_password(payload.password)
    email = str(payload.email).lower()
    with new_session() as s:
        customer = s.exec(select(Customer).where(Customer.contact == email)).first()
        if customer is not None and customer.password_hash:
            raise HTTPException(409, "an account already uses this email: sign in instead")
        if customer is None:  # someone who wrote in before keeps their conversations
            customer, _ = get_or_create_customer(s, email, None, payload.lang)
        customer.name = payload.name.strip()
        customer.language = payload.lang
        customer.password_hash = auth.hash_password(payload.password)
        s.add(customer)
        if not customer_trips(s, customer.id):
            add_starter_rides(s, customer)
        s.commit()
        return {"token": auth.start_customer_session(s, customer), "customer": _me(customer)}


@router.post("/account/signin")
def signin(payload: SigninIn, request: Request) -> dict[str, Any]:
    state.login_limiter.check(client_ip(request))
    with new_session() as s:
        customer = auth.authenticate_customer(s, str(payload.email), payload.password)
        if customer is None:
            raise HTTPException(401, "wrong email or password")
        return {"token": auth.start_customer_session(s, customer), "customer": _me(customer)}


@router.post("/account/signout")
def signout(request: Request) -> dict[str, bool]:
    if token := auth.bearer(request):
        with new_session() as s:
            auth.end_customer_session(s, token)
    return {"signed_out": True}


@router.get("/account/me")
def me(customer: CurrentCustomer) -> dict[str, Any]:
    return _me(customer)


@router.get("/account/rides")
def my_rides(customer: CurrentCustomer) -> list[dict[str, Any]]:
    """Upcoming first (soonest first), then past rides (most recent first)."""
    with new_session() as s:
        views = [rides.receipt(t) for t in customer_trips(s, customer.id)]
    upcoming = sorted(
        (v for v in views if v["state"] in ("scheduled", "in_progress")),
        key=lambda v: v["started_at"],
    )
    return upcoming + [v for v in views if v["state"] not in ("scheduled", "in_progress")]


@router.post("/account/rides", status_code=201)
def book(payload: BookIn, customer: CurrentCustomer) -> dict[str, Any]:
    with new_session() as s:
        try:
            trip = rides.book(s, customer, payload.pickup, payload.dropoff, payload.at)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return rides.receipt(trip)


@router.post("/account/rides/{ride_id}/cancel")
def cancel(ride_id: str, customer: CurrentCustomer) -> dict[str, Any]:
    with new_session() as s:
        trip = s.get(Trip, ride_id)
        if trip is None or trip.customer_id != customer.id:
            raise HTTPException(404, "no such ride on your account")
        try:
            rides.cancel(s, trip)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return rides.receipt(trip)


@router.get("/account/conversations")
def my_conversations(customer: CurrentCustomer) -> list[dict[str, Any]]:
    """Every conversation started from this email address, with its tracking link key."""
    with new_session() as s:
        tickets = s.exec(
            select(Ticket)
            .where(Ticket.sender == customer.contact)
            .order_by(col(Ticket.id).desc())
            .limit(50)
        ).all()
        return [
            {
                "id": t.id,
                "number": t.number,
                "key": t.track_key,
                "status": t.status,
                "channel": t.channel,
                "received_at": as_utc(t.received_at),
                "preview": t.body[:140],
            }
            for t in tickets
        ]


@router.get("/rides/places")
def places() -> list[str]:
    return list(rides.PLACES)


@router.post("/rides/quote")
def quote(payload: QuoteIn) -> dict[str, float]:
    if payload.pickup not in rides.PLACES or payload.dropoff not in rides.PLACES:
        raise HTTPException(422, "unknown place")
    if payload.pickup == payload.dropoff:
        raise HTTPException(422, "choose two different places")
    return rides.quote(payload.pickup, payload.dropoff)
