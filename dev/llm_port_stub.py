"""ВРЕМЕННО: копия порта LLMClient, пока нет validator/ports/llm.py (тиммейт 1).

Агенты импортируют порт только под TYPE_CHECKING, поэтому после мержа
части тиммейта 1 ничего переключать не нужно — этот файл просто удалить.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    model: str  # имя модели — для паспорта отчёта

    def ask_json(self, prompt: str, schema: type[T]) -> T:
        """Структурированный вывод: JSON по схеме pydantic, валидированный."""
        ...
