"""Верификатор (без LLM) — guardrail против выдуманных цитат.

Каждое замечание должно цитировать документ: цитата после нормализации (регистр,
пробелы, кавычки, тире, ё/е, разметка Markdown) — подстрока документа.
Замечания с несуществующими цитатами выбрасываются и попадают в warnings.
"""

from __future__ import annotations

from validator.agents.quotes import normalize, quote_in_document
from validator.agents.state import ReviewState
from validator.domain.models import ModeratorOutput


def verify(document: str, moderated: ModeratorOutput) -> tuple[ModeratorOutput, list[str]]:
    ndoc = normalize(document)
    result = moderated.model_copy(deep=True)
    dropped: list[str] = []
    for req in result.requirements:
        kept = []
        for issue in req.issues:
            if quote_in_document(issue.quote, ndoc):
                kept.append(issue)
            else:
                dropped.append(f"{req.req_id} [{issue.criterion}] «{issue.quote[:80]}»")
        if len(kept) != len(req.issues):
            req.issues = kept
            if not kept:  # все замечания оказались без опоры на текст
                req.status = "ok"
                req.suggestion = None
    warnings = []
    if dropped:
        warnings.append(f"Верификатор: выброшено {len(dropped)} замечаний с цитатами не из документа")
        warnings += [f"  — {d}" for d in dropped]
    return result, warnings


def node(state: ReviewState) -> dict:
    moderated, warnings = verify(state["document"], state["moderated"])
    total = sum(len(r.issues) for r in state["moderated"].requirements)
    kept = sum(len(r.issues) for r in moderated.requirements)
    return {
        "moderated": moderated,
        "warnings": warnings,
        "metrics": [{"node": "verifier", "llm_calls": 0, "seconds": 0.0, "issues_in": total, "issues_dropped": total - kept}],
    }
