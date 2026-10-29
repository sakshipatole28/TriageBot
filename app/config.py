"""Configuration for TriageBot.

All settings come from environment variables. A local .env file is read too,
but real environment variables (from Docker, docker compose or Kubernetes)
always win, because we load .env with override=False.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env if it exists. Existing environment variables are NOT overwritten.
load_dotenv(BASE_DIR / ".env", override=False)

APP_NAME = "TriageBot - Multi-Agent Bug Triage Assistant"

# API keys (never hardcode these, never log them)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()

# Provider: "google" or "groq". If not set, use Google when a Gemini key exists.
MODEL_PROVIDER: str = (
    os.getenv("MODEL_PROVIDER", "").strip().lower()
    or ("google" if GEMINI_API_KEY else "groq")
)

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()

HOST: str = os.getenv("HOST", "127.0.0.1").strip()
PORT: int = int(os.getenv("PORT", "8000"))
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "90"))

# Values people often leave in .env by mistake; treat them as "no key".
PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_groq_api_key_here", "placeholder", "changeme"}


def active_api_key() -> str:
    """Return the API key for the selected provider (may be empty)."""
    return GEMINI_API_KEY if MODEL_PROVIDER == "google" else GROQ_API_KEY


def is_provider_configured() -> bool:
    """True when the selected provider has a real-looking API key."""
    return active_api_key() not in PLACEHOLDER_KEYS


def get_active_model_name() -> str:
    """Human readable provider + model name, e.g. 'Groq (openai/gpt-oss-20b)'."""
    if MODEL_PROVIDER == "google":
        return f"Google ({GEMINI_MODEL})"
    return f"Groq ({GROQ_MODEL})"


def redact_secrets(text: str) -> str:
    """Replace any API key that appears in a message with [REDACTED]."""
    for key in (GEMINI_API_KEY, GROQ_API_KEY):
        if key and key not in PLACEHOLDER_KEYS:
            text = text.replace(key, "[REDACTED]")
    return text
