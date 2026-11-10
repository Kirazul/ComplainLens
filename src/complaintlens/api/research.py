"""The console's research pages (signed in): Insights and Annotate.

- Insights: daily volume, detected incidents and problem clusters of the real Uber stream, and
  the report's headline numbers, each traced to the results file that produced it.
- Annotate: the gold sets. Labels are saved under the signed-in account, so two team members
  labelling the pilot set give the inter-annotator agreement.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from complaintlens import annotation
from complaintlens.auth import CurrentUser, current_user
from complaintlens.settings import ROOT
from complaintlens.store import AnnotationItem, new_session

router = APIRouter(prefix="/api", tags=["research"], dependencies=[Depends(current_user)])


GOLD_DIR = ROOT / "eval" / "gold"


class AnnotateIn(BaseModel):
    item_id: str
    labels: annotation.Labels


class NewItemIn(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    lang: str = Field(pattern="^(en|fr)$")


@router.get("/annotate/next")
def annotate_next(user: CurrentUser, set: str = "pilot") -> dict[str, Any]:
    if set not in annotation.SETS:
        raise HTTPException(400, f"set must be one of {annotation.SETS}")
    with new_session() as s:
        item = annotation.next_item(s, user.username, set)
        return {
            "item": item.model_dump() if item else None,
            "progress": annotation.progress(s),
        }


@router.post("/annotate")
def annotate_save(payload: AnnotateIn, user: CurrentUser) -> dict[str, Any]:
    with new_session() as s:
        if s.get(AnnotationItem, payload.item_id) is None:
            raise HTTPException(404, "item not found")
        annotation.save(s, payload.item_id, user.username, payload.labels)
        return {"saved": True, "progress": annotation.progress(s)}


@router.post("/annotate/items", status_code=201)
def annotate_add_item(payload: NewItemIn) -> dict[str, Any]:
    """Author a gold message (used for the French set: no licensed French data exists)."""
    with new_session() as s:
        prefix = f"{payload.lang}-authored-"
        count = s.exec(
            select(func.count())
            .select_from(AnnotationItem)
            .where(col(AnnotationItem.id).startswith(prefix))
        ).one()
        item = AnnotationItem(
            id=f"{prefix}{count + 1:04d}",
            set=f"gold_{payload.lang}",
            lang=payload.lang,
            text=payload.text.strip(),
            meta={"source": "authored by the team (fictional, no personal data)"},
        )
        s.add(item)
        s.commit()
        return item.model_dump()


@router.get("/annotate/agreement")
def annotate_agreement(set: str = "pilot") -> dict[str, Any]:
    with new_session() as s:
        return annotation.agreement(s, set)


RESULTS_DIR = ROOT / "reports" / "results"


def _result(name: str) -> dict[str, Any]:
    path = RESULTS_DIR / name
    if not path.exists():
        raise HTTPException(404, f"{name} not generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/insights")
def insights() -> dict[str, Any]:
    return _result("insights_uber.json")


@router.get("/experiments")
def experiments() -> list[dict[str, Any]]:
    """Headline numbers of the report, each with the results file that produced it."""
    rows: list[dict[str, Any]] = []

    def add(question: str, claim: str, value: str, source: str) -> None:
        rows.append({"question": question, "claim": claim, "value": value, "source": source})

    if (RESULTS_DIR / "baseline_complaints2019.json").exists():
        b = _result("baseline_complaints2019.json")
        best = b["task_a_complaint_vs_not"]["models"]["tfidf_word+char_lr"]
        sev = b["task_b_severity_on_complaints"]["models"]["tfidf_word+char_lr"]
        add(
            "RQ1",
            "Complaint vs. not, macro-F1 (published non-neural best: 79.0)",
            f"{best['macro_f1_mean'] * 100:.1f} ± {best['macro_f1_std'] * 100:.1f}",
            "baseline_complaints2019.json",
        )
        add(
            "RQ1",
            "Severity 1-4, macro-F1 (published LR-BOW: 43.5)",
            f"{sev['macro_f1_mean'] * 100:.1f} ± {sev['macro_f1_std'] * 100:.1f}",
            "baseline_complaints2019.json",
        )
    if (RESULTS_DIR / "gate_complaints2019.json").exists():
        g = _result("gate_complaints2019.json")["methods"]["gate_alpha_0.1"]
        add(
            "RQ2",
            "Messages automated at a guaranteed 10% error bound",
            f"{g['automation_rate_mean'] * 100:.1f}% (violations: {g['violations_of_alpha']})",
            "gate_complaints2019.json",
        )
    if (RESULTS_DIR / "retrieval_helpcenter.json").exists():
        r = _result("retrieval_helpcenter.json")["retrievers"]
        dense = next(v for k, v in r.items() if k.startswith("dense"))
        add(
            "RQ3",
            "Help Center retrieval MRR@10, dense vs. BM25 (development set)",
            f"{dense['mrr@10']:.2f} vs. {r['bm25']['mrr@10']:.2f}",
            "retrieval_helpcenter.json",
        )
    if (RESULTS_DIR / "trends_uber.json").exists():
        t = _result("trends_uber.json")
        z = t["methods"]["zscore"]["injection_recall_test"]["20"]["mean"]
        c = t["methods"]["count_threshold"]["injection_recall_test"]["20"]["mean"]
        add(
            "RQ4",
            "Recall on injected 20-message bursts, z-score vs. count threshold",
            f"{z:.2f} vs. {c:.2f}",
            "trends_uber.json",
        )
        add(
            "RQ4",
            "Delay before the 14 Nov 2017 promotion-crash alert",
            f"{t['real_event_hourly']['delay_hours']} h",
            "trends_uber.json",
        )
    if (RESULTS_DIR / "rootcause_simulation.json").exists():
        rc = next(
            c
            for c in _result("rootcause_simulation.json")["conditions"]
            if c["incident_size"] == 50 and c["purity"] == 0.5
        )
        add(
            "RQ5",
            "Probable cause precision@k, mixed incident of 50 tickets",
            f"{rc['precision_at_k_ours']:.2f} vs. {rc['precision_at_k_most_frequent']:.2f}",
            "rootcause_simulation.json",
        )
    return rows
