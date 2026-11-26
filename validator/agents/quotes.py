"""Проверка цитат в агентах (без LLM).

Нужна агентам до верификатора: парсер упорядочивает требования по позиции цитаты
в документе, dev-скрипты считают долю цитат-подстрок. Окончательная фильтрация
замечаний — в validator/agents/verifier.py (тиммейт 1).
"""

from __future__ import annotations

import re

_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'"})
_DASHES = str.maketrans({"—": "-", "–": "-", "−": "-", "ё": "е", "Ё": "Е"})
_MARKUP = re.compile(r"[*_`|#>]+")
_SPACES = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"…|\.\.\.")


def normalize(text: str) -> str:
    text = text.translate(_QUOTES).translate(_DASHES)
    text = _MARKUP.sub(" ", text)
    text = _SPACES.sub(" ", text)
    return text.strip().lower()


def quote_fragments(quote: str) -> list[str]:
    """Цитата с «…» внутри — несколько фрагментов; каждый должен быть в документе."""
    parts = [normalize(p).strip(' "\'.,;:') for p in _ELLIPSIS.split(quote)]
    return [p for p in parts if p]


def quote_position(quote: str, normalized_doc: str) -> int | None:
    """Позиция первого фрагмента цитаты в нормализованном документе или None."""
    frags = quote_fragments(quote)
    if not frags:
        return None
    pos = 0
    first = None
    for frag in frags:
        idx = normalized_doc.find(frag, pos)
        if idx < 0:
            return None
        if first is None:
            first = idx
        pos = idx + len(frag)
    return first


def quote_in_document(quote: str, normalized_doc: str) -> bool:
    return quote_position(quote, normalized_doc) is not None
