"""Stage 6: route, prioritise, draft a grounded reply, verify it, and decide (plan §6.8-6.9, §7).

1. Routing + priority: a transparent formula whose parts are shown in the console.
2. Pre-gate on the analysis: spam / venting -> no reply; safety, injury, harassment, legal threat or
   severity 4 -> escalated to a human, with a safe acknowledgement (never an AI-written answer).
3. Retrieval: BM25 over the Help Center in the customer's language (dense/hybrid comes next and is
   evaluated against this baseline).
4. Drafting: the LLM may use ONLY the retrieved sections and the code-computed trip facts, and must
   cite them ([HC-FARES#4], [F3]).
5. Verification (deterministic): every citation must exist and every number in the reply (amounts,
   days, minutes) must appear in a cited source. An invented "$20" or "3 days" blocks sending.
   Known limitation: a wrong number that happens to appear in a cited source passes; the
   claim-level NLI verifier (planned) checks meaning, not just numbers.
6. Gate: money involved / verification failed / uncertainty / low confidence -> human approval;
   otherwise auto-send. (v1 rules; the conformal gate of RQ2 replaces the confidence threshold.)
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from complaintlens.llm import ChatClient, complete_json
from complaintlens.pipeline.base import Context
from complaintlens.pipeline.understand import Analysis
from complaintlens.rag.knowledge import Hit, KnowledgeBase
from complaintlens.schemas import Action, Category, MessageType, RiskFlag, StageResult, Urgency
from complaintlens.settings import get_settings

CONFIDENCE_THRESHOLD = 0.7
ESCALATION_FLAGS = {
    RiskFlag.SAFETY,
    RiskFlag.INJURY,
    RiskFlag.HARASSMENT_DISCRIMINATION,
    RiskFlag.LEGAL_THREAT,
}
MONEY_ACTIONS = {"refund", "credit", "waive_fee"}

TEAMS = {
    Category.FARE_BILLING: "Billing",
    Category.PROMOTIONS_CREDITS: "Billing",
    Category.SAFETY_INCIDENT: "Safety",
    Category.ACCESSIBILITY: "Safety",
    Category.DRIVER_BEHAVIOUR: "Driver Operations",
    Category.CANCELLATION_NO_SHOW: "Driver Operations",
    Category.LOST_ITEM: "Lost & Found",
    Category.DELIVERY_ORDER: "Delivery",
    Category.APP_TECHNICAL: "Tech & Accounts",
    Category.ACCOUNT_ACCESS: "Tech & Accounts",
    Category.OTHER: "General Support",
}


class Draft(BaseModel):
    reply: str
    citations: list[str] = Field(default_factory=list)
    proposed_action: Literal[
        "none", "refund", "credit", "waive_fee", "investigate", "ask_information"
    ] = "none"
    action_amount: float | None = None
    confidence: float = Field(ge=0, le=1)


# --- routing and priority ----------------------------------------------------------------------


def route(analysis: Analysis) -> str:
    if set(analysis.risk_flags) & ESCALATION_FLAGS:
        return "Safety"
    return TEAMS.get(analysis.categories[0], "General Support")


def priority(analysis: Analysis, money_involved: bool) -> tuple[int, dict[str, int]]:
    parts = {
        "urgency": {Urgency.IMMEDIATE: 50, Urgency.WITHIN_24H: 30, Urgency.STANDARD: 15}.get(
            analysis.urgency, 5
        ),
        "severity": 5 * (analysis.severity or 0),
        "risk flags": min(20, 10 * len(analysis.risk_flags)),
        "money involved": 10 if money_involved else 0,
        "negative sentiment": 5 if analysis.sentiment == "negative" else 0,
    }
    return min(100, sum(parts.values())), parts


# --- verification ------------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)?(?![\w-])")
_CITATION = re.compile(r"\[((?:HC-[A-Z]+#\d+)|(?:F\d+))\]")


def _numbers(text: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in _NUMBER.findall(text)}


def verify(draft: Draft, hits: list[Hit], facts: list[dict[str, str]]) -> dict[str, object]:
    sources = {h.chunk.id: h.chunk.indexed_text for h in hits} | {f["id"]: f["text"] for f in facts}
    cited = set(draft.citations) | set(_CITATION.findall(draft.reply))
    unknown = sorted(c for c in cited if c not in sources)
    supported_numbers: set[float] = set()
    for c in cited & sources.keys():
        supported_numbers |= _numbers(sources[c])
    reply_wo_citations = _CITATION.sub("", draft.reply)
    claimed = _numbers(reply_wo_citations)
    unsupported = sorted(n for n in claimed if n not in supported_numbers)
    ok = not unknown and not unsupported and (bool(cited) or not claimed)
    return {
        "supported": ok,
        "citations": sorted(cited),
        "unknown_citations": unknown,
        "numbers_checked": len(claimed),
        "unsupported_numbers": unsupported,
    }


# --- templates (no LLM): safe acknowledgements --------------------------------------------------

TEMPLATES = {
    "escalation": {
        "en": "Hello {name},\n\nThank you for telling us, and we are sorry this happened. Your "
        "safety comes first: if you are in danger, please call 911 now.\n\nYour report "
        "(ticket {ticket}) has been sent to our Safety team, who will contact you within 1 hour.",
        "fr": "Bonjour {name},\n\nMerci de nous avoir prévenus, et nous sommes désolés que cela "
        "soit arrivé. Votre sécurité passe avant tout : si vous êtes en danger, appelez le 911 "
        "maintenant.\n\nVotre signalement (ticket {ticket}) a été transmis à notre équipe "
        "Sécurité, qui vous contactera dans un délai d'une heure.",
    },
    "review": {
        "en": "Hello {name},\n\nThank you for contacting {company}. We have received your message "
        "(ticket {ticket}) and our {team} team is reviewing it. You will hear from us within "
        "24 hours.",
        "fr": "Bonjour {name},\n\nMerci d'avoir contacté {company}. Nous avons bien reçu votre "
        "message (ticket {ticket}) et notre équipe {team} l'examine. Vous aurez de nos nouvelles "
        "sous 24 heures.",
    },
    "unsupported_language": {
        "en": "Hello,\n\nThank you for contacting {company} (ticket {ticket}). We currently answer "
        "in English and French; an agent will review your message.\n\nBonjour, merci d'avoir "
        "contacté {company}. Nous répondons en anglais et en français ; un agent examinera votre "
        "message.",
    },
}


def render(kind: str, lang: str, **values: str) -> str:
    variants = TEMPLATES[kind]
    return variants.get(lang, variants["en"]).format(company=get_settings().company_name, **values)


# --- drafting ----------------------------------------------------------------------------------


def _sources_block(hits: list[Hit], facts: list[dict[str, str]]) -> str:
    lines = ["HELP CENTER SECTIONS:"]
    lines += [f"[{h.chunk.id}] {h.chunk.title} > {h.chunk.heading}: {h.chunk.text}" for h in hits]
    lines.append("\nCUSTOMER RECORD FACTS:" if facts else "\nCUSTOMER RECORD FACTS: none found")
    lines += [f"[{f['id']}] {f['text']}" for f in facts]
    return "\n".join(lines)


def draft_reply(
    client: ChatClient,
    text: str,
    analysis: Analysis,
    lang: str,
    name: str,
    hits: list[Hit],
    facts: list[dict[str, str]],
) -> Draft:
    company = get_settings().company_name
    language = {"fr": "French", "en": "English"}.get(lang, "English")
    system = (
        f"You are a customer-support agent of {company}, a ride-hailing app that also delivers "
        "food. Write the reply to the customer.\n"
        "STRICT RULES:\n"
        "1. Use ONLY information from SOURCES. Never invent policies, amounts, delays or facts.\n"
        "2. After every sentence that states a policy or a fact, cite its source in brackets, "
        "e.g. [HC-FARES#4] or [F3].\n"
        "3. Never promise money. If a refund/credit/fee waiver is justified by policy and record, "
        "say that you have asked the Billing team to approve it, and set proposed_action and "
        "action_amount.\n"
        "4. If the record does not show the trip or the facts needed, ask one precise question "
        "(proposed_action=ask_information).\n"
        f"5. Write in {language}, warm and concise (max 130 words), greet the customer by name, "
        f"sign as '{company} Support'. Do not mention internal fact IDs except as citations.\n"
        "6. Placeholders like [EMAIL_1] are masked personal data: never repeat or guess them.\n"
        "Return ONLY JSON: {reply, citations (list of IDs used), proposed_action (none|refund|"
        "credit|waive_fee|investigate|ask_information), action_amount (number or null), "
        "confidence (0-1: how sure you are the reply fully and correctly resolves the message)}."
    )
    user = (
        f"Customer name: {name}\nAnalysis: {analysis.summary} Goal: {analysis.customer_goal}\n"
        f"Customer message:\n<<<\n{text}\n>>>\n\nSOURCES:\n{_sources_block(hits, facts)}"
    )
    return complete_json(client, system, user, Draft, temperature=0.2)


# --- the stage ---------------------------------------------------------------------------------


def respond_stage(ctx: Context) -> StageResult:
    analysis: Analysis = ctx["analysis"]
    lang = ctx.get("language", "en")
    ticket_no = ctx.get("ticket_number", "LG-??????")
    name = ctx["customer"].name if ctx.get("customer") else "there"
    facts = ctx.get("facts", [])
    team = route(analysis)
    reasons: list[str] = []
    draft: Draft | None = None
    verification: dict[str, object] = {}
    hits: list[Hit] = []
    message: str | None = None
    kind = "answer"

    if lang == "other":
        action, kind = Action.AWAITING_APPROVAL, "acknowledgement"
        message = render("unsupported_language", "en", ticket=ticket_no)
        reasons.append("unsupported language")
    elif analysis.message_type == MessageType.SPAM:
        action = Action.NO_REPLY
        reasons.append("spam or irrelevant")
    elif not analysis.response_required:
        action = Action.NO_REPLY
        reasons.append("no response required (e.g. venting with nothing actionable)")
    elif set(analysis.risk_flags) & ESCALATION_FLAGS or analysis.severity == 4:
        action, kind = Action.ESCALATED, "escalation"
        message = render("escalation", lang, name=name, ticket=ticket_no)
        flags = sorted(f.value for f in set(analysis.risk_flags) & ESCALATION_FLAGS)
        reasons.append(f"high risk ({', '.join(flags) or 'severity 4'}): human handles it")
    else:
        kb: KnowledgeBase = ctx["kb"]
        query = f"{analysis.summary} {analysis.customer_goal} {ctx['text_masked']}"
        hits = kb.search(query, lang if lang in ("en", "fr") else "en", k=4)
        client: ChatClient | None = ctx.get("llm")
        if client is None:
            action, kind = Action.AWAITING_APPROVAL, "acknowledgement"
            message = render("review", lang, name=name, ticket=ticket_no, team=team)
            reasons.append("no LLM configured: an agent writes the answer")
        else:
            draft = draft_reply(client, ctx["text_masked"], analysis, lang, name, hits, facts)
            verification = verify(draft, hits, facts)
            message = draft.reply
            if draft.proposed_action in MONEY_ACTIONS:
                action = Action.AWAITING_APPROVAL
                amount = f" ({draft.action_amount:.2f})" if draft.action_amount else ""
                reasons.append(f"money involved: {draft.proposed_action}{amount} needs approval")
            elif not verification["supported"]:
                action = Action.AWAITING_APPROVAL
                reasons.append("verification failed: unsupported or unknown claims")
            elif ctx.get("uncertain"):
                action = Action.AWAITING_APPROVAL
                reasons.append("models disagree on the message type")
            elif draft.confidence < CONFIDENCE_THRESHOLD:
                action = Action.AWAITING_APPROVAL
                reasons.append(f"low confidence ({draft.confidence:.2f})")
            else:
                action = Action.AUTO_SEND
                reasons.append("verified, low risk, confident: sent automatically")

    money = bool(draft and draft.proposed_action in MONEY_ACTIONS)
    score, parts = priority(analysis, money)
    ctx["decision"] = {
        "action": action.value,
        "reasons": reasons,
        "team": team,
        "priority": score,
        "priority_parts": parts,
    }
    ctx["reply"] = (
        {
            "kind": kind,
            "body": message,
            "citations": verification.get("citations", []),
            "verification": verification,
        }
        if message
        else None
    )
    return StageResult(
        name="respond",
        output={
            "decision": ctx["decision"],
            "retrieved": [
                {"id": h.chunk.id, "heading": h.chunk.heading, "score": h.score} for h in hits
            ],
            "draft": draft.model_dump() if draft else None,
            "verification": verification,
            "message": message,
        },
        confidence=draft.confidence if draft else None,
    )


respond_stage.stage_name = "respond"  # type: ignore[attr-defined]
