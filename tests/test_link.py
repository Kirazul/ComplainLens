"""Stage 5: a ride problem is linked only through a ride ID on the customer's own account."""

from datetime import timedelta

import pytest

from complaintlens.demo_data import add_starter_rides, customer_trips, get_or_create_customer
from complaintlens.pipeline.link import link_stage, ride_refs, trip_facts
from complaintlens.pipeline.understand import Analysis
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.store import new_session

SENDER = "prof@univ.tn"


@pytest.fixture
def session(tmp_path):
    with new_session(f"sqlite:///{(tmp_path / 't.db').as_posix()}") as s:
        yield s


def account(session, email=SENDER):
    """A customer with an account and the starter history; returns their rides, newest first."""
    customer, _ = get_or_create_customer(session, email, "Prof", "en")
    add_starter_rides(session, customer)
    return customer_trips(session, customer.id)


def analysis(categories, message_type="complaint"):
    return Analysis(
        message_type=message_type,
        response_required=True,
        urgency="24h",
        categories=categories,
        severity=2 if message_type == "complaint" else None,
        sentiment="negative",
        entities=[],
        summary="s",
        customer_goal="g",
    )


def run(session, text, categories, message_type="complaint", sender=SENDER):
    msg = InboundMessage(channel=Channel.EMAIL, sender=sender, body=text, received_at=utcnow())
    ctx = {
        "session": session,
        "message": msg,
        "text": text,
        "language": "fr",
        "analysis": analysis(categories, message_type),
    }
    return ctx, link_stage(ctx)


def test_first_time_sender_is_a_guest_without_rides(session):
    _, result = run(session, "hello", ["other"], "request")
    assert result.output["customer"]["new_demo_profile"] is True
    assert result.output["customer"]["has_account"] is False
    _, again = run(session, "hello again", ["other"], "request")
    assert again.output["customer"]["id"] == result.output["customer"]["id"]


def test_ride_complaint_without_an_id_is_not_guessed(session):
    account(session)
    text = "J'ai été facturé deux fois pour ma course d'hier soir"
    ctx, result = run(session, text, ["fare_billing"])
    assert ctx["about_ride"] is True and ctx["trip"] is None and ctx["facts"] == []
    assert "no ride ID" in result.note


def test_ride_id_on_the_account_is_linked_and_checked(session):
    dup = next(t for t in account(session) if len(t.charges) == 2)
    text = f"Facturé deux fois hier soir pour {dup.id.lower().replace('-', '')}"
    ctx, result = run(session, text, ["fare_billing"])
    assert ctx["trip"].id == dup.id
    facts = " ".join(f["text"] for f in ctx["facts"])
    assert "really charged 2 times" in facts
    assert {"ok": True, "text": "two charge lines on record: on record"} in result.output["checks"]


def test_ride_id_of_someone_else_is_not_found(session):
    other = account(session, "someone.else@example.com")[0]
    account(session)
    ctx, result = run(session, f"Problem with {other.id}", ["fare_billing"])
    assert ctx["trip"] is None and ctx["ride_not_found"] == other.id
    assert "not on this customer's account" in result.note


def test_amount_that_matches_no_charge_is_flagged_not_overwritten(session):
    # Real case from the live demo: the customer quoted 24,50 $ but the ride shows other amounts;
    # the reply must not state the record's amount as if the customer agreed with it.
    dup = next(t for t in account(session) if len(t.charges) == 2)
    ctx, result = run(session, f"{dup.id}: facturé deux fois (24,50 $)", ["fare_billing"])
    assert {"ok": False, "text": "the amount quoted matches no charge"} in result.output["checks"]
    assert "The customer mentions $24.50" in ctx["facts"][-1]["text"]
    assert ctx["facts"][-1]["id"] == f"F{len(ctx['facts'])}"


def test_longer_route_is_on_the_record(session):
    detour = next(t for t in account(session) if t.details.get("suggested_km"))
    ctx, _ = run(session, f"The driver took a long detour on {detour.id}", ["driver_behaviour"])
    assert any("suggested route" in f["text"] for f in ctx["facts"])


def test_cancellation_facts_are_numbered_for_citation(session):
    cancelled = next(t for t in account(session) if t.status == "cancelled")
    ctx, _ = run(session, f"Unfair fee on {cancelled.id}, the driver was late", ["fare_billing"])
    ids = [f["id"] for f in trip_facts(ctx["trip"])]
    assert ids == [f"F{i}" for i in range(1, len(ids) + 1)]
    assert any("7 minutes later" in f["text"] for f in ctx["facts"])


def test_questions_and_feedback_need_no_ride(session):
    account(session)
    for text, categories, kind in (
        ("How do cancellation fees work?", ["cancellation_no_show"], "request"),
        ("I can't log in to my account", ["account_access"], "complaint"),
        ("You should let us tip in cash", ["other"], "feedback"),
    ):
        ctx, result = run(session, text, categories, kind)
        assert ctx["about_ride"] is False and ctx["trip"] is None and result.note is None, text


def test_returning_customer_read_back_from_database_still_links(tmp_path):
    # Regression: SQLite returns naive datetimes in a new session; checking must not crash.
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    with new_session(url) as s1:
        ride = account(s1, "back@univ.tn")[0]
        s1.commit()
    with new_session(url) as s2:
        text = f"charged twice yesterday on {ride.id}"
        ctx, _ = run(s2, text, ["fare_billing"], sender="back@univ.tn")
        assert ctx["trip"].id == ride.id


def test_starter_history_has_last_nights_double_charge(session):
    rides = account(session)
    dup = next(t for t in rides if len(t.charges) == 2)
    assert dup.started_at.date() == (utcnow() - timedelta(days=1)).date()
    assert len(rides) == 6


def test_ride_ids_are_normalised():
    assert ride_refs("lg12345 and LG-12345, then Lg-6789") == ["LG-12345", "LG-6789"]
