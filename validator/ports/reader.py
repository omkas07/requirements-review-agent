"""Порт чтения документа требований."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentReader(Protocol):
    def read(self, path: Path) -> str:
        """Текст документа как есть, без правок: верификатор сверяет с ним цитаты."""
        ...
