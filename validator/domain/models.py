"""Контракт данных между частями проекта.

Финальные модели (Issue, Requirement, Question, SetCheck) — то, что уходит в отчёт.
Промежуточные модели — то, что возвращают LLM-агенты (схемы структурированного вывода).

Меняется только через Омара.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "needs_clarification", "blocking"]
Severity = Literal["blocking", "major", "minor"]


# --------------------------------------------------------------------------- #
# Финальные модели (контракт с отчётом)
# --------------------------------------------------------------------------- #


class Issue(BaseModel):
    criterion: str = Field(description="Критерий качества, например «Непротиворечивость»")
    text: str = Field(description="Что не так + почему важно + как исправить, до 3 предложений")
    quote: str = Field(description="Дословная цитата из документа")
    impact: str | None = Field(
        default=None, description="«Если не исправить» — только для blocking и важных замечаний"
    )
    question_id: str | None = Field(default=None, description="Ссылка на вопрос, например «В-1»")


class Requirement(BaseModel):
    req_id: str
    doc_ref: str
    title: str
    quote: str
    status: Status
    issues: list[Issue] = []
    suggestion: str | None = None


class Question(BaseModel):
    q_id: str = Field(description="«В-1», «В-2»…")
    text: str = Field(description="Сам вопрос, одно предложение")
    context: str = Field(description="Конкретная ситуация из документа, на которой видна проблема")
    options: list[str] = Field(description="Варианты ответа с последствиями: «а) … → исправить R-13»")
    related_reqs: list[str] = Field(description="ID требований, например [\"R-04\", \"R-13\"]")
    blocks: str | None = Field(
        default=None, description="Что блокирует, пока нет ответа; null — если вопрос не блокирующий"
    )


class SetCheck(BaseModel):
    criterion: str
    passed: bool
    details: str
    refs: list[str]


# --------------------------------------------------------------------------- #
# Промежуточные модели (выход агентов)
# --------------------------------------------------------------------------- #


class ParsedRequirement(BaseModel):
    req_id: str = Field(description="R-01, R-02… в порядке документа")
    doc_ref: str = Field(description="Где в документе: «Ф-2», «Часть B, REST type»")
    title: str = Field(description="Краткая формулировка, 3–7 слов")
    quote: str = Field(description="Дословная цитата из документа")


class ParserOutput(BaseModel):
    requirements: list[ParsedRequirement]


class Finding(BaseModel):
    req_id: str = Field(description="ID требования или «SET», если про документ целиком")
    criterion: str
    text: str
    quote: str
    related_req_ids: list[str] = []
    suggestion: str | None = None
    needs_business_decision: bool = False
    # ДОБАВЛЕНО к контракту: оценка эксперта, помогает модератору выставить статус.
    severity: Severity = "major"
    # ДОБАВЛЕНО: заполняется кодом (не LLM) — какой эксперт нашёл.
    expert: str | None = None


class ExpertOutput(BaseModel):
    findings: list[Finding]


class ModeratorOutput(BaseModel):
    requirements: list[Requirement]
    set_checks: list[SetCheck]
    strengths: list[str] = Field(description="2–4 конкретные сильные стороны с цитатами")


# ДОБАВЛЕНО: то, что реально возвращает LLM-модератор. Цитаты и названия
# требований модератор не переписывает — код берёт их из парсера и собирает
# ModeratorOutput. Так ни одно требование не теряется и не искажается.
class ModeratedRequirement(BaseModel):
    req_id: str
    status: Status
    issues: list[Issue] = []
    suggestion: str | None = None


class ModeratorLLMOutput(BaseModel):
    requirements: list[ModeratedRequirement]
    set_checks: list[SetCheck]
    strengths: list[str]


class QuestionLink(BaseModel):
    q_id: str
    req_ids: list[str]
    # ДОБАВЛЕНО: конкретные замечания вида «R-05/1» (требование/номер замечания с 1),
    # чтобы question_id проставлялся не во все замечания требования, а в нужное.
    issue_refs: list[str] = []


class ClarifierOutput(BaseModel):
    questions: list[Question]
    links: list[QuestionLink]
