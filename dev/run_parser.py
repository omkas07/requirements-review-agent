"""Шаг 2: только парсер. Печатает таблицу нарезки и долю цитат-подстрок.

    python dev/run_parser.py [--input path] [--fake] [--cache]
"""

from __future__ import annotations

import json
import time

from common import ROOT, arg_parser, make_llm, quote_stats, read_document  # noqa: I001

from validator.agents.parser import parse_requirements


def main() -> None:
    args = arg_parser(__doc__).parse_args()
    path, doc = read_document(args.input)
    llm = make_llm(args)
    t0 = time.time()
    reqs, warns = parse_requirements(llm, doc)
    print(f"Документ: {path}  · требований: {len(reqs)}  · {time.time() - t0:.1f} с\n")
    print(f"| {'ID':5} | {'Где в документе':38} | Кратко")
    print(f"|{'-' * 7}|{'-' * 40}|{'-' * 40}")
    for r in reqs:
        print(f"| {r.req_id:5} | {r.doc_ref[:38]:38} | {r.title}")
    ok, total, bad = quote_stats([r.quote for r in reqs], doc)
    print(f"\nЦитаты-подстроки: {ok}/{total}")
    for q in bad:
        print(f"  ✗ «{q[:100]}»")
    for w in warns:
        print("  ! " + w)
    out = ROOT / "dev" / "out"
    out.mkdir(exist_ok=True)
    (out / "parser.json").write_text(json.dumps([r.model_dump() for r in reqs], ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
