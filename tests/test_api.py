import pytest
from fastapi.testclient import TestClient

from complaintlens import store
from complaintlens.settings import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setenv("LLM_API_KEY", "")  # offline: classical fallback, no network
    monkeypatch.setenv("EMAIL_ADDRESS", "")
    get_settings.cache_clear()
    store.get_engine.cache_clear()
    from complaintlens.api import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    store.get_engine.cache_clear()


def test_health_reports_configuration(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["company"] == "LunaGo"
    assert body["llm"]["enabled"] is False and body["email"]["enabled"] is False


def test_form_message_is_processed_and_traced(client):
    r = client.post(
        "/api/messages",
        json={"email": "Prof@Univ.tn", "name": "Prof", "body": "I was charged twice yesterday!"},
    )
    assert r.status_code == 202
    tickets = client.get("/api/tickets").json()  # background task ran before the response
    assert len(tickets) == 1 and tickets[0]["sender"] == "prof@univ.tn"
    detail = client.get(f"/api/tickets/{tickets[0]['id']}").json()
    assert [s["name"] for s in detail["stages"]] == [
        "normalize",
        "pii_masking",
        "language",
        "understand",
        "link",
        "respond",
    ]
    assert detail["trip"] is not None
    assert detail["replies"] and detail["replies"][0]["kind"] == "acknowledgement"
    assert client.get("/api/stats").json()["tickets"] == 1


def test_customer_can_track_only_with_the_secret_key(client):
    r = client.post("/api/messages", json={"email": "a@b.co", "body": "Where is my lost phone?"})
    ticket = r.json()
    assert ticket["number"].startswith("LG-")
    view = client.get(f"/api/public/tickets/{ticket['id']}", params={"k": ticket["track_key"]})
    assert view.status_code == 200
    body = view.json()
    assert [p["name"] for p in body["phases"]] == ["received", "understood", "routed", "answered"]
    # Offline the ticket waits for an agent: routed, but not answered yet (an acknowledgement
    # is not an answer).
    assert body["status"] == "awaiting_approval"
    assert [p["done"] for p in body["phases"]] == [True, True, True, False]
    assert "analysis" not in body and "sender" not in body  # no internals for customers
    wrong = client.get(f"/api/public/tickets/{ticket['id']}", params={"k": "guess"})
    assert wrong.status_code == 404


def test_help_center_endpoint_serves_both_languages(client):
    fr = client.get("/api/help", params={"lang": "fr"}).json()
    assert len(fr) == 9 and fr[0]["sections"][0]["id"].startswith("HC-")
    assert any(a["title"].startswith("Objets perdus") for a in fr)


def test_invalid_form_is_rejected(client):
    assert (
        client.post("/api/messages", json={"email": "not-an-email", "body": "hi"}).status_code
        == 422
    )


def test_unknown_ticket_is_404(client):
    assert client.get("/api/tickets/999").status_code == 404
