"""Settings loaded from environment variables (and an optional .env at the project root)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    # The project's .env wins over stale variables already set in the shell or Windows settings,
    # so a leftover GEMINI_MODEL from an earlier setup cannot silently override it.
    load_dotenv(ROOT / ".env", override=True)


@dataclass
class Settings:
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    # Development-only simulator. Never use it for the hackathon demo video.
    fake_paypal: bool = False

    mongodb_uri: str = ""
    mongodb_db: str = "proofpay"
    storage_mode: str = "auto"  # auto | mongo | local
    local_data_file: str = str(ROOT / "backend" / "data" / "proofpay_local.json")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_timeout_seconds: float = 40.0

    github_token: str = ""
    cors_origins: list = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    allow_demo_reset: bool = True
    currency: str = "USD"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def ai_provider_name(self) -> str:
        if self.gemini_api_key:
            return "gemini"
        if self.ai_api_key and self.ai_base_url and self.ai_model:
            return "openai-compatible"
        return ""


def _bool(value: str, default: bool) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    _load_env()
    e = os.environ.get
    origins = [o.strip() for o in e("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    return Settings(
        paypal_client_id=e("PAYPAL_CLIENT_ID", "").strip(),
        paypal_client_secret=e("PAYPAL_CLIENT_SECRET", "").strip(),
        fake_paypal=_bool(e("PROOFPAY_FAKE_PAYPAL", ""), False),
        mongodb_uri=e("MONGODB_URI", "").strip(),
        mongodb_db=e("MONGODB_DB", "proofpay").strip() or "proofpay",
        storage_mode=e("STORAGE_MODE", "auto").strip().lower() or "auto",
        local_data_file=e("LOCAL_DATA_FILE", "").strip() or str(ROOT / "backend" / "data" / "proofpay_local.json"),
        gemini_api_key=e("GEMINI_API_KEY", "").strip(),
        gemini_model=e("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite",
        ai_api_key=e("AI_API_KEY", "").strip(),
        ai_base_url=e("AI_BASE_URL", "").strip().rstrip("/"),
        ai_model=e("AI_MODEL", "").strip(),
        ai_timeout_seconds=float(e("AI_TIMEOUT_SECONDS", "40") or 40),
        github_token=e("GITHUB_TOKEN", "").strip(),
        cors_origins=origins,
        allow_demo_reset=_bool(e("ALLOW_DEMO_RESET", ""), True),
        currency=(e("CURRENCY", "USD").strip() or "USD").upper(),
    )
