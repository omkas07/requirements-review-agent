"""Адаптер Google Gemini (google-genai): structured output по JSON-схеме pydantic."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from validator.adapters.llm_base import JSONLLMClient, backoff

_RETRY_DELAY = re.compile(r"retry(?:Delay)?['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.I)
_RETRYABLE = {429, 500, 502, 503, 504}


class GeminiClient(JSONLLMClient):
    provider = "gemini"

    def __init__(self, api_key: str, model: str, temperature: float = 0.0, max_attempts: int = 6, cache_dir: Path | None = None):
        super().__init__(model, temperature, max_attempts, cache_dir)
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def _call(self, prompt: str, schema: type[BaseModel]) -> tuple[str, int, int]:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        resp = self._client.models.generate_content(model=self.model, contents=prompt, config=config)
        um = resp.usage_metadata
        tin = getattr(um, "prompt_token_count", 0) or 0
        tout = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
        return resp.text or "", tin, tout

    def _retry_delay(self, error: Exception, attempt: int) -> float | None:
        from google.genai import errors

        if not isinstance(error, errors.APIError) or getattr(error, "code", None) not in _RETRYABLE:
            return None
        m = _RETRY_DELAY.search(str(error))  # бесплатный тариф присылает retryDelay в 429
        return float(m.group(1)) + 1 if m else backoff(attempt)
