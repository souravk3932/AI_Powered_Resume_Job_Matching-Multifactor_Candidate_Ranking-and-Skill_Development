"""LLM settings, read from environment variables (the .env file).

Nothing here is hard-coded to one provider: change LLM_PROVIDER / LLM_MODEL in
.env to switch. The API key lives ONLY in .env and is never logged or returned.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROVIDER = "groq"
DEFAULT_MODEL = "openai/gpt-oss-20b"  # supports strict structured JSON on Groq


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    model: str
    api_key: str
    timeout_seconds: float
    max_attempts: int  # how many times we ask again when the JSON is invalid


def _number(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        value = default
    return min(max(value, low), high)


def load_settings() -> LlmSettings:
    """Read settings each time, so a changed .env is picked up after a restart."""
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    return LlmSettings(
        provider=provider,
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL).strip(),
        api_key=os.getenv(f"{provider.upper()}_API_KEY", "").strip(),
        timeout_seconds=_number("LLM_TIMEOUT_SECONDS", 30, 5, 120),
        max_attempts=int(_number("LLM_MAX_ATTEMPTS", 2, 1, 4)),
    )
