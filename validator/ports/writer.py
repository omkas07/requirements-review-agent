"""Порт записи отчёта."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ReportWriter(Protocol):
    def write(self, text: str, path: Path) -> None:
        """Записывает готовый текст отчёта в файл (создаёт папки при необходимости)."""
        ...
