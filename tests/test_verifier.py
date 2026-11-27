from validator.agents.verifier import node, verify
from validator.domain.models import Issue, ModeratorOutput, Requirement

DOC = "### Ф\n* **Ф-1.** Клиент задаёт порог от 1 000 до 1 000 000 ₸ включительно.\n| Порог | `amount` |"


def make(issues_by_req):
    reqs = [
        Requirement(req_id=rid, doc_ref=rid, title="t", quote="q", status="blocking", issues=issues, suggestion="s")
        for rid, issues in issues_by_req.items()
    ]
    return ModeratorOutput(requirements=reqs, set_checks=[], strengths=[])


def issue(quote):
    return Issue(criterion="Полнота", text="t", quote=quote)


def test_keeps_real_quotes_after_normalization():
    mod = make({"R-01": [issue("клиент ЗАДАЁТ  порог"), issue("**Ф-1.** Клиент задает порог"), issue("Порог | amount")]})
    out, warns = verify(DOC, mod)
    assert len(out.requirements[0].issues) == 3 and warns == []


def test_drops_invented_quotes_and_logs_count():
    mod = make({"R-01": [issue("от 1 000 до 1 000 000 ₸"), issue("порог от 500 ₸")], "R-02": [issue("выдумано")]})
    out, warns = verify(DOC, mod)
    r1, r2 = out.requirements
    assert [i.quote for i in r1.issues] == ["от 1 000 до 1 000 000 ₸"] and r1.status == "blocking"
    assert r2.issues == [] and r2.status == "ok" and r2.suggestion is None
    assert "выброшено 2" in warns[0] and any("выдумано" in w for w in warns)


def test_does_not_mutate_input():
    mod = make({"R-01": [issue("выдумано")]})
    verify(DOC, mod)
    assert len(mod.requirements[0].issues) == 1


def test_node_contract():
    mod = make({"R-01": [issue("выдумано"), issue("включительно")]})
    upd = node({"document": DOC, "moderated": mod})
    assert set(upd) == {"moderated", "warnings", "metrics"}
    assert upd["metrics"][0]["issues_dropped"] == 1
