"""Чтение Markdown / текстовых файлов."""

from __future__ import annotations

from pathlib import Path


class MarkdownReader:
    def read(self, path: Path) -> str:
        raw = Path(path).read_bytes()
        for enc in ("utf-8-sig", "cp1251"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
