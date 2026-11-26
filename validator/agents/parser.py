"""Парсер (LLM): режет документ на требования R-01, R-02… в порядке документа.

После LLM код гарантирует порядок документа (по позиции цитаты) и сплошную
нумерацию — от этого зависят ссылки в отчёте.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from validator.agents.prompting import render, wrap_document
from validator.agents.quotes import normalize, quote_fragments
from validator.domain.models import ParsedRequirement, ParserOutput

if TYPE_CHECKING:
    from validator.ports.llm import LLMClient

_MD = re.compile(r"\*\*|`")


def clean_quote(quote: str) -> str:
    q = _MD.sub("", quote).strip()
    return q.strip("«»\"").strip()


def _locate(quote: str, ndoc: str, start: int) -> int | None:
    frags = quote_fragments(quote)
    if not frags:
        return None
    idx = ndoc.find(frags[0], start)
    if idx < 0:
        idx = ndoc.find(frags[0])
    return idx if idx >= 0 else None


def postprocess(reqs: list[ParsedRequirement], document: str) -> tuple[list[ParsedRequirement], list[str]]:
    warnings: list[str] = []
    ndoc = normalize(document)
    placed: list[tuple[float, int, ParsedRequirement]] = []
    last = 0.0
    seen: set[str] = set()
    for i, r in enumerate(reqs):
        r = r.model_copy(update={"quote": clean_quote(r.quote)})
        key = normalize(r.quote)
        if key in seen:
            warnings.append(f"Парсер: дубль требования «{r.quote[:60]}» — пропущен")
            continue
        seen.add(key)
        pos = _locate(r.quote, ndoc, int(last))
        if pos is None:
            warnings.append(f"Парсер: цитата {r.req_id} не найдена в документе: «{r.quote[:80]}»")
            pos_f = last + 0.001  # оставить на месте относительно соседей
        else:
            pos_f = float(pos)
        last = max(last, pos_f)
        placed.append((pos_f, i, r))
    placed.sort(key=lambda t: (t[0], t[1]))
    out = [
        r.model_copy(update={"req_id": f"R-{n:02d}"}) for n, (_, _, r) in enumerate(placed, start=1)
    ]
    return out, warnings


def parse_requirements(llm: "LLMClient", document: str) -> tuple[list[ParsedRequirement], list[str]]:
    prompt = render("parser", document=wrap_document(document))
    result = llm.ask_json(prompt, ParserOutput)
    return postprocess(result.requirements, document)
