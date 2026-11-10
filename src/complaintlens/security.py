"""Access control and abuse protection for the public API.

- Operators (support agents) send ``Authorization: Bearer <OPERATOR_TOKEN>``; everyone else sees
  the console read-only, with customer contacts masked.
- The forum relay sends ``X-Channel-Token: <CHANNEL_TOKEN>``.
- Message submission is rate-limited per client and per day: each message costs LLM calls.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from complaintlens.settings import get_settings


def _matches(given: str | None, expected: str) -> bool:
    # Bytes: compare_digest rejects non-ASCII str, and a header can contain anything.
    return bool(given) and secrets.compare_digest((given or "").encode(), expected.encode())


def is_operator(request: Request) -> bool:
    expected = get_settings().operator_token
    if not expected:  # local development: no token configured
        return True
    auth = request.headers.get("authorization", "")
    return auth.startswith("Bearer ") and _matches(auth.removeprefix("Bearer "), expected)


def require_operator(request: Request) -> None:
    if not is_operator(request):
        raise HTTPException(401, "operator token required")


def require_channel_token(request: Request) -> None:
    expected = get_settings().channel_token
    if not expected:
        raise HTTPException(404, "channel not enabled")
    if not _matches(request.headers.get("x-channel-token"), expected):
        raise HTTPException(401, "invalid channel token")


def mask_contact(contact: str | None) -> str | None:
    """``rimel.zouari@example.com`` -> ``r••••@example.com`` (forum logins are public already)."""
    if not contact or "@" not in contact or contact.startswith("forum:"):
        return contact
    local, domain = contact.split("@", 1)
    return f"{local[:1]}••••@{domain}"


class RateLimiter:
    """Sliding-window limits: ``per_key`` events per ``window`` seconds, ``total`` per day."""

    def __init__(self, per_key: int, window: float, total: int) -> None:
        self.per_key, self.window, self.total = per_key, window, total
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._day: deque[float] = deque()
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window:
                events.popleft()
            while self._day and now - self._day[0] > 86_400:
                self._day.popleft()
            if len(self._day) >= self.total:
                raise HTTPException(429, "daily message limit reached, please try again tomorrow")
            if len(events) >= self.per_key:
                raise HTTPException(429, "too many messages, please try again later")
            events.append(now)
            self._day.append(now)


def client_ip(request: Request) -> str:
    # Behind Railway's proxy: X-Real-IP, or the last X-Forwarded-For entry (the one the proxy
    # added). Earlier entries are written by the client and could be forged.
    if real := request.headers.get("x-real-ip"):
        return real.strip()
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
