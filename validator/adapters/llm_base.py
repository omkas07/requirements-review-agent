"""Общая часть LLM-адаптеров: валидация по схеме, повторы, паузы, кеш, счётчики."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("validator.llm")


class LLMError(RuntimeError):
    pass


class JSONLLMClient:
    """Реализует LLMClient.ask_json. Наследник задаёт _call и _retry_delay."""

    provider = "base"

    def __init__(self, model: str, temperature: float = 0.0, max_attempts: int = 6, cache_dir: Path | None = None):
        self.model = model
        self.temperature = temperature
        self.max_attempts = max_attempts
        self.cache_dir = cache_dir
        self.requests = 0  # вызовов ask_json
        self.calls = 0  # HTTP-запросов, включая повторы
        self.tokens_in = 0
        self.tokens_out = 0

    # --- переопределяют адаптеры ------------------------------------------ #
    def _call(self, prompt: str, schema: type[BaseModel]) -> tuple[str, int, int]:
        """Один запрос к API: (текст ответа, токены на вход, токены на выход)."""
        raise NotImplementedError

    def _retry_delay(self, error: Exception, attempt: int) -> float | None:
        """Пауза перед повтором для ошибки API или None, если повторять бессмысленно."""
        return None

    # --- общее ------------------------------------------------------------ #
    def _cache_file(self, prompt: str, schema: type[BaseModel]) -> Path | None:
        if self.cache_dir is None:
            return None
        key = f"{self.provider}|{self.model}|{self.temperature}|{getattr(self, 'reasoning_effort', None)}|{schema.__name__}|{prompt}"
        return self.cache_dir / f"{schema.__name__}_{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"

    def ask_json(self, prompt: str, schema: type[T]) -> T:
        self.requests += 1
        cache = self._cache_file(prompt, schema)
        if cache is not None and cache.exists():
            return schema.model_validate_json(cache.read_text(encoding="utf-8"))

        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.calls += 1
            try:
                text, tin, tout = self._call(prompt, schema)
            except Exception as e:  # noqa: BLE001 — решает _retry_delay
                delay = self._retry_delay(e, attempt)
                if delay is None:
                    raise LLMError(f"{self.provider}: {type(e).__name__}: {e}") from e
                last = e
                log.warning("%s: %s, повтор через %.0f с (попытка %d)", self.provider, _short(e), delay, attempt)
                time.sleep(delay)
                continue
            self.tokens_in += tin
            self.tokens_out += tout
            try:
                result = schema.model_validate_json(_strip_fences(text))
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last = e
                log.warning("%s: невалидный JSON для %s (попытка %d): %s", self.provider, schema.__name__, attempt, _short(e))
                continue
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(result.model_dump_json(), encoding="utf-8")
            return result
        raise LLMError(f"{self.provider}: нет валидного ответа за {self.max_attempts} попыток: {_short(last)}")


def backoff(attempt: int, cap: float = 60.0) -> float:
    return min(cap, 2.0 * 2 ** (attempt - 1))


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _short(e: Exception | None) -> str:
    return (f"{type(e).__name__}: {e}" if e else "—")[:300]
