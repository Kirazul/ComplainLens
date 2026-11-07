"""Process one inbound message end to end: ticket -> traced stages -> decision -> replies.

What is sent immediately:
- auto_send: the verified answer;
- escalated: the safe acknowledgement (call 911 if in danger, Safety team within 1 hour);
- awaiting_approval: an acknowledgement ("our team is reviewing it"), while the AI draft waits in
  the console for an agent to approve or edit;
- no_reply: nothing.
If the pipeline itself fails, the customer still gets the acknowledgement and a human gets the
ticket: a message is never lost.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from complaintlens.llm import ChatClient
from complaintlens.pipeline.base import run_stages
from complaintlens.pipeline.language import language_stage
from complaintlens.pipeline.link import link_stage
from complaintlens.pipeline.normalize import normalize_stage
from complaintlens.pipeline.pii import pii_stage
from complaintlens.pipeline.respond import render, respond_stage
from complaintlens.pipeline.understand import understand_stage
from complaintlens.rag.knowledge import KnowledgeBase
from complaintlens.schemas import Action, InboundMessage, StageResult, utcnow
from complaintlens.store import Customer, Reply, StageRecord, Ticket, new_session

log = logging.getLogger(__name__)
STAGES = [normalize_stage, pii_stage, language_stage, understand_stage, link_stage, respond_stage]
Publish = Callable[[dict[str, Any]], None]


class ReplySender(Protocol):
    def send(self, ticket: Ticket, reply: Reply) -> None: ...


class Processor:
    def __init__(
        self,
        kb: KnowledgeBase,
        llm: ChatClient | None,
        senders: dict[str, ReplySender] | None = None,
        publish: Publish | None = None,
        database_url: str | None = None,
    ) -> None:
        self.kb, self.llm = kb, llm
        self.senders = senders or {}
        self.publish = publish or (lambda event: None)
        self.database_url = database_url

    def process(self, inbound: InboundMessage) -> Ticket:
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
                "llm": self.llm,
                "ticket_number": ticket.number,
            }
            trace = run_stages(STAGES, ctx, on_stage=on_stage)
            self._apply(ticket, ctx, trace)
            to_send = self._make_replies(session, ticket, ctx)
            session.commit()

            for reply in to_send:
                self._send(session, ticket, reply)
            session.commit()
            self.publish(
                {"type": "ticket_updated", "ticket_id": ticket.id, "status": ticket.status}
            )
            return ticket

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

    def _make_replies(self, session, ticket: Ticket, ctx: dict[str, Any]) -> list[Reply]:
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
                to_send.append(draft)
                return to_send
        elif reply:  # escalation / acknowledgement templates
            msg = Reply(ticket_id=ticket.id, kind=reply["kind"], body=reply["body"])
            session.add(msg)
            to_send.append(msg)
            return to_send
        ack = Reply(
            ticket_id=ticket.id,
            kind="acknowledgement",
            body=render(
                "review",
                lang,
                name=customer.name if customer else "",
                ticket=ticket.number,
                team=ticket.team or "Support",
            ),
        )
        session.add(ack)
        to_send.append(ack)
        return to_send

    def _send(self, session, ticket: Ticket, reply: Reply) -> None:
        sender = self.senders.get(ticket.channel)
        if sender is None:  # web chat replies are read from the API; nothing to push
            reply.status = "sent" if ticket.channel in ("web", "chat") else "draft"
            reply.sent_at = utcnow() if reply.status == "sent" else None
            return
        try:
            sender.send(ticket, reply)
            reply.status, reply.sent_at = "sent", utcnow()
        except Exception as exc:
            log.exception("sending reply for %s failed", ticket.number)
            reply.status, reply.error = "failed", f"{type(exc).__name__}: {exc}"
        session.add(reply)
        self.publish({"type": "reply", "ticket_id": ticket.id, "status": reply.status})

    def approve(self, ticket_id: int, body: str | None = None) -> Reply:
        """An agent approves (optionally edits) the AI draft; it is sent on the ticket's channel."""
        with new_session(self.database_url) as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket is None:
                raise KeyError(ticket_id)
            from sqlmodel import select

            draft = session.exec(
                select(Reply).where(
                    Reply.ticket_id == ticket_id, Reply.kind == "answer", Reply.status == "draft"
                )
            ).first()
            if draft is None:
                draft = Reply(ticket_id=ticket_id, kind="answer", body=body or "")
            if body:
                draft.body = body
                draft.verification = {**draft.verification, "edited_by_agent": True}
            session.add(draft)
            self._send(session, ticket, draft)
            ticket.status = "answered" if draft.status == "sent" else ticket.status
            session.add(ticket)
            session.commit()
            self.publish(
                {"type": "ticket_updated", "ticket_id": ticket.id, "status": ticket.status}
            )
            return draft
