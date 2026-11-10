"""Support inbox on mail.tm: a free mailbox created through a public API, with no sign-up.

mail.tm receives only (it has no SMTP), so with this inbox replies are read on the tracking page
and in the console. Each message's raw source is downloaded and parsed exactly like an IMAP
message, so loop protection and normalisation are the same for both inboxes.

Create the inbox once with ``uv run complaintlens inbox-create <name>``.

mail.tm limits request rates (HTTP 429), so the login token is reused until it expires and the
caller polls at a modest pace and backs off when told to.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime

import httpx
from imap_tools import MailMessage

from complaintlens.channels.email import Fetched, should_skip, to_inbound
from complaintlens.settings import Settings, get_settings

log = logging.getLogger(__name__)
_tokens: dict[str, str] = {}  # address -> login token, reused across polls


def _client(s: Settings) -> httpx.Client:
    return httpx.Client(base_url=s.mailtm_api, timeout=30)


def _token(client: httpx.Client, address: str, password: str) -> str:
    r = client.post("/token", json={"address": address, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def create_inbox(name: str, settings: Settings | None = None) -> tuple[str, str]:
    """Create ``name@<current mail.tm domain>`` with a random password; return both."""
    s = settings or get_settings()
    with _client(s) as client:
        domains = client.get("/domains").json()["hydra:member"]
        domain = next(d["domain"] for d in domains if d["isActive"])
        password = secrets.token_urlsafe(18)
        r = client.post("/accounts", json={"address": f"{name}@{domain}", "password": password})
        r.raise_for_status()
        address = r.json()["address"]  # mail.tm normalises the name (it drops dots, for example)
        _token(client, address, password)  # proves the credentials work
    return address, password


def check_login(settings: Settings | None = None) -> None:
    """Raise if the configured inbox cannot be logged into."""
    s = settings or get_settings()
    with _client(s) as client:
        _token(client, s.email_address, s.email_password)


def _authorize(client: httpx.Client, s: Settings, refresh: bool = False) -> None:
    if refresh or s.email_address not in _tokens:
        _tokens[s.email_address] = _token(client, s.email_address, s.email_password)
    client.headers["Authorization"] = f"Bearer {_tokens[s.email_address]}"


def _get(client: httpx.Client, s: Settings, path: str, **kwargs) -> httpx.Response:
    r = client.get(path, **kwargs)
    if r.status_code == 401:  # token expired: log in again once
        _authorize(client, s, refresh=True)
        r = client.get(path, **kwargs)
    r.raise_for_status()
    return r


def fetch_new_messages(settings: Settings | None = None) -> list[Fetched]:
    """Unseen messages to process; skipped ones (automatic replies, our own) are marked seen.

    Raises ``httpx.HTTPStatusError`` (e.g. 429 when rate-limited): the caller retries later.
    """
    s = settings or get_settings()

    def mark_seen(message_id: str) -> None:
        with _client(s) as c:
            _authorize(c, s)
            c.patch(
                f"/messages/{message_id}",
                json={"seen": True},
                headers={"Content-Type": "application/merge-patch+json"},
            ).raise_for_status()

    out: list[Fetched] = []
    with _client(s) as client:
        _authorize(client, s)
        listing = _get(client, s, "/messages", params={"page": 1})
        for item in listing.json()["hydra:member"]:
            if item.get("seen"):
                continue
            raw = _get(client, s, f"/messages/{item['id']}/download").content
            msg = MailMessage.from_bytes(raw)
            if should_skip(msg, s):
                mark_seen(item["id"])
                continue
            arrived = datetime.fromisoformat(item["createdAt"]) if item.get("createdAt") else None
            out.append(Fetched(to_inbound(msg, arrived), lambda i=item["id"]: mark_seen(i)))
    return out
