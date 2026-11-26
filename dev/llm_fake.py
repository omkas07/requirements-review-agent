"""Фейковый LLMClient: проверяет проводку графа без сети и без ключа.

Отвечает правдоподобными данными по схеме: цитаты берёт из документа в промпте.
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from validator.domain import models as m

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.requests = 0
        self.tokens_in = self.tokens_out = 0
        self.model = "fake"

    def ask_json(self, prompt: str, schema: type[T]) -> T:
        self.calls += 1
        self.requests += 1
        doc = prompt.split("<<<ДОКУМЕНТ\n", 1)[-1].split("\nДОКУМЕНТ>>>", 1)[0]
        reqs = re.findall(r"^- (R-\d+) \| ", prompt, re.M)
        if schema is m.ParserOutput:
            items = re.findall(r"^\* \*\*(.+?)\.\*\* (.+)$", doc, re.M)
            out = [m.ParsedRequirement(req_id=f"X{i}", doc_ref=ref, title=text[:30], quote=text) for i, (ref, text) in enumerate(reversed(items))]
            return schema(requirements=out)
        if schema is m.ExpertOutput:
            return schema(findings=[
                m.Finding(req_id=r, criterion="Однозначность", text=f"Фейковая находка {r}.", quote=doc.splitlines()[0].lstrip("# "),
                          needs_business_decision=(i == 0), severity="blocking" if i == 0 else "minor")
                for i, r in enumerate(reqs)
            ] + [m.Finding(req_id="SET", criterion="Полнота", text="Пустой раздел.", quote="заполняются тестировщиками")])
        if schema is m.ModeratorLLMOutput:
            out = [m.ModeratedRequirement(req_id=r, status="blocking" if i == 0 else "ok",
                                          issues=[m.Issue(criterion="Однозначность", text="x", quote="y", impact="z")] if i == 0 else [])
                   for i, r in enumerate(reqs[:-1])]  # одно требование «теряем» — проверка fallback
            return schema(requirements=out, set_checks=[m.SetCheck(criterion="Полнота набора", passed=False, details="d", refs=[reqs[0]])],
                          strengths=["«x» — y"])
        if schema is m.ClarifierOutput:
            first = re.search(r"^(R-\d+) \(", prompt, re.M).group(1)
            return schema(
                questions=[m.Question(q_id="Q1", text="Как?", context="c", options=["а) x", "б) y"], related_reqs=[first], blocks="b")],
                links=[m.QuestionLink(q_id="Q1", req_ids=[first], issue_refs=[f"{first}/1"])],
            )
        raise TypeError(schema)
