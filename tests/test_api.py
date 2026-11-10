"""The HTTP API, offline: public endpoints, the console (signed in) and research pages."""


def test_health_reports_configuration(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["company"] == "LunaGo"
    assert body["llm"]["enabled"] is False and body["email"]["enabled"] is False


def test_form_message_is_processed_and_traced(client, staff):
    r = client.post(
        "/api/messages",
        json={"email": "Prof@Univ.tn", "name": "Prof", "body": "I was charged twice yesterday!"},
    )
    assert r.status_code == 202
    tickets = client.get("/api/tickets", headers=staff).json()  # background task already ran
    assert len(tickets) == 1 and tickets[0]["sender"] == "prof@univ.tn"
    detail = client.get(f"/api/tickets/{tickets[0]['id']}", headers=staff).json()
    assert [s["name"] for s in detail["stages"]] == [
        "normalize",
        "pii_masking",
        "language",
        "understand",
        "link",
        "respond",
    ]
    assert detail["trip"] is not None
    assert [m["from"] for m in detail["thread"]] == ["customer", "lunago"]
    assert detail["thread"][1]["kind"] == "acknowledgement"
    assert client.get("/api/stats", headers=staff).json()["tickets"] == 1


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


def test_experiments_trace_each_number_to_a_results_file(client, staff):
    rows = client.get("/api/experiments", headers=staff).json()
    assert rows, "at least the committed results should be summarised"
    for row in rows:
        assert set(row) == {"question", "claim", "value", "source"}
        assert row["source"].endswith(".json")


def test_insights_serve_timeline_and_clusters(client, staff):
    body = client.get("/api/insights", headers=staff).json()
    assert len(body["timeline"]) > 30 and len(body["clusters"]) == 30


def test_annotation_flow_over_http(client, staff):
    first = client.get("/api/annotate/next", params={"set": "pilot"}, headers=staff).json()
    item = first["item"]
    assert item["set"] == "pilot" and first["progress"]["items"]["pilot"] == 50
    labels = {
        "message_type": "complaint",
        "response_required": True,
        "urgency": "24h",
        "categories": ["delivery_order"],
        "severity": 2,
        "risk_flags": [],
    }
    ok = client.post("/api/annotate", json={"item_id": item["id"], "labels": labels}, headers=staff)
    assert ok.status_code == 200
    bad = {**labels, "severity": None}  # complaint without severity: rejected
    rejected = client.post(
        "/api/annotate", json={"item_id": item["id"], "labels": bad}, headers=staff
    )
    assert rejected.status_code == 422
    nxt = client.get("/api/annotate/next", headers=staff).json()["item"]
    assert nxt["id"] != item["id"]  # labels are saved under the signed-in account
    fr = client.post(
        "/api/annotate/items",
        json={"text": "Mon chauffeur était impoli", "lang": "fr"},
        headers=staff,
    )
    assert fr.status_code == 201 and fr.json()["set"] == "gold_fr"


def test_invalid_form_is_rejected(client):
    assert (
        client.post("/api/messages", json={"email": "not-an-email", "body": "hi"}).status_code
        == 422
    )


def test_unknown_ticket_is_404(client, staff):
    assert client.get("/api/tickets/999", headers=staff).status_code == 404
