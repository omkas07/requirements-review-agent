"""Шаги 3–4: эксперты на нарезке из dev/out/parser.json.

    python dev/run_experts.py --role developer      # один эксперт
    python dev/run_experts.py                       # все три параллельно
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from common import ROOT, arg_parser, make_llm, quote_stats, read_document  # noqa: I001

from validator.agents.experts import EXPERTS, run_expert
from validator.agents.parser import parse_requirements
from validator.domain.criteria import find_vague_words
from validator.domain.models import ParsedRequirement


def main() -> None:
    ap = arg_parser(__doc__)
    ap.add_argument("--role", choices=list(EXPERTS), action="append")
    args = ap.parse_args()
    path, doc = read_document(args.input)
    llm = make_llm(args)
    cached = ROOT / "dev" / "out" / "parser.json"
    if cached.exists() and not args.fake:
        reqs = [ParsedRequirement(**x) for x in json.loads(cached.read_text(encoding="utf-8"))]
    else:
        reqs, _ = parse_requirements(llm, doc)
    hits = find_vague_words(doc)
    roles = args.role or list(EXPERTS)
    t0 = time.time()
    with ThreadPoolExecutor(len(roles)) as pool:
        results = dict(zip(roles, pool.map(lambda r: run_expert(llm, r, doc, reqs, hits), roles)))
    print(f"Эксперты {roles}: {time.time() - t0:.1f} с\n")
    all_findings = []
    for role, (found, warns) in results.items():
        print(f"=== {EXPERTS[role][1]}: {len(found)} находок")
        for f in found:
            flag = "❓" if f.needs_business_decision else "  "
            print(f"{flag} {f.req_id:5} [{f.severity:8}] {f.criterion}: {f.text}\n         «{f.quote}»")
        for w in warns:
            print("  ! " + w)
        ok, total, bad = quote_stats([f.quote for f in found], doc)
        print(f"Цитаты-подстроки: {ok}/{total} = {ok / max(total, 1):.0%}")
        for q in bad:
            print(f"  ✗ «{q[:100]}»")
        print()
        all_findings += [f.model_dump() for f in found]
    (ROOT / "dev" / "out").mkdir(exist_ok=True)
    (ROOT / "dev" / "out" / "findings.json").write_text(json.dumps(all_findings, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
