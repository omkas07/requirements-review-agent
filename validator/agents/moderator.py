"""Модератор (LLM): объединяет дубли, ставит статусы, заполняет impact,
проверяет набор целиком и выделяет сильные стороны.

LLM возвращает только оценки (ModeratorLLMOutput); req_id/doc_ref/title/quote
код берёт из нарезки парсера, поэтому ни одно требование не теряется.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from validator.agents.prompting import render, requirements_block, to_json, wrap_document
from validator.domain.criteria import SET_CRITERIA
from validator.domain.models import (
    Finding,
    Issue,
    ModeratedRequirement,
    ModeratorLLMOutput,
    ModeratorOutput,
    ParsedRequirement,
    Requirement,
    SetCheck,
)

if TYPE_CHECKING:
    from validator.ports.llm import LLMClient

SET_ORDER = [c.name for c in SET_CRITERIA]
IMPORTANT = ("blocking", "major")


def findings_block(findings: list[Finding]) -> str:
    rows = []
    for i, f in enumerate(findings, start=1):
        rows.append(
            {
                "id": f"F-{i}",
                "expert": f.expert,
                "req_id": f.req_id,
                "criterion": f.criterion,
                "severity": f.severity,
                "text": f.text,
                "quote": f.quote,
                "related": f.related_req_ids,
                "suggestion": f.suggestion,
                "business": f.needs_business_decision,
            }
        )
    return to_json(rows)


def _issue_from_finding(f: Finding) -> Issue:
    return Issue(criterion=f.criterion, text=f.text, quote=f.quote)


def fallback_requirement(req: ParsedRequirement, findings: list[Finding]) -> ModeratedRequirement:
    """Без LLM: замечания как есть, статус по максимальной серьёзности."""
    own = [f for f in findings if f.req_id == req.req_id]
    if not own:
        return ModeratedRequirement(req_id=req.req_id, status="ok")
    status = "blocking" if any(f.severity == "blocking" for f in own) else "needs_clarification"
    suggestion = next((f.suggestion for f in own if f.suggestion), None)
    return ModeratedRequirement(
        req_id=req.req_id, status=status, issues=[_issue_from_finding(f) for f in own], suggestion=suggestion
    )


def assemble(
    reqs: list[ParsedRequirement], llm_out: ModeratorLLMOutput | None, findings: list[Finding]
) -> tuple[ModeratorOutput, list[str]]:
    warnings: list[str] = []
    by_id: dict[str, ModeratedRequirement] = {}
    if llm_out is not None:
        for m in llm_out.requirements:
            if m.req_id in by_id:
                # модератор вернул требование дважды — сливаем замечания
                by_id[m.req_id].issues.extend(m.issues)
            else:
                by_id[m.req_id] = m.model_copy(deep=True)
        unknown = set(by_id) - {r.req_id for r in reqs}
        if unknown:
            warnings.append(f"Модератор: неизвестные req_id {sorted(unknown)} — пропущены")

    final: list[Requirement] = []
    for r in reqs:
        m = by_id.get(r.req_id)
        if m is None:
            if llm_out is not None:
                warnings.append(f"Модератор пропустил {r.req_id} — замечания взяты из находок экспертов")
            m = fallback_requirement(r, findings)
        issues = [i.model_copy(update={"question_id": None}) for i in m.issues]
        status = m.status
        # Страховка: модератор не может «закрыть» требование, по которому эксперты нашли
        # важные проблемы, — такие находки возвращаются как есть.
        important = [f for f in findings if f.req_id == r.req_id and f.severity in IMPORTANT]
        if llm_out is not None and not issues and important:
            issues = [_issue_from_finding(f) for f in important]
            status = "blocking" if any(f.severity == "blocking" for f in important) else "needs_clarification"
            m.suggestion = m.suggestion or next((f.suggestion for f in important if f.suggestion), None)
            warnings.append(f"Модератор пометил {r.req_id} без замечаний, хотя эксперты нашли важные проблемы ({len(important)}) — возвращены")
        if issues and status == "ok":
            status = "needs_clarification"
            warnings.append(f"{r.req_id}: статус ok при наличии замечаний → needs_clarification")
        if not issues and status != "ok":
            warnings.append(f"{r.req_id}: статус {status} без замечаний → ok")
            status = "ok"
        if status == "ok":
            m.suggestion = None
        final.append(
            Requirement(
                req_id=r.req_id,
                doc_ref=r.doc_ref,
                title=r.title,
                quote=r.quote,
                status=status,
                issues=issues,
                suggestion=m.suggestion,
            )
        )

    # Проверка набора: ровно 8 критериев в порядке стандарта.
    checks: dict[str, SetCheck] = {}
    if llm_out is not None:
        for c in llm_out.set_checks:
            name = next((n for n in SET_ORDER if n.lower() in c.criterion.lower()), c.criterion)
            known = {x.req_id for x in reqs}
            checks.setdefault(name, c.model_copy(update={"criterion": name, "refs": [x for x in c.refs if x in known]}))
    set_checks = []
    for name in SET_ORDER:
        if name in checks:
            set_checks.append(checks[name])
        else:
            warnings.append(f"Модератор не оценил критерий набора «{name}»")
            related = [f for f in findings if f.req_id == "SET" and name.lower() in f.criterion.lower()]
            set_checks.append(
                SetCheck(
                    criterion=name,
                    passed=not related,
                    details=" ".join(f.text for f in related) or "Модератор не дал оценки; у экспертов замечаний по этому критерию нет.",
                    refs=[],
                )
            )
    strengths = list(llm_out.strengths) if llm_out is not None else []
    return ModeratorOutput(requirements=final, set_checks=set_checks, strengths=strengths), warnings


def moderate(
    llm: "LLMClient", document: str, reqs: list[ParsedRequirement], findings: list[Finding]
) -> tuple[ModeratorOutput, list[str]]:
    prompt = render(
        "moderator",
        requirements=requirements_block(reqs),
        findings=findings_block(findings),
        document=wrap_document(document),
    )
    llm_out = llm.ask_json(prompt, ModeratorLLMOutput)
    return assemble(reqs, llm_out, findings)
