import json

from complaintlens.silver import run
from tests.fakes import FakeLLM

LABELS = {
    "message_type": "complaint",
    "response_required": True,
    "urgency": "24h",
    "categories": ["fare_billing"],
    "severity": 2,
    "risk_flags": [],
}
MSGS = [{"id": f"m{i}", "text": f"text {i}"} for i in range(3)]


def answer(ids):
    return {"items": [{"id": i, "labels": LABELS} for i in ids]}


def test_batch_is_labelled_in_one_call_and_resumes(tmp_path):
    out = tmp_path / "silver.jsonl"
    llm = FakeLLM(answer(["m0", "m1", "m2"]))
    stats = run(llm, MSGS, out, batch_size=3)
    assert stats == {"skipped_already_done": 0, "labelled": 3, "failed": 0}
    assert len(llm.calls) == 1
    # Resume: nothing left to do, no new call.
    assert run(FakeLLM(), MSGS, out, batch_size=3)["skipped_already_done"] == 3


def test_invalid_batch_is_retried_message_by_message_and_failures_are_recorded(tmp_path):
    out = tmp_path / "silver.jsonl"
    bad_severity = {**LABELS, "message_type": "praise"}  # praise with a severity: invalid
    llm = FakeLLM(
        {"items": [{"id": "m0", "labels": bad_severity}]},  # batch answer: wrong
        "still not json",  # batch retry inside complete_json
        answer(["m0"]),  # m0 alone: fine
        answer(["m1"]),  # m1 alone: fine
        "garbage",  # m2 alone: fails twice
        "garbage",
    )
    stats = run(llm, MSGS[:3], out, batch_size=3)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert stats["labelled"] == 2 and stats["failed"] == 1
    assert [r["id"] for r in rows] == ["m0", "m1", "m2"]
    assert rows[2]["labels"] is None and "invalid" in rows[2]["error"]
