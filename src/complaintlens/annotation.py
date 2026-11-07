"""Gold-set annotation: items, assignment, validation and inter-annotator agreement (plan §5.3).

Workflow:
1. PILOT: every annotator labels the same 50 items; agreement is measured per field; the guidelines
   are revised (eval/annotation_guidelines.md, "Borderline cases log").
2. GOLD: the remaining items are shared; about 30% (chosen by a stable hash of the item ID) are
   labelled by every annotator so agreement can be reported on the full set too.

Agreement: Cohen's kappa per field (quadratic-weighted for the ordinal severity, where confusing
1 with 4 is worse than 3 with 4) and raw percentage agreement. Multi-label fields (categories, risk
flags) are compared on the main category and per flag.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sklearn.metrics import cohen_kappa_score
from sqlmodel import Session, func, select

from complaintlens.schemas import Category, MessageType, RiskFlag, Urgency
from complaintlens.store import Annotation, AnnotationItem

DOUBLE_SHARE = 0.3
SETS = ("pilot", "gold_en", "gold_fr")


class Labels(BaseModel):
    """One annotator's labels for one message (same fields as eval/annotation_guidelines.md)."""

    message_type: MessageType
    response_required: bool
    urgency: Urgency | None = None
    categories: list[Category] = Field(min_length=1, max_length=3)
    severity: int | None = Field(default=None, ge=1, le=4)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def consistent(self) -> Labels:
        if self.message_type != MessageType.COMPLAINT and self.severity is not None:
            raise ValueError("severity is only given for complaints")
        if self.message_type == MessageType.COMPLAINT and self.severity is None:
            raise ValueError("complaints need a severity (1-4)")
        if not self.response_required and self.urgency is not None:
            raise ValueError("urgency is only given when a response is required")
        if self.response_required and self.urgency is None:
            raise ValueError("choose an urgency when a response is required")
        return self


def is_double(item_id: str) -> bool:
    """Stable choice of the ~30% gold items that every annotator labels."""
    h = int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16)
    return h % 100 < DOUBLE_SHARE * 100


def load_items(session: Session, path: Path) -> int:
    """Insert items from a JSONL file if they are not in the database yet."""
    added = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if session.get(AnnotationItem, raw["id"]) is None:
            meta = {k: v for k, v in raw.items() if k not in {"id", "set", "lang", "text"}}
            session.add(
                AnnotationItem(
                    id=raw["id"], set=raw["set"], lang=raw["lang"], text=raw["text"], meta=meta
                )
            )
            added += 1
    session.commit()
    return added


def next_item(session: Session, annotator: str, set_name: str) -> AnnotationItem | None:
    """Next item for this annotator: pilot items are for everyone; gold items are double-labelled
    when ``is_double``, otherwise labelled once by whoever reaches them first."""
    mine = set(session.exec(select(Annotation.item_id).where(Annotation.annotator == annotator)))
    labelled_by_anyone = set(session.exec(select(Annotation.item_id)))
    items = session.exec(
        select(AnnotationItem).where(AnnotationItem.set == set_name).order_by(AnnotationItem.id)
    )
    for item in items:
        if item.id in mine:
            continue
        if set_name == "pilot" or is_double(item.id) or item.id not in labelled_by_anyone:
            return item
    return None


def save(session: Session, item_id: str, annotator: str, labels: Labels) -> Annotation:
    existing = session.exec(
        select(Annotation).where(Annotation.item_id == item_id, Annotation.annotator == annotator)
    ).first()
    record = existing or Annotation(item_id=item_id, annotator=annotator)
    record.labels = labels.model_dump(mode="json")
    session.add(record)
    session.commit()
    return record


def progress(session: Session) -> dict[str, Any]:
    totals = dict(
        session.exec(select(AnnotationItem.set, func.count()).group_by(AnnotationItem.set)).all()
    )
    rows = session.exec(
        select(AnnotationItem.set, Annotation.annotator, func.count())
        .join(Annotation, Annotation.item_id == AnnotationItem.id)
        .group_by(AnnotationItem.set, Annotation.annotator)
    ).all()
    done: dict[str, dict[str, int]] = {}
    for set_name, annotator, n in rows:
        done.setdefault(set_name, {})[annotator] = n
    return {"items": totals, "labelled": done}


def _pairs(session: Session, set_name: str) -> list[tuple[dict, dict]]:
    by_item: dict[str, list[Annotation]] = {}
    q = (
        select(Annotation)
        .join(AnnotationItem, Annotation.item_id == AnnotationItem.id)
        .where(AnnotationItem.set == set_name)
        .order_by(Annotation.annotator)
    )
    for a in session.exec(q):
        by_item.setdefault(a.item_id, []).append(a)
    return [(v[0].labels, v[1].labels) for v in by_item.values() if len(v) >= 2]


def _kappa(a: list, b: list, weights: str | None = None) -> float | None:
    if len(a) < 2 or len(set(a) | set(b)) < 2:
        return None  # undefined: a single category everywhere
    return round(float(cohen_kappa_score(a, b, weights=weights)), 3)


def agreement(session: Session, set_name: str = "pilot") -> dict[str, Any]:
    pairs = _pairs(session, set_name)
    out: dict[str, Any] = {"set": set_name, "double_labelled_items": len(pairs), "fields": {}}
    if not pairs:
        return out

    def field(name: str, values: list[tuple[Any, Any]], weights: str | None = None) -> None:
        a, b = [str(x) for x, _ in values], [str(y) for _, y in values]
        out["fields"][name] = {
            "kappa": _kappa(a, b, weights),
            "agreement": round(sum(x == y for x, y in zip(a, b, strict=True)) / len(a), 3),
        }

    field("message_type", [(x["message_type"], y["message_type"]) for x, y in pairs])
    field("response_required", [(x["response_required"], y["response_required"]) for x, y in pairs])
    field("urgency", [(x.get("urgency"), y.get("urgency")) for x, y in pairs])
    field("main_category", [(x["categories"][0], y["categories"][0]) for x, y in pairs])
    sev = [(x.get("severity") or 0, y.get("severity") or 0) for x, y in pairs]
    out["fields"]["severity"] = {
        "kappa_quadratic": _kappa([a for a, _ in sev], [b for _, b in sev], "quadratic"),
        "agreement": round(sum(a == b for a, b in sev) / len(sev), 3),
    }
    for flag in RiskFlag:
        values = [(flag.value in x["risk_flags"], flag.value in y["risk_flags"]) for x, y in pairs]
        if any(a or b for a, b in values):
            field(f"risk:{flag.value}", values)
    return out
