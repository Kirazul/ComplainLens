"""Support inbox on mail.tm: a free mailbox created through a public API, with no sign-up.

mail.tm receives only (it has no SMTP), so with this inbox replies are read on the tracking page
and in the console. Each message's raw source is downloaded and parsed exactly like an IMAP
message, so loop protection and normalisation are the same for both inboxes.

Create the inbox once with ``uv run complaintlens inbox create <name>``.
"""

from __future__ import annotations

import logging
import secrets

import httpx
from imap_tools import MailMessage

from complaintlens.channels.email import is_automatic, to_inbound
from complaintlens.schemas import InboundMessage
from complaintlens.settings import Settings, get_settings

log = logging.getLogger(__name__)


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


def fetch_new_messages(settings: Settings | None = None) -> list[InboundMessage]:
    """Fetch unseen messages, mark them seen, and return the ones we should process."""
    s = settings or get_settings()
    out: list[InboundMessage] = []
    with _client(s) as client:
        client.headers["Authorization"] = (
            f"Bearer {_token(client, s.email_address, s.email_password)}"
        )
        listing = client.get("/messages", params={"page": 1})
        listing.raise_for_status()
        for item in listing.json()["hydra:member"]:
            if item.get("seen"):
                continue
            raw = client.get(f"/messages/{item['id']}/download")
            raw.raise_for_status()
            client.patch(
                f"/messages/{item['id']}",
                json={"seen": True},
                headers={"Content-Type": "application/merge-patch+json"},
            ).raise_for_status()
            msg = MailMessage.from_bytes(raw.content)
            if msg.from_.lower() == s.email_address.lower() or is_automatic(msg):
                log.info("skipping automatic/own message from %s", msg.from_)
                continue
            out.append(to_inbound(msg))
    return out
