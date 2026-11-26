"""Общее для dev-скриптов: путь к ТЗ, выбор клиента, кодировка консоли."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Консоль Windows по умолчанию cp1251 — «₸» и «→» не печатаются.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def default_input() -> Path:
    for p in (ROOT / "examples" / "requirements.md", ROOT / "dev" / "data" / "requirements.md"):
        if p.exists():
            return p
    raise FileNotFoundError("Нет examples/requirements.md и dev/data/requirements.md")


def arg_parser(desc: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--fake", action="store_true", help="фейковый LLM без сети (проверка кода)")
    ap.add_argument("--cache", action="store_true", help="кешировать ответы LLM в dev/.cache")
    ap.add_argument("--model", default=None)
    return ap


def read_document(path: Path | None) -> tuple[Path, str]:
    path = path or default_input()
    if path.suffix.lower() == ".pdf":
        import fitz  # pymupdf; боевой ридер — validator/adapters/reader_pdf.py

        with fitz.open(path) as doc:
            return path, "\n".join(page.get_text() for page in doc)
    return path, path.read_text(encoding="utf-8")


def make_llm(args):
    if args.fake:
        from dev.llm_fake import FakeLLM

        return FakeLLM()
    from dev.llm_dev import DevGeminiClient

    return DevGeminiClient(model=args.model, use_cache=args.cache)


def quote_stats(quotes: list[str], document: str) -> tuple[int, int, list[str]]:
    from validator.agents.quotes import normalize, quote_in_document

    ndoc = normalize(document)
    bad = [q for q in quotes if not quote_in_document(q, ndoc)]
    return len(quotes) - len(bad), len(quotes), bad
