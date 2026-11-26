"""ВРЕМЕННЫЙ клиент Gemini для отладки агентов (в сдачу не идёт).

Боевой адаптер — validator/adapters/llm_gemini.py (тиммейт 1).
Ключ: GEMINI_API_KEY в окружении или в .env в корне проекта.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gemini-3.8-flash"
CACHE_DIR = ROOT / "dev" / ".cache"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class DevGeminiClient:
    """ask_json(prompt, schema) -> model. temperature=0, ретраи на 429/5xx и невалидный JSON.

    use_cache=True кеширует ответы по хешу промпта в dev/.cache — чтобы при отладке
    одного узла не тратить лимит бесплатного ключа на повтор предыдущих.
    """

    def __init__(self, model: str | None = None, use_cache: bool = False, max_attempts: int = 6):
        _load_dotenv()
        from google import genai

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Нет GEMINI_API_KEY: положите ключ в .env или в окружение")
        self.client = genai.Client(api_key=key)
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self.temperature = float(os.environ.get("DEV_TEMPERATURE", "0"))
        self.use_cache = use_cache
        self.max_attempts = max_attempts
        self.calls = 0  # реальных HTTP-запросов (с ретраями)
        self.requests = 0  # вызовов ask_json
        self.tokens_in = 0
        self.tokens_out = 0
        self.log: list[dict] = []

    def _cache_path(self, prompt: str, schema: type[BaseModel]) -> Path:
        import hashlib

        h = hashlib.sha256(f"{self.model}|{self.temperature}|{schema.__name__}|{prompt}".encode()).hexdigest()[:24]
        return CACHE_DIR / f"{schema.__name__}_{h}.json"

    def ask_json(self, prompt: str, schema: type[T]) -> T:
        from google.genai import errors, types

        self.requests += 1
        cache = self._cache_path(prompt, schema)
        if self.use_cache and cache.exists():
            return schema.model_validate_json(cache.read_text(encoding="utf-8"))

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        last_err: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.time()
            try:
                self.calls += 1
                resp = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
                um = resp.usage_metadata
                tin = getattr(um, "prompt_token_count", 0) or 0
                tout = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
                self.tokens_in += tin
                self.tokens_out += tout
                self.log.append({"schema": schema.__name__, "seconds": round(time.time() - t0, 1), "in": tin, "out": tout})
                text = resp.text or ""
                result = schema.model_validate_json(text)
                if self.use_cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cache.write_text(result.model_dump_json(), encoding="utf-8")
                return result
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                last_err = e
                print(f"  [llm] невалидный JSON ({schema.__name__}), попытка {attempt}: {str(e)[:200]}")
            except errors.APIError as e:
                last_err = e
                code = getattr(e, "code", None)
                if code not in (429, 500, 502, 503, 504):
                    raise
                m = re.search(r"retry(?:Delay)?['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(e), re.I)
                delay = float(m.group(1)) + 1 if m else min(60, 2 ** attempt * 2)
                print(f"  [llm] HTTP {code}, жду {delay:.0f} с (попытка {attempt})")
                time.sleep(delay)
        raise RuntimeError(f"LLM не ответил валидным JSON за {self.max_attempts} попыток: {last_err}")
