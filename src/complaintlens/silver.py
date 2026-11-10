"""Silver labelling: an LLM labels many training messages with the human annotation guidelines.

These labels train the small multilingual encoder (RQ1, distillation). Their quality is *measured*
against the human gold labels, never assumed.

Budget-aware design: free LLM tiers limit tokens per day and the guidelines prompt is long, so
messages are labelled in batches (one prompt, many messages, one JSON answer per message). Every
answer is validated with the same ``Labels`` schema as the humans; a batch that fails validation is
split and retried message by message; a message that still fails is recorded as failed, never
silently guessed. Output is append-only JSONL, so a run stopped by a quota resumes where it stopped.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from complaintlens.annotation import Labels
from complaintlens.llm import ChatClient, LLMOutputError, complete_json
from complaintlens.pipeline.understand import GUIDELINES


class _Item(BaseModel):
    id: str
    labels: Labels


class _Batch(BaseModel):
    items: list[_Item] = Field(min_length=1)


SYSTEM = (
    "You label customer messages sent to a ride-hailing app. Apply these "
    "annotation guidelines exactly, as the human annotators do:\n\n{guidelines}\n\n"
    "For EACH message return its id and labels: message_type, response_required (bool), urgency "
    "(immediate|24h|standard, null when no response is required), categories (1-3, main first), "
    "severity (1-4 for complaints only, else null), risk_flags (list). [COMPANY], [USER], [URL] "
    'are placeholders. Return ONLY JSON: {{"items": [{{"id": ..., "labels": {{...}}}}, ...]}}.'
)


def _system() -> str:
    return SYSTEM.format(guidelines=GUIDELINES.read_text(encoding="utf-8"))


def label_batch(client: ChatClient, batch: list[dict]) -> list[dict]:
    """Label a batch; on a malformed answer, retry each message alone. Returns one row per input."""
    user = "Messages:\n" + "\n".join(
        json.dumps({"id": m["id"], "text": m["text"]}, ensure_ascii=False) for m in batch
    )
    try:
        result = complete_json(client, _system(), user, _Batch)
        by_id = {i.id: i.labels for i in result.items}
        if set(by_id) == {m["id"] for m in batch}:
            return [
                {
                    "id": m["id"],
                    "labels": by_id[m["id"]].model_dump(mode="json"),
                    "model": client.model,
                }
                for m in batch
            ]
    except (LLMOutputError, ValidationError):
        pass
    if len(batch) == 1:
        return [
            {
                "id": batch[0]["id"],
                "labels": None,
                "error": "invalid after retry",
                "model": client.model,
            }
        ]
    rows: list[dict] = []
    for m in batch:
        rows.extend(label_batch(client, [m]))
    return rows


def already_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line
    }


def batched(items: Iterable[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def run(
    client: ChatClient, messages: list[dict], out: Path, batch_size: int = 20
) -> dict[str, int]:
    """Label ``messages`` (dicts with id, text) into ``out``, skipping ids already labelled."""
    done = already_done(out)
    todo = [m for m in messages if m["id"] not in done]
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {"skipped_already_done": len(done), "labelled": 0, "failed": 0}
    with out.open("a", encoding="utf-8") as f:
        for batch in batched(todo, batch_size):
            for row in label_batch(client, batch):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["failed" if row["labels"] is None else "labelled"] += 1
            f.flush()  # a quota error mid-run loses at most the current batch
    return stats
