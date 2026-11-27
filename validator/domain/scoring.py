"""Готовность ТЗ, вердикт и сводка. Считает код, не LLM.

Число готовности в отчёт НЕ выводится (решение команды 27.11): оно уходило в 0 уже при
нескольких 🔴 и ничего не сообщало. Формула используется только внутри — для вердикта.

Формула (веса и пороги описаны в README):
    готовность = max(0, 100 − 15 × 🔴 − 5 × 🟡)
    🔴 «Разработку начинать нельзя» — есть 🔴 требование, блокирующий вопрос или готовность < 50
    🟡 «Можно начинать после исправления замечаний» — готовность < 80
    🟢 «Готово к разработке» — иначе
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from validator.domain.models import Question, Requirement, SetCheck

WEIGHT_BLOCKING = 15  # за каждое 🔴 требование
WEIGHT_NEEDS_CLARIFICATION = 5  # за каждое 🟡 требование
MAX_SCORE = 100
THRESHOLD_RED = 50  # ниже — 🔴
THRESHOLD_GREEN = 80  # от этого значения — 🟢

STATUS_ORDER = {"blocking": 0, "needs_clarification": 1, "ok": 2}
STATUS_ICON = {"blocking": "🔴", "needs_clarification": "🟡", "ok": "🟢"}
STATUS_LABEL = {"blocking": "Блокирует разработку", "needs_clarification": "Требует уточнения", "ok": "Замечаний нет"}

# Замечания по этим критериям мешают написать тест-кейс.
TEST_BLOCKING_CRITERIA = ("Проверяемость", "Непротиворечивость", "Однозначность")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование с числом: 1 требование, 2 требования, 5 требований."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def readiness(requirements: list[Requirement]) -> int:
    penalty = sum(
        WEIGHT_BLOCKING if r.status == "blocking" else WEIGHT_NEEDS_CLARIFICATION if r.status == "needs_clarification" else 0
        for r in requirements
    )
    return max(0, MAX_SCORE - penalty)


@dataclass(frozen=True)
class Verdict:
    level: str  # red / yellow / green
    icon: str
    text: str
    can_develop: bool
    can_test: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def blocking_questions(questions: list[Question], answered: set[str] | None = None) -> list[Question]:
    answered = answered or set()
    return [q for q in questions if q.blocks and q.q_id not in answered]


def verdict(
    requirements: list[Requirement], questions: list[Question], answered: set[str] | None = None
) -> Verdict:
    score = readiness(requirements)
    blocking = [r for r in requirements if r.status == "blocking"]
    open_blocking_q = blocking_questions(questions, answered)
    reasons = []
    if blocking:
        n = len(blocking)
        reasons.append(f"{n} {plural(n, 'требование блокирует', 'требования блокируют', 'требований блокируют')} разработку")
    if open_blocking_q:
        n = len(open_blocking_q)
        reasons.append(f"{n} {plural(n, 'блокирующий вопрос', 'блокирующих вопроса', 'блокирующих вопросов')} без ответа")
    if score < THRESHOLD_RED:
        reasons.append("замечания у большинства требований")

    test_issues = [
        r for r in requirements if r.status == "blocking" and any(i.criterion in TEST_BLOCKING_CRITERIA for i in r.issues)
    ]
    if reasons:
        return Verdict("red", "🔴", "Разработку начинать нельзя", False, not test_issues and not open_blocking_q, tuple(reasons))
    if score < THRESHOLD_GREEN:
        return Verdict("yellow", "🟡", "Можно начинать после исправления замечаний", True, not test_issues, ("есть требования, требующие уточнения",))
    return Verdict("green", "🟢", "Готово к разработке", True, True, ())


def sort_for_review(requirements: list[Requirement]) -> list[Requirement]:
    """🔴 → 🟡 → 🟢, внутри статуса — порядок документа (стабильная сортировка)."""
    return sorted(requirements, key=lambda r: STATUS_ORDER[r.status])


def summary(requirements: list[Requirement], questions: list[Question], set_checks: list[SetCheck]) -> dict:
    by_status = Counter(r.status for r in requirements)
    by_criterion = Counter(i.criterion for r in requirements for i in r.issues)
    for c in set_checks:
        if not c.passed:
            by_criterion[f"{c.criterion} (набор)"] += 1
    return {
        "requirements": len(requirements),
        "blocking": by_status.get("blocking", 0),
        "needs_clarification": by_status.get("needs_clarification", 0),
        "ok": by_status.get("ok", 0),
        "issues": sum(len(r.issues) for r in requirements),
        "questions": len(questions),
        "blocking_questions": sum(1 for q in questions if q.blocks),
        "set_failed": sum(1 for c in set_checks if not c.passed),
        "by_criterion": by_criterion.most_common(),
    }
