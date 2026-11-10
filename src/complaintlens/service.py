"""Process customer conversations end to end: ticket -> traced stages -> decision -> replies.

A ticket is one conversation. The first message creates it. Follow-ups (live chat, tracking page)
join the same ticket, and the pipeline runs again on everything the customer has said, with the
conversation so far given to the reply writer.

What is sent automatically:
- auto_send: the verified answer;
- escalated: the safety acknowledgement (call 911 if in danger, Safety team within 1 hour);
- awaiting_approval: an acknowledgement ("our team is reviewing it"), while the AI draft waits in
  the console for an agent to send or rewrite;
- no_reply: nothing.
Acknowledgements are sent once per conversation. Once an agent has replied, the AI never sends on
its own again in that conversation: it only prepares a draft. An escalated conversation stays
escalated. If the pipeline itself fails, the customer still gets the acknowledgement and a human
gets the ticket: a message is never lost.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol

from sqlmodel import Session, col, select

from complaintlens.llm import ChatClient
from complaintlens.pipeline.base import run_stages
from complaintlens.pipeline.language import language_stage
from complaintlens.pipeline.link import link_stage
from complaintlens.pipeline.normalize import normalize_stage
from complaintlens.pipeline.pii import mask_pii, pii_stage
from complaintlens.pipeline.respond import render, respond_stage, strip_citations
from complaintlens.pipeline.understand import understand_stage
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.rag.retrieval import BM25Retriever, Retriever
from complaintlens.schemas import Action, Channel, InboundMessage, StageResult, as_utc, utcnow
from complaintlens.store import (
    Customer,
    CustomerMessage,
    Reply,
    StageRecord,
    Ticket,
    new_session,
)

log = logging.getLogger(__name__)
STAGES = [normalize_stage, pii_stage, language_stage, understand_stage, link_stage, respond_stage]
Publish = Callable[[dict[str, Any]], None]
READ_ON_SITE = {"web", "chat", "review"}  # replies are shown on our website
RELAYED = {"forum"}  # replies wait in an outbox for the forum relay (GitHub Actions)
ONCE_PER_CONVERSATION = {"acknowledgement", "escalation"}


class ReplySender(Protocol):
    def send(self, ticket: Ticket, reply: Reply) -> None: ...


def thread(session: Session, ticket: Ticket, *, for_customer: bool) -> list[dict[str, Any]]:
    """The conversation in time order. Customers see only what was delivered, without
    citations; agents also see queued and failed replies (never drafts: those are separate)."""
    items: list[dict[str, Any]] = [
        {"from": "customer", "body": ticket.body, "at": as_utc(ticket.received_at)}
    ]
    follow_ups = session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.ticket_id == ticket.id)
        .order_by(col(CustomerMessage.id))
    ).all()
    items += [{"from": "customer", "body": m.body, "at": as_utc(m.received_at)} for m in follow_ups]
    replies = session.exec(
        select(Reply).where(Reply.ticket_id == ticket.id).order_by(col(Reply.id))
    ).all()
    for r in replies:
        if r.status == "draft" or (for_customer and r.status != "sent"):
            continue
        item = {
            "from": "lunago",
            "kind": r.kind,
            "body": strip_citations(r.body) if for_customer else r.body,
            "at": as_utc(r.sent_at or r.created_at),
            "author": r.author,  # None: sent automatically by the assistant
        }
        if not for_customer:
            item |= {"id": r.id, "status": r.status, "error": r.error, "citations": r.citations}
        items.append(item)
    items.sort(key=lambda i: i["at"])  # stable: equal times keep their order
    return items


class Processor:
    def __init__(
        self,
        kb: KnowledgeBase,
        llm: ChatClient | None,
        senders: dict[str, ReplySender] | None = None,
        publish: Publish | None = None,
        database_url: str | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self.kb, self.llm = kb, llm
        self.retriever = retriever or BM25Retriever(kb)
        self.senders = senders or {}
        self.publish = publish or (lambda event: None)
        self.database_url = database_url
        # One pipeline run or agent action at a time per conversation (a customer can send two
        # chat messages before the first is answered).
        self._locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def _lock(self, ticket_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks[ticket_id]

    def _get(self, session: Session, ticket_id: int | None) -> Ticket:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        return ticket

    def _updated(self, ticket: Ticket) -> None:
        self.publish({"type": "ticket_updated", "ticket_id": ticket.id, "status": ticket.status})

    # --- customer side ---------------------------------------------------------------------

    def process(self, inbound: InboundMessage) -> Ticket:
        """Create the ticket and run the whole pipeline (used for email, the forum and the CLI)."""
        return self.run(self.create_ticket(inbound).id, inbound)

    def create_ticket(self, inbound: InboundMessage) -> Ticket:
        """Fast: store the message and return its ticket (number, tracking key) immediately."""
        with new_session(self.database_url) as session:
            ticket = Ticket(
                channel=inbound.channel.value,
                sender=inbound.sender,
                sender_name=inbound.sender_name,
                subject=inbound.subject,
                body=inbound.body,
                received_at=inbound.received_at,
                external_id=inbound.external_id,
                in_reply_to=inbound.in_reply_to,
                status="processing",
            )
            session.add(ticket)
            session.commit()
            assert ticket.id is not None
            self.publish(
                {"type": "ticket_created", "ticket_id": ticket.id, "number": ticket.number}
            )
            return ticket

    def add_message(self, ticket_id: int, body: str) -> Ticket:
        """Fast: store a customer's follow-up. Then call ``run(ticket_id)`` to answer it."""
        with new_session(self.database_url) as session:
            ticket = self._get(session, ticket_id)
            session.add(CustomerMessage(ticket_id=ticket_id, body=body))
            ticket.status, ticket.updated_at = "processing", utcnow()
            session.add(ticket)
            session.commit()
        self.publish({"type": "message", "ticket_id": ticket_id})
        return ticket

    def _conversation(
        self, session: Session, ticket: Ticket
    ) -> tuple[InboundMessage, list[dict[str, str]]]:
        """Everything the customer said, as one message for the stages, and the conversation
        so far for the reply writer (personal data masked: it is sent to the LLM)."""
        items = thread(session, ticket, for_customer=True)
        said = [i["body"] for i in items if i["from"] == "customer"]
        inbound = InboundMessage(
            channel=Channel(ticket.channel),
            sender=ticket.sender,
            sender_name=ticket.sender_name,
            subject=ticket.subject,
            body="\n\n".join(said),
            received_at=as_utc(ticket.received_at),
            external_id=ticket.external_id,
            in_reply_to=ticket.in_reply_to,
        )
        history = [
            {
                "from": i["from"],
                "text": mask_pii(i["body"])[0] if i["from"] == "customer" else i["body"],
            }
            for i in items
        ]
        return inbound, history

    def run(self, ticket_id: int | None, inbound: InboundMessage | None = None) -> Ticket:
        """Slow: run the stages, decide, and send what must be sent. ``inbound`` is the first
        message; without it the pipeline runs again on the whole conversation (a follow-up)."""
        assert ticket_id is not None
        with self._lock(ticket_id), new_session(self.database_url) as session:
            ticket = self._get(session, ticket_id)
            history: list[dict[str, str]] = []
            if inbound is None:
                inbound, history = self._conversation(session, ticket)
                self._clear_previous_run(session, ticket_id)
            delivered = session.exec(
                select(Reply).where(Reply.ticket_id == ticket_id, Reply.status != "draft")
            ).all()
            seq = 0

            def on_stage(result: StageResult) -> None:
                nonlocal seq
                seq += 1
                session.add(
                    StageRecord(
                        ticket_id=ticket.id,
                        seq=seq,
                        name=result.name,
                        status=result.status,
                        output=result.output,
                        confidence=result.confidence,
                        ms=result.ms,
                        note=result.note,
                    )
                )
                session.commit()
                self.publish(
                    {"type": "stage", "ticket_id": ticket.id, **result.model_dump(mode="json")}
                )

            ctx: dict[str, Any] = {
                "message": inbound,
                "session": session,
                "kb": self.kb,
                "retriever": self.retriever,
                "llm": self.llm,
                "ticket_number": ticket.number,
                "history": history,
            }
            trace = run_stages(STAGES, ctx, on_stage=on_stage)
            self._apply(ticket, ctx, trace)
            self._apply_conversation_rules(ticket, delivered)
            to_send = self._make_replies(session, ticket, ctx, {r.kind for r in delivered})
            ticket.updated_at = utcnow()
            session.commit()

            for reply in to_send:
                self._send(session, ticket, reply)
            session.commit()
            self._updated(ticket)
            return ticket

    def _clear_previous_run(self, session: Session, ticket_id: int) -> None:
        """A new run replaces the previous trace and the unsent draft (sent replies stay)."""
        for old in session.exec(select(StageRecord).where(StageRecord.ticket_id == ticket_id)):
            session.delete(old)
        for old in session.exec(
            select(Reply).where(Reply.ticket_id == ticket_id, Reply.status == "draft")
        ):
            session.delete(old)
        session.commit()

    def _apply(self, ticket: Ticket, ctx: dict[str, Any], trace: list[StageResult]) -> None:
        ticket.total_ms = round(sum(r.ms for r in trace), 1)
        ticket.language = ctx.get("language")
        if analysis := ctx.get("analysis"):
            ticket.analysis = analysis.model_dump(mode="json")
        if customer := ctx.get("customer"):
            ticket.customer_id = customer.id
        if trip := ctx.get("trip"):
            ticket.trip_id = trip.id
        decision = ctx.get("decision")
        if decision is None:  # a stage failed before deciding: a human takes over
            errors = [f"{r.name}: {r.note}" for r in trace if r.status == "error"]
            decision = {
                "action": Action.AWAITING_APPROVAL.value,
                "reasons": [f"pipeline error, routed to a human ({'; '.join(errors)})"],
                "team": "General Support",
                "priority": 50,
                "priority_parts": {"pipeline error": 50},
            }
            ctx["decision"] = decision
        ticket.decision = decision
        ticket.team = decision["team"]
        ticket.priority = decision["priority"]
        ticket.status = decision["action"]

    def _apply_conversation_rules(self, ticket: Ticket, delivered: list[Reply]) -> None:
        """What the conversation so far allows, whatever this message alone would get."""
        if any(r.kind == "escalation" for r in delivered):
            status, reason = Action.ESCALATED, "already escalated: stays with a human"
        elif any(r.author for r in delivered) and ticket.status in (
            Action.AUTO_SEND,
            Action.NEEDS_INFO,
        ):
            status, reason = Action.AWAITING_APPROVAL, "an agent is handling this conversation"
        else:
            return
        if ticket.status != status:
            decision = dict(ticket.decision or {})
            decision["action"] = status.value
            decision["reasons"] = [*decision.get("reasons", []), reason]
            ticket.decision, ticket.status = decision, status.value

    def _make_replies(
        self, session: Session, ticket: Ticket, ctx: dict[str, Any], already_sent: set[str]
    ) -> list[Reply]:
        """The draft to keep and the messages to send now. Acknowledgements go out once."""
        action = ticket.status
        reply = ctx.get("reply")
        customer: Customer | None = ctx.get("customer")
        lang = ctx.get("language") if ctx.get("language") in ("en", "fr") else "en"
        to_send: list[Reply] = []
        if action == Action.NO_REPLY:
            return to_send
        if reply and reply["kind"] == "answer":
            draft = Reply(
                ticket_id=ticket.id,
                kind="answer",
                body=reply["body"],
                citations=reply["citations"],
                verification=reply["verification"],
            )
            session.add(draft)
            if action == Action.AUTO_SEND:
                return [draft]
        elif reply and reply["kind"] == "question":  # "which ride?": asked by the template
            if action == Action.NEEDS_INFO:
                msg = Reply(ticket_id=ticket.id, kind="question", body=reply["body"])
                session.add(msg)
                return [msg]
            # An agent is handling the conversation: the question becomes their draft.
            session.add(Reply(ticket_id=ticket.id, kind="answer", body=reply["body"]))
        elif reply:  # escalation / acknowledgement templates
            if reply["kind"] in already_sent:
                return to_send
            msg = Reply(ticket_id=ticket.id, kind=reply["kind"], body=reply["body"])
            session.add(msg)
            return [msg]
        if action == Action.ESCALATED or "acknowledgement" in already_sent:
            return to_send
        ack = Reply(
            ticket_id=ticket.id,
            kind="acknowledgement",
            body=render(
                "review_ride" if ctx.get("trip") else "review",  # say which ride was checked
                lang,
                name=customer.name if customer else "",
                ticket=ticket.number,
                team=ticket.team or "Support",
                ride=ctx["trip"].id if ctx.get("trip") else "",
            ),
        )
        session.add(ack)
        return [ack]

    def _send(self, session: Session, ticket: Ticket, reply: Reply) -> None:
        sender = self.senders.get(ticket.channel)
        if sender is None:
            if ticket.channel in READ_ON_SITE:  # the customer reads it on the tracking page / chat
                reply.status, reply.sent_at = "sent", utcnow()
            elif ticket.channel in RELAYED:  # the forum relay posts it, then marks it sent
                reply.status = "queued"
            else:  # e.g. a receive-only inbox: visible in the console, not delivered
                reply.status, reply.error = "failed", "no outbound delivery for this channel"
            session.add(reply)
            self.publish({"type": "reply", "ticket_id": ticket.id, "status": reply.status})
            return
        try:
            sender.send(ticket, reply)
            reply.status, reply.sent_at = "sent", utcnow()
        except Exception as exc:
            log.exception("sending reply for %s failed", ticket.number)
            reply.status, reply.error = "failed", f"{type(exc).__name__}: {exc}"
        session.add(reply)
        self.publish({"type": "reply", "ticket_id": ticket.id, "status": reply.status})

    # --- agent side ------------------------------------------------------------------------

    def agent_reply(self, ticket_id: int, body: str | None = None, author: str = "") -> Reply:
        """An agent sends a reply: the AI draft as is, the draft edited, or their own text.
        It is delivered on the ticket's channel."""
        with self._lock(ticket_id), new_session(self.database_url) as session:
            ticket = self._get(session, ticket_id)
            draft = session.exec(
                select(Reply).where(
                    Reply.ticket_id == ticket_id, Reply.kind == "answer", Reply.status == "draft"
                )
            ).first()
            if draft is None:
                draft = Reply(ticket_id=ticket_id, kind="answer", body=body or "")
            elif body and body.strip() != draft.body.strip():
                draft.body = body
                draft.verification = {**draft.verification, "edited_by_agent": True}
            draft.author = author or "Agent"
            session.add(draft)
            self._send(session, ticket, draft)
            if draft.status in ("sent", "queued"):
                ticket.status = "answered"
            ticket.updated_at = utcnow()
            session.add(ticket)
            session.commit()
            self._updated(ticket)
            return draft

    def set_status(self, ticket_id: int, resolved: bool) -> Ticket:
        """Resolve a conversation, or reopen it (it then waits for an agent)."""
        with self._lock(ticket_id), new_session(self.database_url) as session:
            ticket = self._get(session, ticket_id)
            ticket.status = "closed" if resolved else Action.AWAITING_APPROVAL.value
            ticket.updated_at = utcnow()
            session.add(ticket)
            session.commit()
            self._updated(ticket)
            return ticket
