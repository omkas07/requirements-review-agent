"""Запись отчёта в Markdown-файл."""

from __future__ import annotations

from pathlib import Path


class MarkdownWriter:
    def write(self, text: str, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
