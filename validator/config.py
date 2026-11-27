"""Настройки из .env и окружения. Выбор провайдера LLM — LLM_PROVIDER."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_OPENAI_MODEL = "gpt-6-luna"
PROVIDERS = ("gemini", "openai")


class ConfigError(RuntimeError):
    """Понятная пользователю ошибка настройки (нет ключа, неизвестный провайдер)."""


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    model: str
    temperature: float = 0.0
    max_attempts: int = 6
    cache_dir: Path | None = None  # кеш ответов LLM для отладки; выключен по умолчанию
    reasoning_effort: str | None = None  # только OpenAI: "none" — без рассуждений, зато temperature=0


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env", override=False)
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"LLM_PROVIDER={provider!r}: поддерживаются {', '.join(PROVIDERS)}")
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        model = os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        hint = "GEMINI_API_KEY (бесплатный ключ: https://aistudio.google.com/ → Get API key)"
    else:
        key = os.getenv("OPENAI_API_KEY") or ""
        model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        hint = "OPENAI_API_KEY"
    if not key.strip() or key.startswith("your_"):
        raise ConfigError(f"Нет ключа LLM: укажите {hint} в файле .env в корне проекта (образец — .env.example)")
    cache = os.getenv("LLM_CACHE_DIR")
    return Settings(
        provider=provider,
        api_key=key.strip(),
        model=model.strip(),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        max_attempts=int(os.getenv("LLM_MAX_ATTEMPTS", "6")),
        cache_dir=Path(cache) if cache else None,
        reasoning_effort=(os.getenv("OPENAI_REASONING_EFFORT", "none").strip() or None) if provider == "openai" else None,
    )
