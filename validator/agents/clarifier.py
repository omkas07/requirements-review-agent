"""Агент уточнений (LLM): вопросы к автору ТЗ с вариантами и последствиями.

Код после LLM: сквозная нумерация В-1, В-2…, проверка ID требований,
проставление question_id в замечания по links.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from validator.agents.prompting import render, wrap_document
from validator.domain.models import ClarifierOutput, Finding, ModeratorOutput, Question

if TYPE_CHECKING:
    from validator.ports.llm import LLMClient

_ISSUE_REF = re.compile(r"R-?\s*0*(\d+)\s*[/#.:\- ]\s*(\d+)", re.I)
_REQ = re.compile(r"R-?\s*0*(\d+)", re.I)


def review_block(moderated: ModeratorOutput) -> str:
    lines = []
    for r in moderated.requirements:
        if not r.issues:
            continue
        lines.append(f"{r.req_id} ({r.doc_ref}, статус {r.status}) — {r.title}")
        for n, i in enumerate(r.issues, start=1):
            lines.append(f"  {r.req_id}/{n}. [{i.criterion}] {i.text} | цитата: «{i.quote}»")
    for c in moderated.set_checks:
        if not c.passed:
            lines.append(f"Набор — {c.criterion}: {c.details} (refs: {', '.join(c.refs) or '—'})")
    return "\n".join(lines) or "(замечаний нет)"


def business_block(findings: list[Finding]) -> str:
    rows = [
        f"- {f.req_id} [{f.criterion}] {f.text}" + (f" (связано: {', '.join(f.related_req_ids)})" if f.related_req_ids else "")
        for f in findings
        if f.needs_business_decision
    ]
    return "\n".join(rows) or "(нет)"


def _req(raw: str, known: set[str]) -> str | None:
    m = _REQ.search(raw or "")
    if not m:
        return None
    rid = f"R-{int(m.group(1)):02d}"
    return rid if rid in known else None


def apply(moderated: ModeratorOutput, out: ClarifierOutput) -> tuple[ModeratorOutput, list[Question], list[str]]:
    warnings: list[str] = []
    result = moderated.model_copy(deep=True)
    reqs = {r.req_id: r for r in result.requirements}
    known = set(reqs)

    renum: dict[str, str] = {}
    questions: list[Question] = []
    for n, q in enumerate(out.questions, start=1):
        new_id = f"В-{n}"
        renum[q.q_id.strip()] = new_id
        related = list(dict.fromkeys(x for x in (_req(r, known) for r in q.related_reqs) if x))
        questions.append(q.model_copy(update={"q_id": new_id, "related_reqs": related}))
    qmap = {q.q_id: q for q in questions}

    for link in out.links:
        qid = renum.get(link.q_id.strip())
        if qid is None:
            warnings.append(f"Уточнения: связь с неизвестным вопросом «{link.q_id}»")
            continue
        q = qmap[qid]
        linked_reqs: set[str] = set()
        for ref in link.issue_refs:
            m = _ISSUE_REF.search(ref)
            if not m:
                warnings.append(f"Уточнения: не разобрана ссылка «{ref}» ({qid})")
                continue
            rid, idx = f"R-{int(m.group(1)):02d}", int(m.group(2)) - 1
            req = reqs.get(rid)
            if req is None or not (0 <= idx < len(req.issues)):
                warnings.append(f"Уточнения: нет замечания {ref} ({qid})")
                continue
            if req.issues[idx].question_id is None:
                req.issues[idx].question_id = qid
            linked_reqs.add(rid)
        # требования из req_ids без конкретного замечания — первое свободное замечание
        for raw in link.req_ids:
            rid = _req(raw, known)
            if rid is None or rid in linked_reqs:
                continue
            free = next((i for i in reqs[rid].issues if i.question_id is None), None)
            if free is not None:
                free.question_id = qid
                linked_reqs.add(rid)
        for rid in sorted(linked_reqs):
            if rid not in q.related_reqs:
                q.related_reqs.append(rid)

    for q in questions:
        if not q.related_reqs:
            warnings.append(f"Уточнения: вопрос {q.q_id} не привязан ни к одному требованию")
        q.related_reqs.sort()
        linked = any(i.question_id == q.q_id for r in result.requirements for i in r.issues)
        if not linked:
            warnings.append(f"Уточнения: вопрос {q.q_id} не связан ни с одним замечанием")
    return result, questions, warnings


def clarify(
    llm: "LLMClient", document: str, moderated: ModeratorOutput, findings: list[Finding]
) -> tuple[ModeratorOutput, list[Question], list[str]]:
    prompt = render(
        "clarifier",
        review=review_block(moderated),
        business=business_block(findings),
        document=wrap_document(document),
    )
    out = llm.ask_json(prompt, ClarifierOutput)
    return apply(moderated, out)
