import json

import pytest
from pydantic import ValidationError

from complaintlens.annotation import (
    Labels,
    agreement,
    is_double,
    load_items,
    next_item,
    progress,
    save,
)
from complaintlens.store import new_session

COMPLAINT = dict(
    message_type="complaint",
    response_required=True,
    urgency="24h",
    categories=["fare_billing"],
    severity=2,
)


@pytest.fixture
def session(tmp_path):
    items = tmp_path / "items.jsonl"
    rows = [
        {
            "id": f"en-{i:04d}",
            "set": "pilot" if i <= 3 else "gold_en",
            "lang": "en",
            "text": f"msg {i}",
        }
        for i in range(1, 21)
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    with new_session(f"sqlite:///{(tmp_path / 'a.db').as_posix()}") as s:
        assert load_items(s, items) == 20
        assert load_items(s, items) == 0  # idempotent
        yield s


def test_labels_reject_inconsistent_combinations():
    Labels(**COMPLAINT)
    with pytest.raises(ValidationError):
        Labels(**{**COMPLAINT, "severity": None})  # complaint without severity
    with pytest.raises(ValidationError):
        Labels(**{**COMPLAINT, "message_type": "praise"})  # praise with severity
    with pytest.raises(ValidationError):
        Labels(**{**COMPLAINT, "response_required": False})  # urgency without reply


def test_pilot_items_go_to_every_annotator(session):
    for who in ("aziz", "rimel"):
        seen = []
        while (item := next_item(session, who, "pilot")) is not None:
            seen.append(item.id)
            save(session, item.id, who, Labels(**COMPLAINT))
        assert seen == ["en-0001", "en-0002", "en-0003"]


def test_single_gold_items_are_not_given_twice(session):
    single = [i for i in (f"en-{n:04d}" for n in range(4, 21)) if not is_double(i)]
    item = next_item(session, "aziz", "gold_en")
    while item is not None and is_double(item.id):
        save(session, item.id, "aziz", Labels(**COMPLAINT))
        item = next_item(session, "aziz", "gold_en")
    assert item is not None and item.id in single
    save(session, item.id, "aziz", Labels(**COMPLAINT))
    # Rimel never receives an item Aziz already labelled alone.
    labelled_by_rimel = []
    while (other := next_item(session, "rimel", "gold_en")) is not None:
        labelled_by_rimel.append(other.id)
        save(session, other.id, "rimel", Labels(**COMPLAINT))
    assert item.id not in labelled_by_rimel


def test_agreement_reports_kappa_per_field(session):
    for i, who_labels in enumerate(
        [("complaint", "complaint"), ("complaint", "request"), ("request", "request")]
    ):
        item_id = f"en-{i + 1:04d}"
        for who, mtype in zip(("aziz", "rimel"), who_labels, strict=True):
            labels = (
                COMPLAINT
                if mtype == "complaint"
                else {**COMPLAINT, "message_type": "request", "severity": None}
            )
            save(session, item_id, who, Labels(**labels))
    result = agreement(session, "pilot")
    assert result["double_labelled_items"] == 3
    assert result["fields"]["message_type"]["agreement"] == round(2 / 3, 3)
    assert result["fields"]["message_type"]["kappa"] is not None
    assert progress(session)["labelled"]["pilot"] == {"aziz": 3, "rimel": 3}
