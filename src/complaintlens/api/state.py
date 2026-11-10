"""Process-wide objects created at startup (one instance, shared by the routers)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from complaintlens.events import EventBus
from complaintlens.security import RateLimiter
from complaintlens.service import Processor


class State:
    def __init__(self) -> None:
        self.processor: Processor
        self.bus: EventBus
        self.limiter: RateLimiter  # customer messages
        self.login_limiter: RateLimiter  # sign-in attempts
        self.email_task: asyncio.Task[None] | None = None
        self.email_status: dict[str, Any] = {"enabled": False}
        self.last_activity = time.monotonic()
        self.email_backoff_until = 0.0


state = State()
