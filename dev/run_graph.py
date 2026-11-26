"""Шаг 7: полный прогон графа → reports/agents_output.json.

    python dev/run_graph.py [--input path] [--output reports/agents_output.json] [--fake]
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from common import ROOT, arg_parser, make_llm, quote_stats, read_document  # noqa: I001

from validator.agents.graph import agents_output, run_review

ICON = {"ok": "🟢", "needs_clarification": "🟡", "blocking": "🔴"}


def main() -> None:
    ap = arg_parser(__doc__)
    ap.add_argument("--output", type=Path, default=ROOT / "reports" / "agents_output.json")
    args = ap.parse_args()
    path, doc = read_document(args.input)
    llm = make_llm(args)
    t0 = time.time()
    state = run_review(llm, doc, source=(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path).as_posix())
    elapsed = time.time() - t0
    data = agents_output(state)
    data["_meta"].update(
        {
            "model": getattr(llm, "model", "?"),
            "seconds": round(elapsed, 1),
            "http_calls": getattr(llm, "calls", None),
            "tokens_in": getattr(llm, "tokens_in", None),
            "tokens_out": getattr(llm, "tokens_out", None),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    mod = state["moderated"]
    print("\n| ID   | Где в документе                    | Кратко | Статус")
    for r in mod.requirements:
        qs = sorted({i.question_id for i in r.issues if i.question_id})
        print(f"| {r.req_id} | {r.doc_ref[:35]:35} | {r.title[:45]:45} | {ICON[r.status]} {len(r.issues)} {' '.join(qs)}")
    print("\nВопросы:")
    for q in state.get("questions", []):
        print(f"  {'🔴' if q.blocks else '🟡'} {q.q_id}. {q.text}  → {', '.join(q.related_reqs)}")
        for o in q.options:
            print(f"       {o}")
    print("\nПроверка набора:")
    for c in mod.set_checks:
        print(f"  {'✅' if c.passed else '❌'} {c.criterion}: {c.details[:120]}")
    print("\nСильные стороны:")
    for s in mod.strengths:
        print("  + " + s)
    quotes = [i.quote for r in mod.requirements for i in r.issues]
    ok, total, bad = quote_stats(quotes, doc)
    print(f"\nЦитаты замечаний — подстроки документа: {ok}/{total} = {ok / max(total, 1):.0%}")
    for q in bad:
        print(f"  ✗ «{q[:100]}»")
    print("\nПредупреждения:")
    for w in state.get("warnings", []):
        print("  ! " + w)
    st = {s: sum(r.status == s for r in mod.requirements) for s in ICON}
    print(
        f"\nИтог: требований {len(mod.requirements)} (🔴 {st['blocking']} · 🟡 {st['needs_clarification']} · 🟢 {st['ok']}), "
        f"замечаний {total}, вопросов {len(state.get('questions', []))}"
    )
    print("Узлы: " + ", ".join(f"{m['node']} {m['seconds']}с" for m in state["metrics"]))
    print(
        f"Вызовов LLM (узлы): {data['_meta']['llm_calls']} · HTTP-запросов с ретраями: {data['_meta']['http_calls']} · "
        f"токены in/out: {data['_meta']['tokens_in']}/{data['_meta']['tokens_out']} · время: {elapsed:.0f} с"
    )
    print(f"→ {args.output}")


if __name__ == "__main__":
    main()
