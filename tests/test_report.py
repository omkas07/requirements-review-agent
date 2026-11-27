"""Рендер шаблона по eval/fake_result.json: структура, якоря, двусторонние ссылки."""

import json
import re
from pathlib import Path

import pytest

from validator.agents.report_builder import build_report, q_anchor, req_anchor
from validator.domain.models import ModeratorOutput, Question

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ["## 1. Паспорт прогона", "## 2. Сильные стороны документа", "## 3. Нарезка требований",
            "## 4. Проверка каждого требования", "## 5. Вопросы к автору ТЗ", "## 6. Проверка всего набора",
            "## 7. Сводка", "## 8. Итог и порядок исправления"]


@pytest.fixture(scope="module")
def data():
    return json.loads((ROOT / "eval" / "fake_result.json").read_text(encoding="utf-8"))


def render(data, **kw):
    mod = ModeratorOutput.model_validate(data)
    qs = [Question.model_validate(q) for q in data["questions"]]
    passport = {"document": "examples/requirements.md", "date": "27.11.2026", "model": "m", "commit": "abc123", "mode": "обычный"}
    return build_report(mod, qs, passport=passport, **kw)


def test_sections_in_order(data):
    text = render(data)
    positions = [text.index(s) for s in SECTIONS]
    assert positions == sorted(positions)
    assert text.index("Разработку начинать нельзя") < positions[0]  # плашка «Коротко о главном» до паспорта


def test_every_link_has_anchor(data):
    text = render(data)
    anchors = set(re.findall(r'<a id="([^"]+)"></a>', text))
    links = set(re.findall(r"\]\(#([^)]+)\)", text))
    assert {"nav", "questions"} <= anchors
    assert links <= anchors, links - anchors
    assert all(re.fullmatch(r"[a-z0-9-]+", a) for a in anchors)  # только ASCII


def test_bidirectional_links(data):
    text = render(data)
    assert "[R-02](#r-02)" in text  # таблица нарезки → требование
    assert "[❓ Вопрос В-1](#q-1)" in text  # требование → вопрос
    assert "[R-04 (Критерий приёмки №2)](#r-04)" in text  # вопрос → требование
    assert text.count("[↑ к требованиям](#nav)") == len(data["requirements"])


def test_review_order_and_ok_line(data):
    text = render(data)
    sec4 = text[text.index(SECTIONS[3]):text.index(SECTIONS[4])]
    order = re.findall(r"#### \S+ (R-\d+)", sec4)
    assert order == ["R-02", "R-03", "R-04", "R-01"]  # 🔴 → 🟡 → 🟢, внутри — порядок документа
    assert "Замечаний нет: однозначно, проверяемо" in sec4


def test_impact_only_where_given(data):
    text = render(data)
    expected = sum(1 for r in data["requirements"] for i in r["issues"] if i["impact"])
    assert text.count("⚠️ **Если не исправить:**") == expected


def test_verdict_without_readiness_number(data):
    text = render(data)
    assert text.splitlines()[2].startswith("> 🔴 **Разработку начинать нельзя.**")
    assert "Готовность" not in text and "/ 100" not in text


def test_answers_unblock_and_are_shown(data):
    text = render(data, answers={"В-1": "а) январь"})
    assert "✅ **Ответ автора:** а) январь" in text
    assert "Нужны ваши ответы:** [В-2](#q-2)" in text


def test_table_cells_escape_pipes(data):
    data = json.loads(json.dumps(data))
    data["requirements"][0]["title"] = "a | b"
    assert "a \\| b" in render(data)


def test_anchor_helpers():
    assert req_anchor("R-05") == "r-05" and q_anchor("В-12") == "q-12"
