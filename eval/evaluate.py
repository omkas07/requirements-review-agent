"""Сравнение выхода агентов с эталоном: «найдено X из Y, лишних Z».

    python eval/evaluate.py
    python eval/evaluate.py --golden eval/golden_2.json       # после прогона второго ТЗ
    python eval/evaluate.py --json eval/last_score.json     # сохранить метрики (для слайдов)
    python eval/evaluate.py --llm                             # сопоставление через LLM

По умолчанию сопоставление — по ключевым словам эталона (без LLM, воспроизводимо): пункт
эталона найден, если в одном замечании есть хотя бы одно слово из каждой группы keywords.
С --llm сопоставляет модель (1 вызов, понимает перефразирование) и печатает расхождения
со словами — их стоит проверить глазами.
«Лишние» — замечания, не совпавшие ни с одним пунктом: эталон не исчерпывающий,
поэтому это «не подтверждённые эталоном», а не обязательно ложные.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field  # noqa: E402

from validator.agents.quotes import normalize  # noqa: E402


def matches(keywords: list[list[str]], haystack: str) -> bool:
    return all(any(normalize(word) in haystack for word in group) for group in keywords)


def issue_records(result: dict) -> list[dict]:
    """Замечания к требованиям + невыполненные проверки набора (последние не считаются «лишними»).

    Ищем только в самом замечании (критерий, текст, цитата, место в документе): цитата
    требования и предложение дали бы совпадения, которых в замечании нет.
    """
    out = []
    for r in result.get("requirements", []):
        for n, i in enumerate(r.get("issues", []), start=1):
            text = " ".join([i.get("criterion", ""), i.get("text", ""), i.get("quote", ""), r.get("doc_ref", "")])
            out.append({"ref": f"{r['req_id']}/{n}", "label": f"{r['req_id']} [{i.get('criterion')}] {i.get('text', '')}",
                        "hay": normalize(text), "set": False})
    for c in result.get("set_checks", []):
        if not c.get("passed", True):
            out.append({"ref": f"SET:{c['criterion']}", "label": f"Набор [{c['criterion']}] {c.get('details', '')}",
                        "hay": normalize(f"{c['criterion']} {c.get('details', '')}"), "set": True})
    return out


def question_records(result: dict) -> list[dict]:
    return [
        {"ref": q["q_id"], "label": f"{q['q_id']}. {q['text']}",
         "hay": normalize(" ".join([q.get("text", ""), q.get("context", ""), *q.get("options", [])]))}
        for q in result.get("questions", [])
    ]


def keyword_hits(issues: list[dict], questions: list[dict], golden: dict) -> tuple[dict, dict]:
    """Сопоставление по ключевым словам: {id пункта: [ссылки на замечания]}."""
    items = {it["id"]: [x["ref"] for x in issues if matches(it["keywords"], x["hay"])] for it in golden["items"]}
    qs = {it["id"]: [x["ref"] for x in questions if matches(it["keywords"], x["hay"])] for it in golden.get("questions", [])}
    return items, qs


class ItemMatch(BaseModel):
    item_id: int
    refs: list[str] = Field(description="ссылки на замечания, которые описывают ЭТУ проблему; [] если ни одно")
    reason: str = Field(description="одно короткое предложение: почему совпадает или почему нет")


class LLMMatchOutput(BaseModel):
    items: list[ItemMatch]
    questions: list[ItemMatch]


LLM_PROMPT = """Ты проверяешь отчёт агента ревью ТЗ по эталону известных проблем.
Для КАЖДОГО пункта эталона найди замечания агента, которые описывают ту же самую проблему:
то же место (или то же противоречие между теми же местами) и та же суть. Формулировки могут
отличаться. Будь строг: общая тема («что-то про API», «что-то про push») — не совпадение;
замечание засчитывается, только если по нему автор ТЗ понял бы и исправил именно эту проблему.
Если пункт эталона составной (несколько проблем через «;»), засчитывай замечания, которые
описывают хотя бы главную его часть. Если совпадений нет — refs = [].

Так же сопоставь ожидаемые вопросы с вопросами агента (ссылки вида «В-1»): вопрос совпадает,
если просит автора ТЗ принять то же решение.

В refs используй только ссылки из списков ниже, без изменений. В items — запись для каждого
пункта эталона, в questions — для каждого ожидаемого вопроса (item_id — номер ожидаемого вопроса).

## Пункты эталона
$items

## Ожидаемые вопросы
$expected_questions

## Замечания агента (ссылка | место в документе | критерий | текст | цитата)
$issues

