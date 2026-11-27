"""Адаптер OpenAI (Chat Completions): response_format json_schema по схеме pydantic.

strict=False: строгий режим OpenAI не принимает поля со значениями по умолчанию,
поэтому схему не ужесточаем, а валидируем ответ pydantic'ом в базовом классе.

reasoning_effort="none" (по умолчанию): модели GPT-5.6/6 принимают temperature=0 только без
рассуждений — так ревью воспроизводимо. Модели без этого параметра получают запрос без него.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from validator.adapters.llm_base import JSONLLMClient, backoff


class OpenAIClient(JSONLLMClient):
    provider = "openai"

    def __init__(self, api_key: str, model: str, temperature: float = 0.0, max_attempts: int = 6,
                 cache_dir: Path | None = None, reasoning_effort: str | None = "none"):
        super().__init__(model, temperature, max_attempts, cache_dir)
        self.reasoning_effort = reasoning_effort
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, max_retries=0)  # повторы — наши
        self._send_temperature = True

    def _call(self, prompt: str, schema: type[BaseModel]) -> tuple[str, int, int]:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": False},
            },
        )
        if self._send_temperature:
            kwargs["temperature"] = self.temperature
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        resp = self._client.chat.completions.create(**kwargs)
        usage = resp.usage
        return (
            resp.choices[0].message.content or "",
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def _retry_delay(self, error: Exception, attempt: int) -> float | None:
        import openai

        # Часть моделей не принимает temperature — повторяем без неё. Флаг общий для потоков:
        # параллельные эксперты могли отправить temperature до того, как другой поток его выключил.
        text = str(error).lower()
        if isinstance(error, openai.BadRequestError) and "reasoning_effort" in text and self.reasoning_effort:
            self.reasoning_effort = None  # модель без рассуждений — параметр не нужен
            return 0.0
        if isinstance(error, openai.BadRequestError) and "temperature" in text:
            self._send_temperature = False
            return 0.0
        if isinstance(error, (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)):
            return backoff(attempt)
        return None
