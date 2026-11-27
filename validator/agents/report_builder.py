"""Сборщик отчёта (без LLM): сортировка, готовность, сводка, паспорт, рендер Jinja2.

В файл не пишет — возвращает текст; запись делает main.py через ReportWriter.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from validator.agents.state import ReviewState
from validator.domain.models import ModeratorOutput, Question
from validator.domain.scoring import (
    MAX_SCORE,
    STATUS_ICON,
    STATUS_LABEL,
    THRESHOLD_GREEN,
    THRESHOLD_RED,
    WEIGHT_BLOCKING,
    WEIGHT_NEEDS_CLARIFICATION,
    plural,
    readiness,
    sort_for_review,
    summary,
    verdict,
)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_NUM = re.compile(r"(\d+)")


def req_anchor(req_id: str) -> str:
    """R-05 → r-05 (только ASCII: кириллица и эмодзи ломают якоря)."""
    return req_id.lower()


def q_anchor(q_id: str) -> str:
    """В-1 (В кириллицей) → q-1."""
    m = _NUM.search(q_id)
    return f"q-{m.group(1)}" if m else "q-" + re.sub(r"[^a-z0-9]+", "-", q_id.lower()).strip("-")


def cell(text: object) -> str:
    """Текст для ячейки таблицы Markdown: без переносов строк и с экранированным |."""
    return re.sub(r"\s+", " ", str(text or "")).replace("|", "\\|").strip()


def one_line(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.filters.update(req_anchor=req_anchor, q_anchor=q_anchor, cell=cell, one_line=one_line)
    env.globals["plural"] = plural
    return env


def _headline(sm: dict, v) -> str:
    parts = []
    if sm["blocking"]:
        b = sm["blocking"]
        parts.append(f"{b} из {sm['requirements']} {plural(sm['requirements'], 'требования', 'требований', 'требований')} "
                     f"{plural(b, 'блокирует', 'блокируют', 'блокируют')} разработку")
    if sm["needs_clarification"]:
        n = sm["needs_clarification"]
        parts.append(f"{n} {plural(n, 'требует', 'требуют', 'требуют')} уточнения")
    if not parts:
        return "Замечаний к требованиям нет."
    text = ", ".join(parts)
    return text[0].upper() + text[1:] + "."


def _fix_plan(moderated: ModeratorOutput, questions: list[Question], answered: dict[str, str]) -> list[str]:
    plan: list[str] = []
    open_q = [q for q in questions if q.q_id not in answered]
    blocking_q = [q for q in open_q if q.blocks]
    if blocking_q:
        refs = ", ".join(f"[{q.q_id}](#{q_anchor(q.q_id)})" for q in blocking_q)
        plan.append(f"Ответить на блокирующие вопросы {refs} — без них нельзя зафиксировать правила расчёта и контракт.")
    blocking = [r for r in moderated.requirements if r.status == "blocking"]
    if blocking:
        refs = ", ".join(f"[{r.req_id}](#{req_anchor(r.req_id)}) ({r.doc_ref})" for r in blocking)
        plan.append(f"Исправить требования 🔴: {refs}.")
    important = [r for r in moderated.requirements if r.status == "needs_clarification" and any(i.impact for i in r.issues)]
    if important:
        refs = ", ".join(f"[{r.req_id}](#{req_anchor(r.req_id)})" for r in important)
        plan.append(f"Уточнить требования 🟡 с важными последствиями: {refs}.")
    failed = [c for c in moderated.set_checks if not c.passed]
    if failed:
        plan.append("Закрыть замечания к набору: " + ", ".join(c.criterion.lower() for c in failed) + ".")
    rest_q = [q for q in open_q if not q.blocks]
    if rest_q:
        refs = ", ".join(f"[{q.q_id}](#{q_anchor(q.q_id)})" for q in rest_q)
        plan.append(f"Ответить на остальные вопросы: {refs}.")
    rest = [r for r in moderated.requirements if r.status == "needs_clarification" and r not in important]
    if rest:
        refs = ", ".join(f"[{r.req_id}](#{req_anchor(r.req_id)})" for r in rest)
        plan.append(f"Поправить формулировки остальных требований 🟡: {refs}.")
    if not plan:
        plan.append("Исправлять нечего — документ можно передавать в разработку.")
    return plan


def build_report(
    moderated: ModeratorOutput,
    questions: list[Question],
    passport: dict | None = None,
    answers: dict[str, str] | None = None,
    warnings: list[str] | None = None,
    metrics: list[dict] | None = None,
) -> str:
    passport = dict(passport or {})
    answers = answers or {}
    reqs = moderated.requirements
    v = verdict(reqs, questions, answered=set(answers))
    sm = summary(reqs, questions, moderated.set_checks)
    score = readiness(reqs)
    by_id = {r.req_id: r for r in reqs}

    metrics = metrics or []
    if "llm_calls" not in passport:
        passport["llm_calls"] = sum(m.get("llm_calls", 0) for m in metrics)
    if "seconds" not in passport and passport.get("started_at"):
        passport["seconds"] = round(time.time() - float(passport["started_at"]), 1)
    dropped = next((m.get("issues_dropped") for m in metrics if m.get("node") == "verifier"), None)

    return _env().get_template("report.md.j2").render(
        passport=passport,
        score=score,
        max_score=MAX_SCORE,
        verdict=v,
        headline=_headline(sm, v),
        requirements=reqs,
        review=sort_for_review(reqs),
        by_id=by_id,
        questions=questions,
        open_questions=[q for q in questions if q.q_id not in answers],
        answers=answers,
        set_checks=moderated.set_checks,
        strengths=moderated.strengths,
        summary=sm,
        plan=_fix_plan(moderated, questions, answers),
        icon=STATUS_ICON,
        label=STATUS_LABEL,
        weights={"blocking": WEIGHT_BLOCKING, "needs_clarification": WEIGHT_NEEDS_CLARIFICATION},
        thresholds={"red": THRESHOLD_RED, "green": THRESHOLD_GREEN},
        dropped=dropped,
        warnings=warnings or [],
    )


def node(state: ReviewState) -> dict:
    text = build_report(
        state["moderated"],
        state.get("questions", []),
        passport=state.get("passport", {}),
        answers=state.get("answers", {}),
        warnings=state.get("warnings", []),
        metrics=state.get("metrics", []),
    )
    return {"report_text": text, "metrics": [{"node": "report_builder", "llm_calls": 0, "seconds": 0.0}]}
