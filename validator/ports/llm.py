"""Порт LLM: единственный способ, которым агенты обращаются к модели."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    model: str  # имя модели — для паспорта отчёта

    def ask_json(self, prompt: str, schema: type[T]) -> T:
        """Структурированный вывод: JSON по схеме pydantic, уже провалидированный.

        Реализация отвечает за temperature=0, повтор при невалидном JSON
        и паузы при 429/5xx.
        """
        ...
