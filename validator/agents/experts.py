"""Три эксперта (LLM): разработчик, тестировщик, специалист ИБ.

Каждый — ОДИН вызов LLM на весь документ (лимиты бесплатного Gemini).
Каждый получает весь документ (для поиска противоречий) и список требований.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from validator.agents.prompting import load_prompt, render, requirements_block, wrap_document
from validator.domain.criteria import (
    FINTECH_CHECKLIST,
    REQUIREMENT_CRITERIA,
    SET_CRITERIA,
    format_criteria,
    format_vague_hits,
)
from validator.domain.models import ExpertOutput, Finding, ParsedRequirement

if TYPE_CHECKING:
    from validator.ports.llm import LLMClient

# ключ → (файл промпта, имя для отчёта/логов)
EXPERTS: dict[str, tuple[str, str]] = {
    "developer": ("expert_developer", "Разработчик"),
    "tester": ("expert_tester", "Тестировщик"),
    "security": ("expert_security", "Безопасник"),
}

_REQ_ID = re.compile(r"R-?\s*0*(\d+)", re.I)


def normalize_req_id(raw: str, known: set[str]) -> str | None:
    raw = (raw or "").strip()
    if raw.upper() == "SET":
        return "SET"
    m = _REQ_ID.fullmatch(raw) or _REQ_ID.search(raw)
    if not m:
        return None
    rid = f"R-{int(m.group(1)):02d}"
    return rid if rid in known else None


def build_prompt(role: str, document: str, reqs: list[ParsedRequirement], vague_hits: list[dict]) -> str:
    prompt_file, _ = EXPERTS[role]
    return render(
        "expert_base",
        role=load_prompt(prompt_file),
        criteria=format_criteria(REQUIREMENT_CRITERIA),
        set_criteria=format_criteria(SET_CRITERIA),
        fintech=format_criteria(FINTECH_CHECKLIST),
        vague=format_vague_hits(vague_hits),
        requirements=requirements_block(reqs),
        document=wrap_document(document),
    )


def postprocess(role: str, findings: list[Finding], reqs: list[ParsedRequirement]) -> tuple[list[Finding], list[str]]:
    known = {r.req_id for r in reqs}
    name = EXPERTS[role][1]
    out: list[Finding] = []
    warnings: list[str] = []
    for f in findings:
        rid = normalize_req_id(f.req_id, known)
        if rid is None:
            warnings.append(f"{name}: неизвестный req_id «{f.req_id}» → отнесено к SET")
            rid = "SET"
        related = [x for x in (normalize_req_id(r, known) for r in f.related_req_ids) if x and x not in ("SET", rid)]
        out.append(
            f.model_copy(
                update={
                    "req_id": rid,
                    "related_req_ids": list(dict.fromkeys(related)),
                    "expert": name,
                    "quote": f.quote.replace("**", "").replace("`", "").strip().strip("«»\"").strip(),
                }
            )
        )
    return out, warnings


def run_expert(
    llm: "LLMClient", role: str, document: str, reqs: list[ParsedRequirement], vague_hits: list[dict]
) -> tuple[list[Finding], list[str]]:
    result = llm.ask_json(build_prompt(role, document, reqs, vague_hits), ExpertOutput)
    return postprocess(role, result.findings, reqs)
