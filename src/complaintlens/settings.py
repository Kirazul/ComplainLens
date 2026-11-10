"""Configuration from environment variables (or a local ``.env`` file, never committed).

Secrets (API keys, the mailbox app password) live only in the environment (global rule).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    company_name: str = "LunaGo"

    # LLM: any OpenAI-compatible endpoint (Groq by default, or local Ollama).
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    # Chosen 2026-11-10 among the models this Groq key can use (gpt-oss-120b, gpt-oss-20b,
    # qwen3.8-27b; all 1,000 requests/day, 8,000 tokens/min): most complete structured output in a
    # side-by-side test, ~1 s per call. Open weights, so results stay reproducible.
    llm_model: str = "openai/gpt-oss-120b"
    llm_reasoning_effort: str = "low"  # gpt-oss reasoning budget: fast and cheap in tokens
    llm_cache_dir: Path = ROOT / "data" / "cache" / "llm"

    # Retrieval: "dense", "hybrid" (BM25 + dense, RRF) or "bm25". Chosen on the development
    # question set (reports/results/retrieval_helpcenter.json): dense MRR 0.61 vs BM25 0.49
    # (p = 0.022); RRF hybrid 0.54 (not significant): BM25 is too weak on customer wording.
    retrieval: str = "dense"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Use the model's official int8 ONNX file: the service then fits a 1 GB container. Cost on
    # the development questions: MRR 0.59 vs 0.61, not significant (results/retrieval_int8.json).
    embedding_int8: bool = True

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'app.db').as_posix()}"
    models_dir: Path = ROOT / "models"
    help_center_dir: Path = ROOT / "company" / "help_center"

    # Email channel. "imap": any IMAP/SMTP mailbox (e.g. Gmail with an app password), which
    # receives and sends. "mailtm": a free mail.tm inbox (no sign-up), which receives only:
    # replies are then read on the tracking page and in the console.
    email_inbox: str = "imap"
    email_address: str = ""
    email_password: str = ""
    imap_host: str = "imap.gmail.com"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    mailtm_api: str = "https://api.mail.tm"

    # Console sign-in. The first administrator is created at startup with these credentials
    # (only if no account exists yet; later changes are made in the console's Team page).
    # Without ADMIN_PASSWORD the password is "admin": fine on a laptop, never on a server.
    admin_username: str = "admin"
    admin_password: str = ""
    session_hours: int = 12
    # Shared secret of the forum relay (GitHub Actions). Empty = forum channel disabled.
    channel_token: str = ""
    # Abuse and quota protection for public messages (each one costs two LLM calls). A chat
    # conversation sends several messages, hence 30 per hour.
    messages_per_ip_per_hour: int = 30
    messages_per_day: int = 300

    public_base_url: str = "http://localhost:3000"
    # Extra browser origins allowed to call the API (comma-separated), e.g. the website's origin.
    # localhost:3000 is always allowed.
    cors_origins: str = ""

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) or "localhost" in self.llm_base_url

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_address and self.email_password)

    @property
    def email_can_send(self) -> bool:
        return self.email_enabled and self.email_inbox == "imap"


@cache
def get_settings() -> Settings:
    return Settings()