## Вопросы агента
$questions
"""


def llm_hits(issues: list[dict], questions: list[dict], golden: dict, result: dict, llm) -> tuple[dict, dict]:
    """Сопоставление через LLM: один вызов на весь отчёт."""
    from string import Template

    req = {r["req_id"]: r for r in result.get("requirements", [])}
    issue_lines = []
    for x in issues:
        if x["set"]:
            issue_lines.append(f"- {x['ref']} | весь документ | {x['label']}")
            continue
        rid, n = x["ref"].split("/")
        r = req[rid]
        i = r["issues"][int(n) - 1]
        issue_lines.append(f"- {x['ref']} | {r['doc_ref']} | {i['criterion']} | {i['text']} | «{i['quote']}»")
    prompt = Template(LLM_PROMPT).substitute(
        items="\n".join(f"- {it['id']}. {it['title']}" for it in golden["items"]),
        expected_questions="\n".join(f"- {it['id']}. {it['title']}" for it in golden.get("questions", [])) or "(нет)",
        issues="\n".join(issue_lines) or "(нет)",
        questions="\n".join(f"- {q['label']}" for q in questions) or "(нет)",
    )
    out = llm.ask_json(prompt, LLMMatchOutput)
    known_i = {x["ref"] for x in issues}
    known_q = {x["ref"] for x in questions}

    def fix(ref: str) -> str:  # модель иногда пишет латинскую «B» вместо «В» и пробелы
        ref = ref.strip().replace(" ", "")
        return "В" + ref[1:] if ref[:1] in ("B", "b", "в") else ref

    items = {it["id"]: [] for it in golden["items"]}
    for m in out.items:
        if m.item_id in items:
            items[m.item_id] = [r.strip() for r in m.refs if r.strip() in known_i]
    qs = {it["id"]: [] for it in golden.get("questions", [])}
    for m in out.questions:
        if m.item_id in qs:
            qs[m.item_id] = [fix(r) for r in m.refs if fix(r) in known_q]
    return items, qs


def summarize(issues: list[dict], questions: list[dict], golden: dict, item_hits: dict, q_hits: dict) -> dict:
    found, missed, used = [], [], set()
    for item in golden["items"]:
        hits = item_hits.get(item["id"], [])
        (found if hits else missed).append({"id": item["id"], "title": item["title"], "hits": hits})
        used.update(hits)
    extra = [x for x in issues if not x["set"] and x["ref"] not in used]
    real_issues = [x for x in issues if not x["set"]]

    q_found, q_missed = [], []
    for item in golden.get("questions", []):
        hits = q_hits.get(item["id"], [])
        (q_found if hits else q_missed).append({"id": item["id"], "title": item["title"], "hits": hits})

    total = len(golden["items"])
    return {
        "found": len(found),
        "total": total,
        "recall": round(len(found) / total, 3) if total else 0.0,
        "issues": len(real_issues),
        "extra": len(extra),
        "confirmed_share": round(1 - len(extra) / len(real_issues), 3) if real_issues else 0.0,
        "questions_found": len(q_found),
        "questions_expected": len(golden.get("questions", [])),
        "questions_asked": len(questions),
        "found_items": found,
        "missed_items": missed,
        "extra_issues": [x["label"][:160] for x in extra],
        "questions_found_items": q_found,
        "questions_missed_items": q_missed,
    }


def evaluate(result: dict, golden: dict, llm=None) -> dict:
    """Оценка по ключевым словам; с llm — через LLM-сопоставление."""
    issues = issue_records(result)
    questions = question_records(result)
    hits = llm_hits(issues, questions, golden, result, llm) if llm is not None else keyword_hits(issues, questions, golden)
    score = summarize(issues, questions, golden, *hits)
    score["method"] = "llm" if llm is not None else "keywords"
    return score


def print_report(s: dict) -> None:
    print(f"Найдено: {s['found']} из {s['total']} пунктов эталона ({s['recall']:.0%})")
    print(f"Лишних (не подтверждённых эталоном): {s['extra']} из {s['issues']} замечаний "
          f"(подтверждено {s['confirmed_share']:.0%})")
    print(f"Ожидаемых вопросов задано: {s['questions_found']} из {s['questions_expected']} "
          f"(всего вопросов: {s['questions_asked']})")
    if s["missed_items"]:
        print("\nПропущено:")
        for m in s["missed_items"]:
            print(f"  ✗ {m['id']:>2}. {m['title']}")
    if s["questions_missed_items"]:
        print("\nНе задан вопрос:")
        for m in s["questions_missed_items"]:
            print(f"  ✗ {m['title']}")
    print("\nНайдено:")
    for f in s["found_items"]:
        print(f"  ✓ {f['id']:>2}. {f['title']}  ← {', '.join(f['hits'][:4])}")
    if s["extra_issues"]:
        print("\nНе подтверждены эталоном (проверить вручную):")
        for e in s["extra_issues"]:
            print(f"  ? {e}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--result", type=Path, default=ROOT / "eval" / "last_run.json", help="выход агентов (по умолчанию — последний прогон)")
    ap.add_argument("--golden", type=Path, default=ROOT / "eval" / "golden.json")
    ap.add_argument("--json", type=Path, default=None, help="сохранить метрики в JSON")
    ap.add_argument("--llm", action="store_true", help="сопоставлять через LLM (1 вызов) и сравнить с ключевыми словами")
    args = ap.parse_args(argv)
    if not args.result.exists():
        print(f"Нет файла {args.result}: сначала запустите python main.py …", file=sys.stderr)
        return 2
    result = json.loads(args.result.read_text(encoding="utf-8"))
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    print(f"Эталон: {args.golden.name} · выход агентов: {args.result}\n")
    kw = evaluate(result, golden)
    if not args.llm:
        print_report(kw)
        score = kw
    else:
        from validator.adapters.factory import get_llm

        llm = get_llm()
        score = evaluate(result, golden, llm=llm)
        print(f"Сопоставление через LLM ({llm.model}):")
        print_report(score)
        print(f"\nПо ключевым словам: найдено {kw['found']} из {kw['total']}, вопросов {kw['questions_found']} из {kw['questions_expected']}")
        kw_found = {f["id"] for f in kw["found_items"]}
        llm_found = {f["id"] for f in score["found_items"]}
        titles = {it["id"]: it["title"] for it in golden["items"]}
        for i in sorted(llm_found - kw_found):
            print(f"  + LLM засчитала, слова — нет: {i}. {titles[i]}")
        for i in sorted(kw_found - llm_found):
            print(f"  − слова засчитали, LLM — нет: {i}. {titles[i]}")
        score = {**score, "keywords": {k: kw[k] for k in ("found", "total", "extra", "questions_found")}}
    if args.json:
        args.json.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
