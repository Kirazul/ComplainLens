from datetime import timedelta

import pytest

from complaintlens.pipeline.link import link_stage, trip_facts
from complaintlens.pipeline.understand import Analysis
from complaintlens.schemas import Channel, InboundMessage, utcnow
from complaintlens.store import new_session


@pytest.fixture
def session(tmp_path):
    with new_session(f"sqlite:///{(tmp_path / 't.db').as_posix()}") as s:
        yield s


def analysis(categories, entities=()):
    return Analysis(
        message_type="complaint",
        response_required=True,
        urgency="24h",
        categories=categories,
        severity=2,
        sentiment="negative",
        entities=list(entities),
        summary="s",
        customer_goal="g",
    )


def run(session, text, categories, sender="prof@univ.tn"):
    msg = InboundMessage(channel=Channel.EMAIL, sender=sender, body=text, received_at=utcnow())
    ctx = {
        "session": session,
        "message": msg,
        "text": text,
        "language": "fr",
        "analysis": analysis(categories),
    }
    result = link_stage(ctx)
    return ctx, result


def test_first_time_sender_gets_a_deterministic_demo_profile(session):
    _, result = run(session, "hello", ["other"])
    assert result.output["customer"]["new_demo_profile"] is True
    _, again = run(session, "hello again", ["other"])
    assert again.output["customer"]["new_demo_profile"] is False
    assert again.output["customer"]["id"] == result.output["customer"]["id"]


def test_charged_twice_last_night_links_to_the_duplicate_charge(session):
    ctx, result = run(
        session, "J'ai été facturé deux fois pour ma course d'hier soir", ["fare_billing"]
    )
    trip = ctx["trip"]
    assert trip is not None and trip.kind == "ride"
    assert len([c for c in trip.charges if c["type"] == "capture"]) == 2
    facts = " ".join(f["text"] for f in ctx["facts"])
    assert "really charged 2 times" in facts
    assert result.output["why"]  # the link is explained


def test_late_food_order_links_to_the_delivery(session):
    ctx, _ = run(
        session,
        "My food order was super late and the spring rolls were missing",
        ["delivery_order"],
    )
    assert ctx["trip"].kind == "delivery"
    texts = [f["text"] for f in ctx["facts"]]
    assert any("26 minutes" in t for t in texts)
    assert any("Spring rolls" in t for t in texts)


def test_category_alone_is_not_evidence_for_a_trip(session):
    # Regression: a safety report with no date/amount/ref was linked to the latest ride only
    # because "ride matches the category"; unrelated double-charge facts were then shown.
    ctx, result = run(
        session,
        "The driver was texting while driving on the highway and I felt unsafe.",
        ["safety_incident"],
    )
    assert ctx["trip"] is None and ctx["facts"] == []
    assert "ask which one" in result.note


def test_vague_message_does_not_guess_a_trip(session):
    ctx, result = run(session, "Your service is bad", ["other"])
    assert ctx["trip"] is None
    assert "ask which one" in result.note


def test_trip_facts_are_numbered_for_citation(session):
    ctx, _ = run(
        session,
        "cancel fee was unfair, I cancelled because the driver was late",
        ["cancellation_no_show"],
    )
    assert ctx["trip"].status == "cancelled"
    ids = [f["id"] for f in trip_facts(ctx["trip"])]
    assert ids == [f"F{i}" for i in range(1, len(ids) + 1)]
    assert any("7 minutes later" in f["text"] for f in ctx["facts"])


def test_returning_customer_read_back_from_database_still_links(tmp_path):
    # Regression: SQLite returns naive datetimes in a new session; scoring must not crash.
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    with new_session(url) as s1:
        run(s1, "hello", ["other"], sender="back@univ.tn")
        s1.commit()
    with new_session(url) as s2:
        ctx, _ = run(s2, "charged twice yesterday", ["fare_billing"], sender="back@univ.tn")
        assert ctx["trip"] is not None


def test_old_trips_are_not_linked_by_relative_dates(session):
    # Sanity: the duplicate-charge ride is dated yesterday evening.
    ctx, _ = run(session, "charged twice yesterday", ["fare_billing"])
    assert ctx["trip"].started_at.date() == (utcnow() - timedelta(days=1)).date()
