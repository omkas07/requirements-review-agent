"""Офлайн-тесты агентов: код вокруг LLM (без сети и ключа).

    pytest tests/test_agents.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validator.agents import clarifier, experts, moderator, parser
from validator.agents.graph import agents_output, run_review
from validator.agents.prompting import PROMPTS_DIR, load_prompt, render
from validator.agents.quotes import normalize, quote_fragments, quote_in_document
from validator.domain import models as m
from validator.domain.criteria import SET_CRITERIA, find_vague_words

ROOT = Path(__file__).resolve().parent.parent
DOC = """# Тестовое ТЗ

### Цели
Клиент узнаёт о списании сразу.

* **П-1.** Клиент задаёт лимит от 100 до 500 000 ₸ включительно.
* **П-2.** Ответ: 400, 401 и далее — неуспешный.

| Исходные условия | Действие | Ожидаемый результат |
| :--- | :--- | :--- |
| Баланс 10 000 ₸, лимит 12 000 ₸ | Списать 2 000 ₸ | Один push |
"""


def preq(rid: str, quote: str, ref: str = "") -> m.ParsedRequirement:
    return m.ParsedRequirement(req_id=rid, doc_ref=ref or rid, title=f"T {rid}", quote=quote)


REQS = [
    preq("R-01", "Клиент узнаёт о списании сразу."),
    preq("R-02", "Клиент задаёт лимит от 100 до 500 000 ₸ включительно."),
    preq("R-03", "Ответ: 400, 401 и далее — неуспешный."),
]


# --------------------------------------------------------------------------- #
# Опасные слова и цитаты
# --------------------------------------------------------------------------- #


def test_vague_words_found_with_line_and_context():
    hits = find_vague_words(DOC)
    words = {h["word"].lower() for h in hits}
    assert {"сразу", "и далее"} <= words
    h = next(h for h in hits if h["word"] == "и далее")
    assert h["line"] == DOC.splitlines().index("* **П-2.** Ответ: 400, 401 и далее — неуспешный.") + 1
    assert "401" in h["context"]


def test_vague_words_skip_definite_default():
    assert find_vague_words("По умолчанию уведомление выключено.") == []


@pytest.mark.parametrize(
    "quote",
    [
        "Клиент задаёт лимит от 100 до 500 000 ₸ включительно.",
        "**П-1.** Клиент задаёт лимит",  # разметка Markdown
        "клиент   ЗАДАЁТ лимит",  # регистр и пробелы
        "Баланс 10 000 ₸, лимит 12 000 ₸ | Списать 2 000 ₸",  # соседние ячейки таблицы
        "Клиент задаёт лимит … включительно",  # фрагменты через многоточие
        "Клиент задает лимит",  # ё → е
    ],
)
def test_quote_found(quote):
    assert quote_in_document(quote, normalize(DOC))


@pytest.mark.parametrize("quote", ["Клиент задаёт порог", "включительно … Клиент задаёт лимит", ""])
def test_quote_not_found(quote):
    assert not quote_in_document(quote, normalize(DOC))


def test_quote_fragments_strip_punctuation():
    assert quote_fragments("«…лимит от 100…»") == ["лимит от 100"]


# --------------------------------------------------------------------------- #
# Промпты
# --------------------------------------------------------------------------- #


def test_all_prompts_render():
    names = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
    assert {"tone", "parser", "expert_base", "moderator", "clarifier"} <= set(names)
    variables = {
        "document": "{json: {braces}} $BASE",
        "requirements": "-",
        "role": "$TOKEN",
        "criteria": "-",
        "set_criteria": "-",
        "fintech": "-",
        "vague": "-",
        "findings": "[]",
        "review": "-",
        "business": "-",
    }
    for name in names:
        text = render(name, **variables)
        assert "$tone" not in text
    assert load_prompt("tone").strip() in render("moderator", **variables)


# --------------------------------------------------------------------------- #
# Парсер
# --------------------------------------------------------------------------- #


def test_parser_restores_document_order_and_renumbers():
    shuffled = [
        preq("X9", "Ответ: 400, 401 и далее — неуспешный."),
        preq("X1", "**Клиент задаёт лимит от 100 до 500 000 ₸ включительно.**", "П-1"),
        preq("X5", "Клиент узнаёт о списании сразу."),
        preq("X7", "Клиент задаёт лимит от 100 до 500 000 ₸ включительно.", "П-1"),  # дубль
    ]
    out, warns = parser.postprocess(shuffled, DOC)
    assert [r.req_id for r in out] == ["R-01", "R-02", "R-03"]
    assert out[0].quote.startswith("Клиент узнаёт")
    assert out[1].quote == "Клиент задаёт лимит от 100 до 500 000 ₸ включительно."
    assert any("дубль" in w for w in warns)


def test_parser_keeps_unknown_quote_in_place_with_warning():
    reqs = [preq("A", "Клиент узнаёт о списании сразу."), preq("B", "Выдуманный текст"), preq("C", "Ответ: 400")]
    out, warns = parser.postprocess(reqs, DOC)
    assert [r.quote for r in out] == ["Клиент узнаёт о списании сразу.", "Выдуманный текст", "Ответ: 400"]
    assert any("не найдена" in w for w in warns)


# --------------------------------------------------------------------------- #
# Эксперты
# --------------------------------------------------------------------------- #


def test_expert_postprocess_normalizes_ids():
    raw = [
        m.Finding(req_id="R5", criterion="Полнота", text="t", quote="**лимит**", related_req_ids=["R-02", "R-99", "SET"]),
        m.Finding(req_id="R-2", criterion="Однозначность", text="t", quote="«лимит»", related_req_ids=["R-02", "r-3"]),
        m.Finding(req_id="set", criterion="Полнота", text="t", quote="x"),
    ]
    out, warns = experts.postprocess("tester", raw, REQS)
    assert [f.req_id for f in out] == ["SET", "R-02", "SET"]  # R5 нет в нарезке → SET
    assert out[1].related_req_ids == ["R-03"]  # себя, неизвестные и SET убираем
    assert out[0].quote == "лимит" and out[1].quote == "лимит"
    assert {f.expert for f in out} == {"Тестировщик"}
    assert len(warns) == 1


def test_expert_prompt_contains_requirements_and_hints():
    prompt = experts.build_prompt("security", DOC, REQS, find_vague_words(DOC))
    assert "R-03 |" in prompt and "«и далее»" in prompt and "информационной безопасности" in prompt
    assert "<<<ДОКУМЕНТ" in prompt


# --------------------------------------------------------------------------- #
# Модератор
# --------------------------------------------------------------------------- #


def issue(text: str = "t", quote: str = "лимит", **kw) -> m.Issue:
    return m.Issue(criterion="Полнота", text=text, quote=quote, **kw)


def test_moderator_assemble_enforces_invariants():
    llm_out = m.ModeratorLLMOutput(
        requirements=[
            m.ModeratedRequirement(req_id="R-01", status="ok", issues=[issue(question_id="В-7")]),
            m.ModeratedRequirement(req_id="R-02", status="blocking", issues=[], suggestion="s"),
            m.ModeratedRequirement(req_id="R-77", status="blocking", issues=[issue()]),
        ],
        set_checks=[
            m.SetCheck(criterion="Полнота набора", passed=False, details="d", refs=["R-01", "R-77"]),
            m.SetCheck(criterion="Трассируемость", passed=True, details="d", refs=[]),
        ],
        strengths=["«лимит» — понятно"],
    )
    findings = [m.Finding(req_id="R-03", criterion="Полнота", text="открытый список", quote="и далее", severity="blocking")]
    out, warns = moderator.assemble(REQS, llm_out, findings)

    r1, r2, r3 = out.requirements
    assert (r1.status, r1.issues[0].question_id) == ("needs_clarification", None)
    assert (r2.status, r2.suggestion) == ("ok", None)
    assert r3.status == "blocking" and r3.issues[0].text == "открытый список"  # пропущено → из находок
    assert r1.quote == REQS[0].quote and r1.doc_ref == REQS[0].doc_ref  # цитаты из парсера
    assert [c.criterion for c in out.set_checks] == [c.name for c in SET_CRITERIA]
    assert out.set_checks[0].refs == ["R-01"]
    assert any("R-77" in w for w in warns) and any("R-03" in w for w in warns)


def test_moderator_fallback_without_llm():
    findings = [
        m.Finding(req_id="R-02", criterion="Полнота", text="a", quote="лимит", severity="minor"),
        m.Finding(req_id="SET", criterion="Модифицируемость", text="нет версии", quote="ТЗ"),
    ]
    out, _ = moderator.assemble(REQS, None, findings)
    assert [r.status for r in out.requirements] == ["ok", "needs_clarification", "ok"]
    mod = next(c for c in out.set_checks if c.criterion == "Модифицируемость")
    assert not mod.passed and "нет версии" in mod.details


# --------------------------------------------------------------------------- #
# Агент уточнений
# --------------------------------------------------------------------------- #


def moderated() -> m.ModeratorOutput:
    reqs = [
        m.Requirement(**REQS[0].model_dump(), status="needs_clarification", issues=[issue("a"), issue("b")]),
        m.Requirement(**REQS[1].model_dump(), status="blocking", issues=[issue("c")]),
        m.Requirement(**REQS[2].model_dump(), status="ok"),
    ]
    return m.ModeratorOutput(requirements=reqs, set_checks=[], strengths=[])


def q(qid: str, related: list[str]) -> m.Question:
    return m.Question(q_id=qid, text="?", context="c", options=["а) x", "б) y"], related_reqs=related, blocks=None)


def test_clarifier_apply_links_questions():
    out = m.ClarifierOutput(
        questions=[q("Q-a", ["R-01", "R-99"]), q("Q-b", [])],
        links=[
            m.QuestionLink(q_id="Q-a", req_ids=["R-01"], issue_refs=["R-01/2", "R-01/9"]),
            m.QuestionLink(q_id="Q-b", req_ids=["R-02"], issue_refs=[]),
            m.QuestionLink(q_id="Q-zzz", req_ids=["R-01"]),
        ],
    )
    result, questions, warns = clarifier.apply(moderated(), out)
    assert [x.q_id for x in questions] == ["В-1", "В-2"]
    r1, r2, _ = result.requirements
    assert [i.question_id for i in r1.issues] == [None, "В-1"]  # именно замечание №2
    assert r2.issues[0].question_id == "В-2"  # по req_ids — первое свободное
    assert questions[0].related_reqs == ["R-01"]  # R-99 нет в нарезке
    assert questions[1].related_reqs == ["R-02"]  # добавлено из links
    assert any("R-01/9" in w for w in warns) and any("Q-zzz" in w for w in warns)


def test_clarifier_review_block_numbers_issues():
    text = clarifier.review_block(moderated())
    assert "R-01/1." in text and "R-01/2." in text and "R-02/1." in text and "R-03" not in text


# --------------------------------------------------------------------------- #
# Граф целиком на фейковом LLM
# --------------------------------------------------------------------------- #


class FakeLLM:
    model = "fake"

    def __init__(self, fail: set[type] = frozenset()):
        self.fail = fail
        self.calls: list[str] = []

    def ask_json(self, prompt, schema):
        self.calls.append(schema.__name__)
        if schema in self.fail:
            raise RuntimeError("LLM недоступен")
        if schema is m.ParserOutput:
            return schema(requirements=[preq(f"Z{i}", r.quote, r.doc_ref) for i, r in enumerate(reversed(REQS))])
        if schema is m.ExpertOutput:
            return schema(findings=[m.Finding(req_id="R-03", criterion="Проверяемость", text="t", quote="и далее",
                                              needs_business_decision=True, severity="blocking")])
        if schema is m.ModeratorLLMOutput:
            return schema(
                requirements=[m.ModeratedRequirement(req_id="R-03", status="blocking", issues=[issue(quote="и далее")])],
                set_checks=[m.SetCheck(criterion=c.name, passed=True, details="-", refs=[]) for c in SET_CRITERIA],
                strengths=["«от 100 до 500 000 ₸ включительно» — границы видны"],
            )
        if schema is m.ClarifierOutput:
            return schema(questions=[q("1", ["R-03"])], links=[m.QuestionLink(q_id="1", req_ids=["R-03"], issue_refs=["R-03/1"])])
        raise TypeError(schema)


def test_graph_end_to_end():
    llm = FakeLLM()
    state = run_review(llm, DOC, source="x.md", passport={"model": "fake"}, include_optional=False)
    assert sorted(llm.calls) == sorted(["ParserOutput"] + ["ExpertOutput"] * 3 + ["ModeratorLLMOutput", "ClarifierOutput"])
    assert len(state["findings"]) == 3  # fan-in: находки трёх экспертов сложены
    reqs = state["moderated"].requirements
    assert [r.req_id for r in reqs] == ["R-01", "R-02", "R-03"]
    assert reqs[2].issues[0].question_id == "В-1"
    data = agents_output(state)
    assert data["_meta"]["llm_calls"] == 6
    restored = m.ModeratorOutput.model_validate(data)
    assert restored.requirements[2].status == "blocking"
    assert [m.Question.model_validate(x).q_id for x in data["questions"]] == ["В-1"]


def test_graph_survives_expert_and_clarifier_failures():
    llm = FakeLLM(fail={m.ExpertOutput, m.ClarifierOutput})
    state = run_review(llm, DOC, include_optional=False)
    assert state["findings"] == [] and state["questions"] == []
    assert sum("ошибка LLM" in w for w in state["warnings"]) == 4
    assert len(state["moderated"].requirements) == 3


def test_graph_fails_fast_without_requirements():
    class Empty(FakeLLM):
        def ask_json(self, prompt, schema):
            return m.ParserOutput(requirements=[])

    with pytest.raises(RuntimeError, match="ни одного требования"):
        run_review(Empty(), DOC, include_optional=False)


def test_parser_keeps_same_text_in_different_places():
    reqs = [preq("A", "лимит", "Таблица запроса"), preq("B", "лимит", "Таблица ответа"), preq("C", "лимит", "Таблица ответа")]
    out, warns = parser.postprocess(reqs, DOC)
    assert [r.doc_ref for r in out] == ["Таблица запроса", "Таблица ответа"] and len(warns) == 1


def test_moderator_cannot_close_requirement_with_important_findings():
    llm_out = m.ModeratorLLMOutput(
        requirements=[m.ModeratedRequirement(req_id=r.req_id, status="ok") for r in REQS],
        set_checks=[], strengths=[],
    )
    findings = [
        m.Finding(req_id="R-01", criterion="Проверяемость", text="срок неизмерим", quote="сразу", severity="major"),
        m.Finding(req_id="R-02", criterion="Полнота", text="мелочь", quote="лимит", severity="minor"),
    ]
    out, warns = moderator.assemble(REQS, llm_out, findings)
    r1, r2, _ = out.requirements
    assert r1.status == "needs_clarification" and r1.issues[0].text == "срок неизмерим"
    assert r2.status == "ok"  # мелкую находку модератор вправе отбросить
    assert any("R-01" in w and "возвращены" in w for w in warns)
