"""Small LLM client: OpenAI-compatible chat API, JSON output validated by Pydantic, disk cache.

- Provider-agnostic: Groq (default, free tier) or local Ollama through the same API, so the model is
  a configuration choice and is recorded with every result (spec §4H).
- ``complete_json`` asks for a JSON object, validates it against a Pydantic model and retries once
  with the validation error if the model's answer is malformed.
- Responses are cached on disk by (model, messages, temperature): the same demo input never costs a
  second call, and re-running an evaluation is free and reproducible.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from complaintlens.settings import Settings, get_settings


class ChatClient(Protocol):
    """Anything that turns chat messages into a text answer (real API or a test fake)."""

    model: str

    def chat(self, messages: list[dict[str, str]], temperature: float, json_mode: bool) -> str: ...


class OpenAICompatibleClient:
    def __init__(self, settings: Settings | None = None) -> None:
        from openai import OpenAI  # imported lazily: tests never need the network client

        s = settings or get_settings()
        self.model = s.llm_model
        self._client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key or "none", timeout=60)

    def chat(self, messages: list[dict[str, str]], temperature: float, json_mode: bool) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, **kwargs
        )
        return resp.choices[0].message.content or ""


class CachedClient:
    """Wrap a client with a JSON-file cache keyed by the exact request."""

    def __init__(self, inner: ChatClient, cache_dir: Path) -> None:
        self.inner, self.model, self.cache_dir = inner, inner.model, cache_dir

    def chat(self, messages: list[dict[str, str]], temperature: float, json_mode: bool) -> str:
        key = hashlib.sha256(
            json.dumps([self.model, messages, temperature, json_mode], ensure_ascii=False).encode()
        ).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["content"]
        content = self.inner.chat(messages, temperature, json_mode)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"model": self.model, "content": content}, ensure_ascii=False),
            encoding="utf-8",
        )
        return content


def default_client() -> ChatClient | None:
    """The configured LLM client, or None if none is configured (the pipeline then degrades)."""
    s = get_settings()
    if not s.llm_enabled:
        return None
    return CachedClient(OpenAICompatibleClient(s), s.llm_cache_dir)


class LLMOutputError(RuntimeError):
    pass


def complete_json[T: BaseModel](
    client: ChatClient,
    system: str,
    user: str,
    schema: type[T],
    temperature: float = 0.0,
) -> T:
    """Ask for JSON matching ``schema``; retry once with the validation error; else raise."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error = ""
    for _ in range(2):
        raw = client.chat(messages, temperature, json_mode=True)
        try:
            return schema.model_validate_json(_strip_fences(raw))
        except ValidationError as exc:
            last_error = str(exc)
            messages = [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": f"Your JSON was invalid:\n{last_error}\nReturn corrected JSON only.",
                },
            ]
    raise LLMOutputError(last_error)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()
