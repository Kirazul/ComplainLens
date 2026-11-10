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
from complaintlens.rag.retrieval import BM25Retriever, Retriever, search_with_summary
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
    """Two separate checks.

    Grounding (gates sending): every number in the reply must appear in a source the model was
    given (retrieved Help Center sections or record facts), and every citation must exist.
    Citation coverage (quality, reported): share of the reply's numbers whose *cited* source
    contains them. Models sometimes state correct, sourced facts without citing them; that is a
    presentation weakness, not a hallucination, so it does not block the reply on its own.
    """
    sources = {h.chunk.id: h.chunk.indexed_text for h in hits} | {f["id"]: f["text"] for f in facts}
    cited = set(draft.citations) | set(_CITATION.findall(draft.reply))
    unknown = sorted(c for c in cited if c not in sources)
    available: set[float] = set()
    for text in sources.values():
        available |= _numbers(text)
    # Sentence level: a sentence that cites sources must take its numbers from THOSE sources (so a
    # wrong number cannot hide behind an unrelated section); an uncited sentence must at least use
    # numbers present somewhere in the sources, and lowers the citation coverage.
    # Dates ("9 novembre", "Nov 9") are checked against the dates of the customer's record, not
    # against policy numbers: a day number is a date, not an amount.
    fact_days = {float(d) for f in facts for d in _ISO_DAY.findall(f["text"])}
    claimed: set[float] = set()
    unsupported: set[float] = set()
    covered = 0
    for sentence in _sentences(draft.reply):
        days = {float(d) for pair in _DATE_MENTION.findall(sentence) for d in pair if d}
        unsupported |= {d for d in days if d not in fact_days}
        claimed |= days
        numbers = _numbers(_DATE_MENTION.sub(" ", _CITATION.sub("", sentence)))
        if not numbers:
            continue
        claimed |= numbers
        refs = [c for c in _CITATION.findall(sentence) if c in sources]
        if refs:
            allowed: set[float] = set().union(*(_numbers(sources[c]) for c in refs))
            covered += 1
        else:
            allowed = available
        unsupported |= {n for n in numbers if n not in allowed}
    with_numbers = sum(1 for s in _sentences(draft.reply) if _numbers(_CITATION.sub("", s)))
    return {
        "supported": not unknown and not unsupported,
        "citations": sorted(cited),
        "unknown_citations": unknown,
        "numbers_checked": len(claimed),
        "unsupported_numbers": sorted(unsupported),
        "citation_coverage": round(covered / with_numbers, 2) if with_numbers else 1.0,
    }


_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|"
    "novembre|décembre|decembre"
)
_DATE_MENTION = re.compile(
    rf"\b(\d{{1,2}})(?:er)?\s+(?:{_MONTHS})\b|\b(?:{_MONTHS})\.?\s+(\d{{1,2}})\b", re.IGNORECASE
)
_ISO_DAY = re.compile(r"\b\d{4}-\d{2}-(\d{2})\b")

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[^\[])|\n+")


def _sentences(text: str) -> list[str]:
    """Split into sentences, keeping a citation that follows the full stop with its sentence."""
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


def clean_reply(text: str) -> str:
    """Models occasionally emit escaped newlines ("\\n") inside JSON strings: make them real."""
    return text.replace("\\n", "\n").strip()


def strip_citations(text: str) -> str:
    """Citations like [HC-FARES#4] are for agents and the verifier, not for customers."""
    return re.sub(r"\s?\[(?:HC-[A-Z]+#\d+|F\d+)\]", "", text)


# --- templates (no LLM): safe acknowledgements --------------------------------------------------

TEAM_NAMES_FR = {
    "Billing": "Facturation",
    "Safety": "Sécurité",
    "Driver Operations": "Opérations chauffeurs",
    "Lost & Found": "Objets trouvés",
    "Delivery": "Livraison",
    "Tech & Accounts": "Technique et comptes",
    "General Support": "Support général",
    "Support": "Support",
}


def greeting(lang: str, name: str | None) -> str:
    """'Hello Alex,' or just 'Hello,': we never invent a name we do not know."""
    word = "Bonjour" if lang == "fr" else "Hello"
    return f"{word} {name}," if name else f"{word},"


def team_label(team: str, lang: str) -> str:
    return TEAM_NAMES_FR.get(team, team) if lang == "fr" else team


