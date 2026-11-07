"""Stage 4: understand the message (plan §6.3-6.5).

Three independent signals, combined transparently:
1. Classical models (TF-IDF + logistic regression, evaluated in reports/results/
   baseline_complaints2019.json): complaint probability and severity. Fast, free, explainable.
2. An LLM that applies the *same annotation guidelines the human annotators use*
   (eval/annotation_guidelines.md) and returns structured labels. It is also the "teacher" whose
   labels will be distilled into a small encoder (RQ1).
3. A bilingual risk lexicon, recall-first: if a message mentions assault, injury, a lawyer..., the
   flag is raised even if the LLM missed it (a false alarm costs an agent a minute; a miss can cost
   much more).

Without an LLM configured, the stage falls back to the classical models + keyword categories, so
the system keeps working. Disagreement between the LLM and the classical model is reported: it is
an uncertainty signal the response gate uses.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Literal

import joblib
from pydantic import BaseModel, Field

from complaintlens.llm import ChatClient, complete_json
from complaintlens.pipeline.base import Context
from complaintlens.schemas import Category, MessageType, RiskFlag, StageResult, Urgency
from complaintlens.settings import ROOT, get_settings

GUIDELINES = ROOT / "eval" / "annotation_guidelines.md"


class Entity(BaseModel):
    type: Literal["DATE_TIME", "MONEY", "LOCATION", "TRIP_REF", "DRIVER_REF", "PAYMENT_REF"]
    text: str


class Analysis(BaseModel):
    message_type: MessageType
    response_required: bool
    urgency: Urgency | None = None
    categories: list[Category] = Field(min_length=1, max_length=3)
    severity: int | None = Field(default=None, ge=1, le=4)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    sentiment: Literal["negative", "neutral", "positive"]
    entities: list[Entity] = Field(default_factory=list)
    summary: str = Field(description="one neutral English sentence: what happened")
    customer_goal: str = Field(description="what the customer wants, in English")


# --- 3. risk lexicon (EN + FR); stems so that "harassed"/"harcelée" both match -----------------
_RISK_PATTERNS: dict[RiskFlag, re.Pattern[str]] = {
    RiskFlag.SAFETY: re.compile(
        r"\b(assault|attack|unsafe|danger|threat|weapon|gun|knife|drunk|intoxicated|high on|"
        r"speeding|reckless|kidnap|followed me|scared for my life|"
        r"agress|attaqu|ins[ée]curit|dangereu|menac|arme|couteau|ivre|so[uû]l|"
        r"exc[eè]s de vitesse|j'ai eu peur|peur pour ma vie)",
        re.IGNORECASE,
    ),
    RiskFlag.INJURY: re.compile(
        r"\b(injur|hurt|bleed|hospital|ambulance|accident|crash(ed)? into|"
        r"bless[ée]|h[oô]pital|saign|accident)",
        re.IGNORECASE,
    ),
    RiskFlag.HARASSMENT_DISCRIMINATION: re.compile(
        r"\b(harass|grop|touched me|sexual|racis|discriminat|service (dog|animal)|"
        r"harc[eè]l|attouch|sexuel|racis|discrimin|chien d'assistance)",
        re.IGNORECASE,
    ),
    RiskFlag.LEGAL_THREAT: re.compile(
        r"\b(lawyer|attorney|sue\b|suing|lawsuit|court|legal action|police report|"
        r"avocat|poursuiv|tribunal|plainte|mise en demeure)",
        re.IGNORECASE,
    ),
    RiskFlag.FRAUD_ACCOUNT_TAKEOVER: re.compile(
        r"\b(hack|unauthori[sz]ed|fraud|stolen account|someone (used|logged)|"
        r"pirat|frauduleu|non autoris[ée]|vol de compte)",
        re.IGNORECASE,
    ),
    RiskFlag.MEDIA_THREAT: re.compile(
        r"\b(go(ing)? viral|the (news|press|media)|journalist|reporter|"
        r"m[ée]dias|journaliste|la presse)",
        re.IGNORECASE,
    ),
}


def lexicon_flags(text: str) -> list[RiskFlag]:
    return [flag for flag, pattern in _RISK_PATTERNS.items() if pattern.search(text)]


# --- fallback keyword categories (used only when no LLM is configured) -------------------------
_CATEGORY_KEYWORDS: dict[Category, re.Pattern[str]] = {
    Category.FARE_BILLING: re.compile(
        r"charg|refund|fare|price|surge|receipt|bill|factur|rembours|prix|tarif|re[çc]u", re.I
    ),
    Category.DRIVER_BEHAVIOUR: re.compile(r"driver|chauffeur|conducteur|rude|impoli", re.I),
    Category.LOST_ITEM: re.compile(r"\blost\b|left my|forgot|oubli|perdu", re.I),
    Category.CANCELLATION_NO_SHOW: re.compile(r"cancel|no.?show|waited|annul|attendu", re.I),
    Category.DELIVERY_ORDER: re.compile(
        r"order|food|meal|delivery|restaurant|commande|livraison|repas", re.I
    ),
    Category.APP_TECHNICAL: re.compile(r"\bapp\b|crash|bug|error|appli|erreur|plant", re.I),
    Category.ACCOUNT_ACCESS: re.compile(
        r"account|log ?in|password|locked|compte|mot de passe|bloqu", re.I
    ),
    Category.PROMOTIONS_CREDITS: re.compile(r"promo|code|credit|coupon|cr[ée]dit", re.I),
    Category.ACCESSIBILITY: re.compile(r"wheelchair|fauteuil roulant|disab|handicap", re.I),
}


def keyword_categories(text: str) -> list[Category]:
    found = [c for c, p in _CATEGORY_KEYWORDS.items() if p.search(text)]
    return found[:3] or [Category.OTHER]


@cache
def _classical():
    path = get_settings().models_dir / "classical.joblib"
    return joblib.load(path) if path.exists() else None


@cache
def _system_prompt() -> str:
    company = get_settings().company_name
    return (
        f"You analyse customer messages sent to {company}, a ride-hailing app that also delivers "
        "food (one app). Label the message exactly as defined in these annotation guidelines, "
        "which human annotators also follow:\n\n"
        f"{GUIDELINES.read_text(encoding='utf-8')}\n\n"
        "Return ONLY a JSON object with keys: message_type, response_required (bool), urgency "
        "(immediate|24h|standard, or null if no response is required), categories (1-3, main "
        "first), severity (1-4 for complaints, else null), risk_flags (list), sentiment "
        "(negative|neutral|positive), entities (list of {type, text}; types: DATE_TIME, MONEY, "
        "LOCATION, TRIP_REF, DRIVER_REF, PAYMENT_REF; text copied exactly from the message), "
        "summary (one neutral English sentence), customer_goal (English). Placeholders like "
        "[EMAIL_1] are masked personal data: never try to guess them."
    )


def analyse_with_llm(client: ChatClient, text: str) -> Analysis:
    return complete_json(client, _system_prompt(), f"Customer message:\n<<<\n{text}\n>>>", Analysis)


def fallback_analysis(text: str, p_complaint: float | None, severity: int | None) -> Analysis:
    is_complaint = (p_complaint or 0.0) >= 0.5
    return Analysis(
        message_type=MessageType.COMPLAINT if is_complaint else MessageType.REQUEST,
        response_required=True,
        urgency=Urgency.STANDARD,
        categories=keyword_categories(text),
        severity=severity if is_complaint else None,
        risk_flags=[],
        sentiment="negative" if is_complaint else "neutral",
        summary="(no LLM configured: summary unavailable)",
        customer_goal="(no LLM configured)",
    )


def understand_stage(ctx: Context) -> StageResult:
    text = ctx["text_masked"]
    classical: dict[str, object] = {}
    p_complaint: float | None = None
    sev_classical: int | None = None
    bundle = _classical()
    if bundle is not None:
        p_complaint = float(bundle["complaint"].predict_proba([text])[0][1])
        sev_classical = int(bundle["severity"].predict([text])[0])
        classical = {"complaint_probability": round(p_complaint, 3), "severity": sev_classical}

    client: ChatClient | None = ctx.get("llm")
    source = "llm" if client else "classical_fallback"
    if client:
        analysis = analyse_with_llm(client, text)
    else:
        analysis = fallback_analysis(text, p_complaint, sev_classical)

    lex = lexicon_flags(text)
    added = [f for f in lex if f not in analysis.risk_flags]
    if added:  # recall-first safety net
        analysis.risk_flags = [*analysis.risk_flags, *added]
        if analysis.urgency != Urgency.IMMEDIATE and set(added) & {
            RiskFlag.SAFETY,
            RiskFlag.INJURY,
            RiskFlag.HARASSMENT_DISCRIMINATION,
        }:
            analysis.urgency = Urgency.IMMEDIATE
            analysis.response_required = True

    disagreement = None
    if client and p_complaint is not None:
        llm_says = analysis.message_type == MessageType.COMPLAINT
        if llm_says != (p_complaint >= 0.5) and abs(p_complaint - 0.5) > 0.25:
            disagreement = "LLM and classical model disagree on complaint vs. not"

    ctx["analysis"] = analysis
    ctx["uncertain"] = disagreement is not None
    return StageResult(
        name="understand",
        output={
            **analysis.model_dump(mode="json"),
            "source": source,
            "classical": classical,
            "lexicon_flags_added": [f.value for f in added],
        },
        confidence=round(p_complaint, 3) if p_complaint is not None else None,
        note=disagreement,
    )


understand_stage.stage_name = "understand"  # type: ignore[attr-defined]
