"""Сборка workflow на LangGraph.

    prepare ─► parser ─► ┌ developer ┐
                         ├ tester    ├─► moderator ─► [verifier] ─► clarifier ─► [report_builder]
                         └ security  ┘

Сознательно workflow, а не автономный агент: ревью должно быть воспроизводимым.
LLM передаётся снаружи (build_graph(llm)) — агенты не знают про адаптеры.

verifier и report_builder — узлы тиммейтов; подключаются, если модули есть
и экспортируют функцию `node(state: ReviewState) -> dict`.
"""

from __future__ import annotations

import importlib
import time
from typing import TYPE_CHECKING, Any, Callable

from langgraph.graph import END, START, StateGraph

from validator.agents.clarifier import clarify
from validator.agents.experts import EXPERTS, run_expert
from validator.agents.moderator import assemble, moderate
from validator.agents.parser import parse_requirements
from validator.agents.state import ReviewState
from validator.domain.criteria import find_vague_words

if TYPE_CHECKING:
    from validator.ports.llm import LLMClient


def _metric(node: str, t0: float, llm_calls: int, **extra: Any) -> list[dict]:
    return [{"node": node, "llm_calls": llm_calls, "seconds": round(time.time() - t0, 1), **extra}]


def _optional_node(module: str) -> Callable[[ReviewState], dict] | None:
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name and module.startswith(e.name):
            return None
        raise
    return getattr(mod, "node", None)


def build_graph(llm: "LLMClient", *, include_optional: bool = True):
    """Компилирует граф. include_optional=False — без узлов тиммейтов (для отладки)."""

    def prepare(state: ReviewState) -> dict:
        t0 = time.time()
        hits = find_vague_words(state["document"])
        return {"vague_hits": hits, "metrics": _metric("prepare", t0, 0, vague_hits=len(hits))}

    def parser(state: ReviewState) -> dict:
        t0 = time.time()
        reqs, warns = parse_requirements(llm, state["document"])
        if not reqs:
            raise RuntimeError("Парсер не выделил ни одного требования")
        return {"requirements": reqs, "warnings": warns, "metrics": _metric("parser", t0, 1, requirements=len(reqs))}

    def make_expert(role: str):
        name = EXPERTS[role][1]

        def expert(state: ReviewState) -> dict:
            t0 = time.time()
            try:
                found, warns = run_expert(llm, role, state["document"], state["requirements"], state.get("vague_hits", []))
            except Exception as e:  # один эксперт не должен ронять всё ревью
                return {
                    "findings": [],
                    "warnings": [f"{name}: ошибка LLM, находок нет ({type(e).__name__}: {str(e)[:200]})"],
                    "metrics": _metric(role, t0, 1, findings=0, failed=True),
                }
            return {"findings": found, "warnings": warns, "metrics": _metric(role, t0, 1, findings=len(found))}

        expert.__name__ = role
        return expert

    def moderator(state: ReviewState) -> dict:
        t0 = time.time()
        reqs, findings = state["requirements"], state.get("findings", [])
        try:
            out, warns = moderate(llm, state["document"], reqs, findings)
        except Exception as e:
            out, warns = assemble(reqs, None, findings)
            warns = [f"Модератор: ошибка LLM, замечания экспертов без объединения ({type(e).__name__}: {str(e)[:200]})"] + warns
        issues = sum(len(r.issues) for r in out.requirements)
        return {"moderated": out, "warnings": warns, "metrics": _metric("moderator", t0, 1, issues=issues)}

    def clarifier(state: ReviewState) -> dict:
        t0 = time.time()
        try:
            moderated, questions, warns = clarify(llm, state["document"], state["moderated"], state.get("findings", []))
        except Exception as e:
            moderated, questions = state["moderated"], []
            warns = [f"Агент уточнений: ошибка LLM, вопросов нет ({type(e).__name__}: {str(e)[:200]})"]
        return {
            "moderated": moderated,
            "questions": questions,
            "warnings": warns,
            "metrics": _metric("clarifier", t0, 1, questions=len(questions)),
        }

    g = StateGraph(ReviewState)
    g.add_node("prepare", prepare)
    g.add_node("parser", parser)
    for role in EXPERTS:
        g.add_node(role, make_expert(role))
    g.add_node("moderator", moderator)
    g.add_node("clarifier", clarifier)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "parser")
    for role in EXPERTS:  # fan-out
        g.add_edge("parser", role)
    g.add_edge(list(EXPERTS), "moderator")  # fan-in: ждёт всех трёх

    verifier = _optional_node("validator.agents.verifier") if include_optional else None
    if verifier is not None:
        g.add_node("verifier", verifier)
        g.add_edge("moderator", "verifier")
        g.add_edge("verifier", "clarifier")
    else:
        g.add_edge("moderator", "clarifier")

    report = _optional_node("validator.agents.report_builder") if include_optional else None
    if report is not None:
        g.add_node("report_builder", report)
        g.add_edge("clarifier", "report_builder")
        g.add_edge("report_builder", END)
    else:
        g.add_edge("clarifier", END)
    return g.compile()


def run_review(llm: "LLMClient", document: str, source: str = "", **kwargs: Any) -> ReviewState:
    graph = build_graph(llm, **kwargs)
    return graph.invoke({"document": document, "source": source, "findings": [], "metrics": [], "warnings": []})


def agents_output(state: ReviewState) -> dict:
    """Выход агентов для сборщика отчёта: ModeratorOutput + questions (+ служебное _meta)."""
    moderated = state["moderated"]
    data = moderated.model_dump(mode="json")
    data["questions"] = [q.model_dump(mode="json") for q in state.get("questions", [])]
    data["_meta"] = {
        "source": state.get("source", ""),
        "llm_calls": sum(m.get("llm_calls", 0) for m in state.get("metrics", [])),
        "metrics": state.get("metrics", []),
        "warnings": state.get("warnings", []),
        "findings_raw": len(state.get("findings", [])),
        "vague_hits": state.get("vague_hits", []),
    }
    return data
