from pathlib import Path

import pytest

from tests.helpers import md_to_pdf
from validator.adapters.factory import get_reader, get_writer
from validator.adapters.reader_md import MarkdownReader
from validator.adapters.reader_pdf import PdfReader
from validator.agents.quotes import normalize, quote_in_document

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "requirements.md"

QUOTES = [
    "Месяц определяется по дате совершения покупки в Алматы.",
    "При ошибке ввода сообщение появляется под полем.",
    "Покупка 31 января в 23:58 на 4 000 ₸",
    "Для чужой карты возвращается 404, как и для отсутствующей карты.",
    "Если результат 400, 401 и далее — неуспешный.",
]


def test_markdown_reader_utf8_and_cp1251(tmp_path):
    (tmp_path / "a.md").write_text("Порог ₸", encoding="utf-8")
    (tmp_path / "b.md").write_bytes("Порог".encode("cp1251"))
    assert MarkdownReader().read(tmp_path / "a.md") == "Порог ₸"
    assert MarkdownReader().read(tmp_path / "b.md") == "Порог"


def test_pdf_reader_keeps_text_for_quotes(tmp_path):
    pdf = md_to_pdf(EXAMPLE.read_text(encoding="utf-8"), tmp_path / "req.pdf")
    text = PdfReader().read(pdf)
    ndoc = normalize(text)
    assert all(quote_in_document(q, ndoc) for q in QUOTES)


def test_pdf_example_in_repo_is_readable():
    pdf = ROOT / "examples" / "requirements.pdf"
    if not pdf.exists():
        pytest.skip("нет examples/requirements.pdf")
    assert "Уведомление о расходах по карте" in PdfReader().read(pdf)


def test_pdf_without_text_layer(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "empty.pdf")
    with pytest.raises(ValueError, match="текстового слоя"):
        PdfReader().read(tmp_path / "empty.pdf")


def test_factory_picks_reader_by_extension(tmp_path):
    assert isinstance(get_reader(Path("x.PDF")), PdfReader)
    assert isinstance(get_reader(Path("x.md")), MarkdownReader)
    with pytest.raises(ValueError, match="Неподдерживаемый формат"):
        get_reader(Path("x.docx"))


def test_writer_creates_folders(tmp_path):
    out = tmp_path / "deep" / "report.md"
    get_writer(out).write("# Отчёт", out)
    assert out.read_text(encoding="utf-8") == "# Отчёт\n"
