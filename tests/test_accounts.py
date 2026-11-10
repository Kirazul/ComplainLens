"""Customer accounts, rides and bookings on the website, and the "which ride?" question."""

from datetime import timedelta

from complaintlens import rides
from complaintlens.schemas import utcnow
from tests.conftest import sign_in


def signup(client, email="sam@example.com", password="sam-pass-123"):
    r = client.post(
        "/api/account/signup", json={"email": email, "name": "Sam Lee", "password": password}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_signup_signin_and_starter_rides(client):
    me = signup(client)
    assert client.get("/api/account/me", headers=me).json()["email"] == "sam@example.com"
    history = client.get("/api/account/rides", headers=me).json()
    assert len(history) == 6 and all(r["state"] in ("completed", "cancelled") for r in history)
    assert "details" not in history[0]  # the receipt only, no internal notes
    again = client.post(
        "/api/account/signup",
        json={"email": "sam@example.com", "name": "X", "password": "another-pass"},
    )
    assert again.status_code == 409
    wrong = client.post(
        "/api/account/signin", json={"email": "sam@example.com", "password": "nope"}
    )
    assert wrong.status_code == 401
    ok = client.post(
        "/api/account/signin", json={"email": "SAM@example.com", "password": "sam-pass-123"}
    )
    assert ok.status_code == 200
    client.post("/api/account/signout", headers=me)
    assert client.get("/api/account/me", headers=me).status_code == 401


def test_customer_and_staff_tokens_are_separate(client, staff):
    me = signup(client)
    assert client.get("/api/tickets", headers=me).status_code == 401
    assert client.get("/api/account/me", headers=staff).status_code == 401


def test_book_a_ride_then_cancel_it(client):
    me = signup(client)
    places = client.get("/api/rides/places").json()
    q = client.post("/api/rides/quote", json={"pickup": places[0], "dropoff": places[3]}).json()
    assert q["price"] >= 6.5 and q["distance_km"] > 0
    later = (utcnow() + timedelta(hours=2)).isoformat()
    ride = client.post(
        "/api/account/rides",
        json={"pickup": places[0], "dropoff": places[3], "at": later},
        headers=me,
    ).json()
    assert ride["state"] == "scheduled" and ride["upfront_price"] == q["price"]
    assert ride["charges"] == [] and ride["total"] is None  # nothing charged before the ride
    assert client.get("/api/account/rides", headers=me).json()[0]["id"] == ride["id"]
    cancelled = client.post(f"/api/account/rides/{ride['id']}/cancel", headers=me).json()
    assert cancelled["state"] == "cancelled"
    bad = client.post(
        "/api/account/rides",
        json={"pickup": "Old Town", "dropoff": "Old Town", "at": later},
        headers=me,
    )
    assert bad.status_code == 422


def test_ride_state_follows_the_clock():
    trip = rides.make_ride(
        __import__("random").Random(1), 1, "LG-1", utcnow(), "Old Town", "Market", "1234"
    )
    start = trip.started_at
    assert rides.state(trip, start - timedelta(minutes=1)) == "scheduled"
    assert rides.state(trip, start + timedelta(minutes=1)) == "in_progress"
    assert rides.state(trip, start + timedelta(minutes=trip.duration_min + 1)) == "completed"


def test_ride_problem_without_an_id_asks_for_it_then_links(client, staff):
    me = signup(client)
    dup = next(
        r for r in client.get("/api/account/rides", headers=me).json() if len(r["charges"]) == 2
    )
    r = client.post(
        "/api/messages",
        json={
            "email": "sam@example.com",
            "body": "I was charged twice for my ride last night, refund me!",
        },
    ).json()
    view = client.get(f"/api/public/tickets/{r['id']}", params={"k": r["track_key"]}).json()
    assert view["status"] == "needs_info"
    assert "LG-12345" in view["messages"][-1]["body"]  # the question shows what an ID looks like
    client.post(
        f"/api/public/tickets/{r['id']}/messages", json={"k": r["track_key"], "body": dup["id"]}
    )
    detail = client.get(f"/api/tickets/{r['id']}", headers=staff).json()
    assert detail["trip"]["id"] == dup["id"] and detail["status"] != "needs_info"


def test_chosen_ride_is_attached_and_listed_in_my_conversations(client, staff):
    me = signup(client)
    ride = client.get("/api/account/rides", headers=me).json()[-1]["id"]
    r = client.post(
        "/api/messages",
        json={"email": "sam@example.com", "body": "The driver was rude.", "ride": ride},
    ).json()
    detail = client.get(f"/api/tickets/{r['id']}", headers=staff).json()
    assert detail["subject"] == f"Ride {ride}" and detail["trip"]["id"] == ride
    mine = client.get("/api/account/conversations", headers=me).json()
    assert mine[0]["number"] == r["number"] and mine[0]["key"] == r["track_key"]
    bad = client.post("/api/messages", json={"email": "a@b.co", "body": "hi", "ride": "drop table"})
    assert bad.status_code == 422


def test_staff_sign_in_helper_still_works(client):
    sign_in(client)


def test_acknowledgement_names_the_ride_it_checked(client):
    me = signup(client)
    ride = client.get("/api/account/rides", headers=me).json()[-1]["id"]
    r = client.post(
        "/api/messages",
        json={"email": "sam@example.com", "body": "The driver was rude to me.", "ride": ride},
    ).json()
    view = client.get(f"/api/public/tickets/{r['id']}", params={"k": r["track_key"]}).json()
    assert f"found ride {ride}" in view["messages"][-1]["body"]
