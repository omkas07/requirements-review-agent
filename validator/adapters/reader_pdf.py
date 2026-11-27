"""Чтение PDF через pymupdf: текст страниц по порядку."""

from __future__ import annotations

from pathlib import Path


class PdfReader:
    def read(self, path: Path) -> str:
        import pymupdf

        with pymupdf.open(Path(path)) as doc:
            if doc.needs_pass:
                raise ValueError(f"PDF защищён паролем: {path}")
            pages = [page.get_text("text", sort=True).rstrip() for page in doc]
        text = "\n\n".join(p for p in pages if p)
        if not text.strip():
            raise ValueError(f"В PDF нет текстового слоя (скан?): {path}")
        return text