TEMPLATES = {
    "escalation": {
        "en": "{greeting}\n\nThank you for telling us, and we are sorry this happened. Your "
        "safety comes first: if you are in danger, please call 911 now.\n\nYour report "
        "(ticket {ticket}) has been sent to our Safety team, who will contact you within 1 hour.",
        "fr": "{greeting}\n\nMerci de nous avoir prévenus, et nous sommes désolés que cela "
        "soit arrivé. Votre sécurité passe avant tout : si vous êtes en danger, appelez le 911 "
        "maintenant.\n\nVotre signalement (ticket {ticket}) a été transmis à notre équipe "
        "Sécurité, qui vous contactera dans un délai d'une heure.",
    },
    "review": {
        "en": "{greeting}\n\nThank you for contacting {company}. We have received your message "
        "(ticket {ticket}) and our {team} team is reviewing it. You will hear from us within "
        "24 hours.",
        "fr": "{greeting}\n\nMerci d'avoir contacté {company}. Nous avons bien reçu votre "
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


def render(kind: str, lang: str, name: str | None = None, team: str = "", ticket: str = "") -> str:
    variants = TEMPLATES[kind]
    lang = lang if lang in variants else "en"
    return variants[lang].format(
        company=get_settings().company_name,
        greeting=greeting(lang, name),
        team=team_label(team, lang),
        ticket=ticket,
    )


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
    history: list[dict[str, str]] | None = None,
) -> Draft:
    company = get_settings().company_name
    language = {"fr": "French", "en": "English"}.get(lang, "English")
    system = (
        f"You are a customer-support agent of {company}, a ride-hailing app that also delivers "
        "food. Write the reply to the customer.\n"
        "STRICT RULES:\n"
        "1. Use ONLY information from SOURCES. Never invent policies, amounts, delays or facts.\n"
        "2. After EVERY sentence that states a policy or a fact, put its source ID in square "
        'brackets, and list the same IDs in `citations`. Example: "Your ride was charged twice, '
        '$16.42 each time [F4]. Refunds take 5 to 10 business days [HC-FARES#4]."\n'
        "3. Never promise money. If a refund/credit/fee waiver is justified by policy and record, "
        f"say that you have asked the {team_label('Billing', lang)} team to approve it, and set "
        "proposed_action and action_amount.\n"
        "4. If the record does not show the trip or the facts needed, ask one precise question "
        "(proposed_action=ask_information).\n"
        f"5. Write in {language}, warm and concise (max 130 words), greet the customer (by name "
        "only if a name is given; never invent one), "
        f"sign as '{company} Support'. Do not mention internal fact IDs except as citations.\n"
        "6. Placeholders like [EMAIL_1] are masked personal data: never repeat or guess them.\n"
        "Return ONLY JSON: {reply, citations (list of IDs used), proposed_action (none|refund|"
        "credit|waive_fee|investigate|ask_information), action_amount (number or null), "
        "confidence (0-1: how sure you are the reply fully and correctly resolves the message)}."
    )
    user = (
        f"Customer name: {name or '(unknown: greet without a name)'}\n"
        f"Analysis: {analysis.summary} Goal: {analysis.customer_goal}\n"
        f"Customer message:\n<<<\n{text}\n>>>\n\nSOURCES:\n{_sources_block(hits, facts)}"
    )
    if history and len(history) > 1:  # a follow-up: answer the latest message, in context
        said = "\n".join(
            f"{'Customer' if h['from'] == 'customer' else company}: {h['text']}" for h in history
        )
        user += (
            f"\n\nCONVERSATION SO FAR (oldest first):\n<<<\n{said}\n>>>\n"
            f"Reply to the customer's latest message. Do not repeat what {company} already said, "
            "and keep the greeting short."
        )
    draft = complete_json(client, system, user, Draft, temperature=0.2)
    draft.reply = clean_reply(draft.reply)
    return draft


# --- the stage ---------------------------------------------------------------------------------


def respond_stage(ctx: Context) -> StageResult:
    analysis: Analysis = ctx["analysis"]
    lang = ctx.get("language", "en")
    ticket_no = ctx.get("ticket_number", "LG-??????")
    name = ctx["customer"].name if ctx.get("customer") else ""
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
        retriever: Retriever = ctx.get("retriever") or BM25Retriever(kb)
        # Customer's words (their language) fused with the LLM's English summary (same sections,
        # mapped back to their language): MRR 0.657 vs 0.613 on the development questions
        # (reports/results/retrieval_summary.json). Without an LLM, the text alone is used.
        llm_summary = analysis.summary if ctx.get("llm") else None
        hits = search_with_summary(
            retriever, kb, ctx["text_masked"], llm_summary, lang if lang in ("en", "fr") else "en"
        )
        client: ChatClient | None = ctx.get("llm")
        if client is None:
            action, kind = Action.AWAITING_APPROVAL, "acknowledgement"
            message = render("review", lang, name=name, ticket=ticket_no, team=team)
            reasons.append("no LLM configured: an agent writes the answer")
        else:
            draft = draft_reply(
                client, ctx["text_masked"], analysis, lang, name, hits, facts, ctx.get("history")
            )
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
            "retriever": (ctx.get("retriever") or BM25Retriever(ctx["kb"])).name if hits else None,
            "draft": draft.model_dump() if draft else None,
            "verification": verification,
            "message": message,
        },
        confidence=draft.confidence if draft else None,
    )


respond_stage.stage_name = "respond"  # type: ignore[attr-defined]
