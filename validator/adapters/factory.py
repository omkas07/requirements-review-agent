"""Единственное место, где создаются конкретные адаптеры."""

from __future__ import annotations

from pathlib import Path

from validator.config import Settings, load_settings
from validator.ports.llm import LLMClient
from validator.ports.reader import DocumentReader
from validator.ports.writer import ReportWriter

READERS = {".md": "md", ".markdown": "md", ".txt": "md", ".pdf": "pdf"}


def get_llm(settings: Settings | None = None) -> LLMClient:
    s = settings or load_settings()
    args = dict(api_key=s.api_key, model=s.model, temperature=s.temperature, max_attempts=s.max_attempts, cache_dir=s.cache_dir)
    if s.provider == "openai":
        from validator.adapters.llm_openai import OpenAIClient

        return OpenAIClient(**args, reasoning_effort=s.reasoning_effort)
    from validator.adapters.llm_gemini import GeminiClient

    return GeminiClient(**args)


def get_reader(path: Path) -> DocumentReader:
    kind = READERS.get(Path(path).suffix.lower())
    if kind is None:
        raise ValueError(f"Неподдерживаемый формат {Path(path).suffix or '(без расширения)'}: нужен .pdf, .md или .txt")
    if kind == "pdf":
        from validator.adapters.reader_pdf import PdfReader

        return PdfReader()
    from validator.adapters.reader_md import MarkdownReader

    return MarkdownReader()


def get_writer(path: Path) -> ReportWriter:
    from validator.adapters.writer_markdown import MarkdownWriter

    return MarkdownWriter()
