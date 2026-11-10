"""Console sign-in: the console is private, accounts and roles, passwords, abuse limits."""

import pytest
from sqlalchemy import create_engine, inspect, text

from complaintlens import auth, store
from tests.conftest import ADMIN_PASSWORD, sign_in

PRIVATE = [
    ("get", "/api/tickets"),
    ("get", "/api/tickets/1"),
    ("post", "/api/tickets/1/reply"),
    ("post", "/api/tickets/1/status"),
    ("get", "/api/stats"),
    ("get", "/api/events"),
    ("get", "/api/insights"),
    ("get", "/api/experiments"),
    ("get", "/api/annotate/next"),
    ("get", "/api/users"),
]


@pytest.mark.parametrize(("method", "path"), PRIVATE)
def test_console_endpoints_need_sign_in(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert getattr(client, method)(path, headers=bad).status_code == 401


def test_sign_in_sign_out(client):
    wrong = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert wrong.status_code == 401
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert unknown.status_code == 401 and unknown.json() == wrong.json()  # nothing revealed
    headers = sign_in(client, "ADMIN ", ADMIN_PASSWORD)  # usernames are case-insensitive
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "admin"
    client.post("/api/auth/logout", headers=headers)
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_admin_manages_the_team_and_agents_cannot(client, staff):
    new = {"username": "rimel", "name": "Rimel", "password": "agent-pass-1"}
    created = client.post("/api/users", json=new, headers=staff)
    assert created.status_code == 201 and created.json()["role"] == "agent"
    assert client.post("/api/users", json=new, headers=staff).status_code == 409
    weak = {**new, "username": "sam", "password": "short"}
    assert client.post("/api/users", json=weak, headers=staff).status_code == 422

    agent = sign_in(client, "rimel", "agent-pass-1")
    assert client.get("/api/tickets", headers=agent).status_code == 200
    assert client.get("/api/users", headers=agent).status_code == 403

    rimel = created.json()["id"]
    reset = {"password": "new-agent-pass"}
    assert client.post(f"/api/users/{rimel}/password", json=reset, headers=staff).status_code == 200
    assert client.get("/api/auth/me", headers=agent).status_code == 401  # signed out everywhere
    agent = sign_in(client, "rimel", "new-agent-pass")

    me = client.get("/api/auth/me", headers=staff).json()["id"]
    assert client.delete(f"/api/users/{me}", headers=staff).status_code == 400
    assert client.delete(f"/api/users/{rimel}", headers=staff).status_code == 200
    assert client.get("/api/auth/me", headers=agent).status_code == 401


def test_change_own_password(client, staff):
    bad = {"current": "wrong", "new": "brand-new-pass"}
    assert client.post("/api/auth/password", json=bad, headers=staff).status_code == 403
    ok = client.post(
        "/api/auth/password",
        json={"current": ADMIN_PASSWORD, "new": "brand-new-pass"},
        headers=staff,
    )
    assert ok.status_code == 200
    fresh = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=staff).status_code == 401
    sign_in(client, "admin", "brand-new-pass")


def test_sign_in_attempts_are_rate_limited(client):
    codes = [
        client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_default_admin_without_a_configured_password(api_factory):
    client = api_factory(ADMIN_PASSWORD="")
    sign_in(client, "admin", "admin")


def test_passwords_are_hashed_with_a_salt():
    one, two = auth.hash_password("secret-pass"), auth.hash_password("secret-pass")
    assert one != two and "secret-pass" not in one
    assert auth.verify_password("secret-pass", one) and not auth.verify_password("other", one)
    assert not auth.verify_password("secret-pass", "not-a-hash")


def test_new_columns_are_added_to_an_existing_database(tmp_path):
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    with create_engine(url).begin() as conn:  # a reply table from an older release
        conn.execute(text("CREATE TABLE reply (id INTEGER PRIMARY KEY, ticket_id INTEGER)"))
    store.get_engine.cache_clear()
    try:
        columns = {c["name"] for c in inspect(store.get_engine(url)).get_columns("reply")}
    finally:
        store.get_engine.cache_clear()
    assert {"author", "status", "body"} <= columns
