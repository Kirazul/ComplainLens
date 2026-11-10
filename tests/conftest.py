"""Shared fixtures: an offline API (no LLM, no email, BM25 retrieval) on a fresh database."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from complaintlens import store
from complaintlens.settings import get_settings

ADMIN_PASSWORD = "admin-pass-123"


@pytest.fixture
def api_factory(tmp_path, monkeypatch) -> Iterator[Callable[..., TestClient]]:
    """Start the API with extra environment variables, e.g. ``api_factory(CHANNEL_TOKEN="x")``."""
    clients: list[TestClient] = []

    def start(**env: str) -> TestClient:
        settings = {
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'api.db').as_posix()}",
            "LLM_API_KEY": "",  # offline: classical fallback, no network
            "EMAIL_ADDRESS": "",
            "EMAIL_INBOX": "agentmail",
            "CHANNEL_TOKEN": "",
            "RETRIEVAL": "bm25",  # no embedding model download
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            **env,
        }
        for key, value in settings.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        store.get_engine.cache_clear()
        from complaintlens.api import app

        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)
    get_settings.cache_clear()
    store.get_engine.cache_clear()


@pytest.fixture
def client(api_factory) -> TestClient:
    return api_factory()


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD) -> dict:
    """Authorization header of a fresh session."""
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def staff(client) -> dict:
    return sign_in(client)
