"""Агент статического ревью ТЗ.

    python main.py --input examples/requirements.md --output reports/report.md
    python main.py --input examples/requirements.pdf --output reports/report_pdf.md

В папку отчёта пишется только отчёт. Служебный выход агентов последнего прогона (JSON)
сохраняется в eval/last_run.json (не в git) — для eval/evaluate.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from validator.adapters.factory import get_llm, get_reader, get_writer
from validator.agents.graph import agents_output, build_graph
from validator.config import ROOT, ConfigError, load_settings

LAST_RUN = ROOT / "eval" / "last_run.json"  # служебный JSON для eval/evaluate.py, не в git

NODE_LABELS = {
    "prepare": "Поиск «опасных слов»",
    "parser": "Парсер: нарезка требований",
    "developer": "Эксперт-разработчик",
    "tester": "Эксперт-тестировщик",
    "security": "Эксперт по ИБ",
    "moderator": "Модератор: сведение замечаний",
    "verifier": "Верификатор цитат",
    "clarifier": "Агент уточнений: вопросы",
    "report_builder": "Сборщик отчёта",
}


def _console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        if sha.returncode != 0:
            return "нет git"
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "validator", "main.py"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return sha.stdout.strip() + (" (+ незакоммиченные изменения)" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "нет git"


def document_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line and not line.startswith("#"):
            return line[:120]
    return path.name


def _describe(node: str, update: dict) -> str:
    m = (update.get("metrics") or [{}])[-1]
    extra = []
    for key, word in (("requirements", "требований"), ("findings", "находок"), ("issues", "замечаний"),
                      ("questions", "вопросов"), ("issues_dropped", "отброшено"), ("vague_hits", "опасных слов")):
        if key in m:
            extra.append(f"{word}: {m[key]}")
    if m.get("failed"):
        extra.append("ошибка LLM — узел пропущен")
    tail = f" — {', '.join(extra)}" if extra else ""
    secs = f" ({m['seconds']} с)" if m.get("seconds") else ""
    return f"  ✓ {NODE_LABELS.get(node, node)}{secs}{tail}"


def run_graph(graph, init: dict) -> dict:
    state: dict = {}
    for mode, chunk in graph.stream(init, stream_mode=["updates", "values"]):
        if mode == "values":
            state = chunk
        else:
            for node, update in chunk.items():
                print(_describe(node, update or {}), flush=True)
    return state


def main(argv: list[str] | None = None) -> int:
    _console_utf8()
    ap = argparse.ArgumentParser(description="Статическое ревью документа с требованиями (ТЗ) и отчёт на русском.")
    ap.add_argument("--input", required=True, type=Path, help="файл требований: .pdf, .md или .txt")
    ap.add_argument("--output", required=True, type=Path, help="куда записать отчёт (.md)")
    ap.add_argument("-v", "--verbose", action="store_true", help="подробный лог")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="  [%(name)s] %(message)s")

    if not args.input.exists():
        print(f"Файл не найден: {args.input}", file=sys.stderr)
        return 2
    try:
        settings = load_settings()
        reader = get_reader(args.input)
        llm = get_llm(settings)
    except (ConfigError, ValueError) as e:
        print(f"Ошибка настройки: {e}", file=sys.stderr)
        return 2

    text = reader.read(args.input)
    started = time.time()
    try:
        source = args.input.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = args.input.as_posix()
    passport = {
        "document": source,
        "title": document_title(text, args.input),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "model": settings.model + (f", reasoning_effort={settings.reasoning_effort}" if settings.reasoning_effort else ""),
        "provider": settings.provider,
        "commit": git_commit(),
        "mode": "обычный",
        "started_at": started,
    }
    print(f"Ревью: {source} · {len(text)} символов · модель {settings.model}")

    graph = build_graph(llm)
    init = {"document": text, "source": source, "passport": passport, "findings": [], "metrics": [], "warnings": []}
    try:
        state = run_graph(graph, init)
    except Exception as e:  # noqa: BLE001 — показать причину без трейсбэка
        print(f"\nПрогон остановлен: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


    elapsed = round(time.time() - started, 1)
    data = agents_output(state)
    data["_meta"].update({"model": settings.model, "seconds": elapsed, "http_calls": getattr(llm, "calls", None),
                          "tokens_in": getattr(llm, "tokens_in", None), "tokens_out": getattr(llm, "tokens_out", None)})
    LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    get_writer(args.output).write(state["report_text"], args.output)
    for w in state.get("warnings", []):
        if not w.startswith("  "):
            print(f"  ! {w}")
    print(
        f"\nГотово за {elapsed} с · вызовов LLM: {data['_meta']['llm_calls']} (HTTP с повторами: {getattr(llm, 'calls', '?')}) · "
        f"токены: {getattr(llm, 'tokens_in', 0)} / {getattr(llm, 'tokens_out', 0)}"
    )
    print(f"Отчёт: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
