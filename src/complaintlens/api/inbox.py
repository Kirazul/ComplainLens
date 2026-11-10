"""The email poller: new mail becomes tickets, without ever losing a message.

A message is acknowledged only after its ticket is stored, and a Message-ID that is already
stored is not processed twice. A reply in an existing email thread joins that ticket's
conversation instead of opening a new one.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from sqlmodel import select

from complaintlens.api.state import state
from complaintlens.channels import agentmail as agentmail_inbox
from complaintlens.channels import email as imap_inbox
from complaintlens.channels.email import Fetched
from complaintlens.settings import get_settings
from complaintlens.store import CustomerMessage, Ticket, new_session

log = logging.getLogger(__name__)
POLL_SECONDS = 30
BACKOFF_SECONDS = 120  # wait after the mail provider says "too many requests"
# The host puts the service to sleep after 10 idle minutes (no network traffic) and wakes it on
# the next request. Polling the inbox forever would keep it awake (and spend the free credit), so
# the inbox is polled only while the API has been used recently; a scheduled relay
# (.github/workflows/relay.yml) wakes it every hour to collect mail even when nobody visits.
ACTIVE_WINDOW_SECONDS = 600


def _store_email(item: Fetched) -> tuple[Ticket, bool] | None:
    """Store the email (a new ticket, or a follow-up in its thread's ticket), then mark it
    handled. Returns the ticket and whether it is new; None if this email is already stored (a
    crash between the two steps, or the same Message-ID delivered twice)."""
    message = item.message
    with new_session() as s:
        if message.external_id and (
            s.exec(select(Ticket.id).where(Ticket.external_id == message.external_id)).first()
            or s.exec(
                select(CustomerMessage.id).where(CustomerMessage.external_id == message.external_id)
            ).first()
        ):
            item.ack()
            return None
        thread = (
            s.exec(select(Ticket).where(Ticket.thread_id == message.thread_id)).first()
            if message.thread_id
            else None
        )
    if thread is not None:
        state.processor.add_message(thread.id, message.body, external_id=message.external_id)
        item.ack()
        return thread, False
    ticket = state.processor.create_ticket(message)
    item.ack()
    return ticket, True


async def poll_inbox_once() -> int:
    """Fetch new emails and run each through the pipeline; returns how many were new."""
    if time.monotonic() < state.email_backoff_until:
        return 0
    inbox = agentmail_inbox if get_settings().email_inbox == "agentmail" else imap_inbox
    try:
        fetched = await asyncio.to_thread(inbox.fetch_new_messages)
        state.email_status.update(last_poll_ok=True, last_error=None)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 429:
            log.exception("email poll failed")
        else:
            log.warning("mail provider rate limit: pausing the inbox for %s s", BACKOFF_SECONDS)
            state.email_backoff_until = time.monotonic() + BACKOFF_SECONDS
        state.email_status.update(last_poll_ok=False, last_error=f"HTTP {exc.response.status_code}")
        return 0
    except Exception as exc:
        log.exception("email poll failed")
        state.email_status.update(last_poll_ok=False, last_error=f"{type(exc).__name__}: {exc}")
        return 0
    new = 0
    for item in fetched:  # one bad message must not stop the others (or the poller)
        try:
            stored = await asyncio.to_thread(_store_email, item)
        except Exception:
            log.exception("could not store an email; it stays unread and is retried")
            continue
        if stored is None:
            continue
        ticket, is_new = stored
        new += 1
        try:  # a follow-up runs again on the whole conversation
            await asyncio.to_thread(
                state.processor.run, ticket.id, item.message if is_new else None
            )
        except Exception:
            log.exception("pipeline failed for %s", ticket.number)
    return new


async def email_loop() -> None:
    """Poll the support inbox every few seconds while the API is in use."""
    while True:
        if time.monotonic() - state.last_activity < ACTIVE_WINDOW_SECONDS:
            await poll_inbox_once()
        await asyncio.sleep(POLL_SECONDS)
