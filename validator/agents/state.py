"""State графа LangGraph.

Поля со списками, которые пишут параллельные узлы (эксперты), объявлены через
Annotated[list, operator.add]: LangGraph складывает их, а не затирает.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from validator.domain.models import Finding, ModeratorOutput, ParsedRequirement, Question


class ReviewState(TypedDict, total=False):
    # Вход
    document: str  # полный текст ТЗ (Markdown или текст из PDF)
    source: str  # путь к файлу, для паспорта и логов
    passport: dict  # заполняет main.py: модель, дата, коммит, режим — для сборщика

    # Код (без LLM)
    vague_hits: list[dict]  # find_vague_words(document)

    # Парсер
    requirements: list[ParsedRequirement]

    # Эксперты (fan-out / fan-in)
    findings: Annotated[list[Finding], operator.add]

    # Модератор → (верификатор) → агент уточнений
    moderated: ModeratorOutput
    questions: list[Question]

    # Интерактивный режим: ответы автора ТЗ на вопросы {"В-1": "б) …"}
    answers: dict[str, str]

    # Сборщик (без LLM): готовый текст отчёта; в файл пишет main.py через ReportWriter
    report_text: str

    # Служебное: что делал каждый узел
    metrics: Annotated[list[dict], operator.add]  # {"node", "llm_calls", "seconds", ...}
    warnings: Annotated[list[str], operator.add]
