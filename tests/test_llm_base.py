"""Общая логика LLM-адаптеров без сети: повторы, паузы, кеш, ошибки."""

import pytest

import validator.adapters.llm_base as base
from validator.adapters.llm_base import JSONLLMClient, LLMError
from validator.domain.models import QuestionLink


class Scripted(JSONLLMClient):
    provider = "test"

    def __init__(self, replies, **kw):
        super().__init__("m", **kw)
        self.replies = list(replies)

    def _call(self, prompt, schema):
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r, 10, 5

    def _retry_delay(self, error, attempt):
        return 0.0 if isinstance(error, TimeoutError) else None


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)


def test_returns_validated_model_and_counts_tokens():
    c = Scripted(['```json\n{"q_id": "В-1", "req_ids": ["R-01"]}\n```'])
    out = c.ask_json("p", QuestionLink)
    assert out.req_ids == ["R-01"] and (c.calls, c.tokens_in, c.tokens_out) == (1, 10, 5)


def test_retries_invalid_json_then_succeeds():
    c = Scripted(["не json", '{"q_id": 1}', '{"q_id": "В-1", "req_ids": []}'])
    assert c.ask_json("p", QuestionLink).q_id == "В-1" and c.calls == 3


def test_retries_retryable_errors():
    c = Scripted([TimeoutError(), TimeoutError(), '{"q_id": "В-2", "req_ids": []}'])
    assert c.ask_json("p", QuestionLink).q_id == "В-2"


def test_non_retryable_error_raises_immediately():
    c = Scripted([PermissionError("bad key"), '{"q_id": "x", "req_ids": []}'])
    with pytest.raises(LLMError, match="bad key"):
        c.ask_json("p", QuestionLink)
    assert c.calls == 1


def test_gives_up_after_max_attempts():
    c = Scripted(["x"] * 3, max_attempts=3)
    with pytest.raises(LLMError, match="3 попыток"):
        c.ask_json("p", QuestionLink)


def test_cache_skips_second_call(tmp_path):
    c = Scripted(['{"q_id": "В-1", "req_ids": []}'], cache_dir=tmp_path)
    c.ask_json("p", QuestionLink)
    assert c.ask_json("p", QuestionLink).q_id == "В-1" and c.calls == 1


def test_gemini_retry_delay_uses_retry_hint():
    pytest.importorskip("google.genai")
    from google.genai import errors

    from validator.adapters.llm_gemini import GeminiClient

    c = GeminiClient.__new__(GeminiClient)
    e429 = errors.APIError(429, {"error": {"message": "quota", "details": [{"retryDelay": "17s"}]}})
    e400 = errors.APIError(400, {"error": {"message": "bad"}})
    assert c._retry_delay(e429, 1) == 18.0
    assert c._retry_delay(e400, 1) is None
    assert c._retry_delay(ValueError(), 1) is None


def test_openai_temperature_error_retried_in_every_thread():
    openai = pytest.importorskip("openai")
    import httpx

    from validator.adapters.llm_openai import OpenAIClient

    c = OpenAIClient.__new__(OpenAIClient)
    c._send_temperature = False  # другой поток уже выключил
    req = httpx.Request("POST", "https://x")
    err = openai.BadRequestError("Unsupported value: 'temperature'", response=httpx.Response(400, request=req), body=None)
    assert c._retry_delay(err, 1) == 0.0 and c._send_temperature is False
    other = openai.BadRequestError("bad schema", response=httpx.Response(400, request=req), body=None)
    assert c._retry_delay(other, 1) is None
