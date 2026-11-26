"""Загрузка и рендер промптов из validator/prompts/*.md.

Рендер — string.Template ($document, $requirements, $tone…), а не str.format():
в промптах есть фигурные скобки (JSON-примеры). Неизвестная переменная — ошибка,
чтобы опечатка в промпте не уходила в LLM молча.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from string import Template

from validator.domain.models import ParsedRequirement

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(name: str, **variables: str) -> str:
    """Подставляет переменные в промпт; $tone подставляется всегда."""
    variables.setdefault("tone", load_prompt("tone"))
    # Шаблоны могут включать другие шаблоны ($tone, $expert_base) — рендерим их тоже.
    return Template(load_prompt(name)).substitute(variables)


def wrap_document(document: str) -> str:
    """Документ как есть, внутри разделителей. Номера строк не добавляем:
    модель начинает вставлять их в цитаты."""
    return f"<<<ДОКУМЕНТ\n{document.strip()}\nДОКУМЕНТ>>>"


def requirements_block(reqs: list[ParsedRequirement]) -> str:
    return "\n".join(
        f"- {r.req_id} | {r.doc_ref} | {r.title}\n  цитата: «{r.quote}»" for r in reqs
    )


def to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)
