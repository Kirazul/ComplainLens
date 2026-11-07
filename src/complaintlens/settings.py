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
    company_city: str = "Montréal"

    # LLM: any OpenAI-compatible endpoint (Groq by default, or local Ollama).
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_cache_dir: Path = ROOT / "data" / "cache" / "llm"

    # Retrieval: "hybrid" (BM25 + dense, RRF) or "bm25". Model choice: see
    # reports/results/retrieval_helpcenter.json.
    retrieval: str = "hybrid"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'app.db').as_posix()}"
    models_dir: Path = ROOT / "models"
    help_center_dir: Path = ROOT / "company" / "help_center"

    # Email channel (Gmail with an app password, or any IMAP/SMTP provider).
    email_address: str = ""
    email_password: str = ""
    imap_host: str = "imap.gmail.com"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465

    public_base_url: str = "http://localhost:3000"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) or "localhost" in self.llm_base_url

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_address and self.email_password)


@cache
def get_settings() -> Settings:
    return Settings()
