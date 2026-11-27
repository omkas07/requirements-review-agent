import pytest

from validator.domain.models import Issue, Question, Requirement, SetCheck
from validator.domain.scoring import (
    THRESHOLD_GREEN,
    THRESHOLD_RED,
    WEIGHT_BLOCKING,
    WEIGHT_NEEDS_CLARIFICATION,
    plural,
    readiness,
    sort_for_review,
    summary,
    verdict,
)


def req(rid, status, criteria=("Полнота",)):
    issues = [] if status == "ok" else [Issue(criterion=c, text="t", quote="q") for c in criteria]
    return Requirement(req_id=rid, doc_ref=rid, title="t", quote="q", status=status, issues=issues)


def q(qid, blocks=None):
    return Question(q_id=qid, text="?", context="c", options=["а) x"], related_reqs=[], blocks=blocks)


def test_readiness_formula_and_floor():
    reqs = [req("R-01", "blocking"), req("R-02", "needs_clarification"), req("R-03", "ok")]
    assert readiness(reqs) == 100 - WEIGHT_BLOCKING - WEIGHT_NEEDS_CLARIFICATION
    assert readiness([req(f"R-{i}", "blocking") for i in range(10)]) == 0


def test_verdict_red_on_blocking_requirement_even_with_high_score():
    v = verdict([req("R-01", "blocking")] + [req(f"R-{i}", "ok") for i in range(2, 10)], [])
    assert v.level == "red" and not v.can_develop


def test_verdict_red_on_blocking_question_until_answered():
    reqs = [req("R-01", "needs_clarification")]
    assert verdict(reqs, [q("В-1", blocks="расчёт")]).level == "red"
    assert verdict(reqs, [q("В-1", blocks="расчёт")], answered={"В-1"}).level == "green"


@pytest.mark.parametrize(
    "n_yellow, level",
    [(0, "green"), ((100 - THRESHOLD_GREEN) // WEIGHT_NEEDS_CLARIFICATION, "green"),
     ((100 - THRESHOLD_GREEN) // WEIGHT_NEEDS_CLARIFICATION + 1, "yellow"),
     ((100 - THRESHOLD_RED) // WEIGHT_NEEDS_CLARIFICATION + 1, "red")],
)
def test_verdict_thresholds(n_yellow, level):
    reqs = [req(f"R-{i}", "needs_clarification") for i in range(n_yellow)]
    assert verdict(reqs, []).level == level


def test_testing_blocked_by_untestable_blocking_requirement():
    assert not verdict([req("R-01", "blocking", ("Проверяемость",))], []).can_test
    assert verdict([req("R-01", "blocking", ("Уместность",))], []).can_test


def test_sort_keeps_document_order_inside_status():
    reqs = [req("R-01", "ok"), req("R-02", "blocking"), req("R-03", "needs_clarification"), req("R-04", "blocking")]
    assert [r.req_id for r in sort_for_review(reqs)] == ["R-02", "R-04", "R-03", "R-01"]


def test_summary_counts():
    reqs = [req("R-01", "blocking", ("Полнота", "Полнота")), req("R-02", "ok")]
    s = summary(reqs, [q("В-1", "x"), q("В-2")], [SetCheck(criterion="Полнота", passed=False, details="d", refs=[])])
    assert (s["blocking"], s["ok"], s["issues"], s["questions"], s["blocking_questions"], s["set_failed"]) == (1, 1, 2, 2, 1, 1)
    assert s["by_criterion"][0] == ("Полнота", 2)


@pytest.mark.parametrize("n, word", [(1, "вопрос"), (3, "вопроса"), (5, "вопросов"), (11, "вопросов"), (21, "вопрос"), (24, "вопроса")])
def test_plural(n, word):
    assert plural(n, "вопрос", "вопроса", "вопросов") == word
