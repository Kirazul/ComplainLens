"""Test doubles: a fake LLM that answers from a queue, recording the prompts it received."""

from __future__ import annotations

import json
from typing import Any


class FakeLLM:
    model = "fake-llm"

    def __init__(self, *answers: dict[str, Any] | str) -> None:
        self.answers = list(answers)
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], temperature: float, json_mode: bool) -> str:
        self.calls.append(messages)
        answer = self.answers.pop(0)
        return answer if isinstance(answer, str) else json.dumps(answer)
