"""Помощники тестов: простой Markdown → PDF через pymupdf (Story), с кириллицей и таблицами.

Регенерация PDF-версии примера:
    python tests/helpers.py examples/requirements.md examples/requirements.pdf
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")

CSS = """
body { font-family: sans-serif; font-size: 10pt; }
h1 { font-size: 16pt; } h2 { font-size: 13pt; } h3 { font-size: 11pt; } h4 { font-size: 10pt; }
table { border-collapse: collapse; } td, th { border: 1px solid #888; padding: 2px; font-size: 8pt; }
pre { font-family: monospace; font-size: 8pt; }
"""


def _inline(text: str) -> str:
    t = html.escape(text)
    t = _BOLD.sub(r"<b>\1</b>", t)
    return _CODE.sub(r"<code>\1</code>", t)


def md_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(html.escape(lines[i]))
                i += 1
            out.append("<pre>" + "\n".join(block) + "</pre>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                    rows.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("<table>" + "".join(rows) + "</table>")
            continue
        elif m := re.match(r"(#{1,4}) (.+)", line):
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif m := re.match(r"(\*|\d+\.) (.+)", line):
            out.append(f"<p>{html.escape(m.group(1)) if m.group(1)[0].isdigit() else '•'} {_inline(m.group(2))}</p>")
        elif line == "---":
            out.append("<hr/>")
        elif line:
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    return "<body>" + "\n".join(out) + "</body>"


def md_to_pdf(md: str, path: Path) -> Path:
    import pymupdf

    story = pymupdf.Story(html=md_to_html(md), user_css=CSS)
    writer = pymupdf.DocumentWriter(str(path))
    page = pymupdf.paper_rect("a4")
    where = page + (40, 40, -40, -40)
    more = 1
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return Path(path)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    md_to_pdf(src.read_text(encoding="utf-8"), dst)
    print(f"{src} → {dst}")
