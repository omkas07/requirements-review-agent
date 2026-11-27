"""Сквозной запуск CLI на фейковом LLM: main.py → граф → верификатор → сборщик → файл."""

import json
from pathlib import Path

import main
from tests.test_agents import FakeLLM
from validator.config import ConfigError, Settings, load_settings

ROOT = Path(__file__).resolve().parent.parent


def test_cli_end_to_end(tmp_path, monkeypatch, capsys):
    from tests import test_agents

    doc = tmp_path / "req.md"
    doc.write_text(test_agents.DOC, encoding="utf-8")
    monkeypatch.setattr(main, "load_settings", lambda: Settings(provider="gemini", api_key="x", model="fake"))
    monkeypatch.setattr(main, "get_llm", lambda s: FakeLLM())
    out, js = tmp_path / "r" / "report.md", tmp_path / "last_run.json"
    monkeypatch.setattr(main, "LAST_RUN", js)

    assert main.main(["--input", str(doc), "--output", str(out)]) == 0
    report = out.read_text(encoding="utf-8")
    assert "## 1. Паспорт прогона" in report and "| Модель | fake (gemini) |" in report
    assert "| Вызовов LLM | 6 |" in report
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["questions"][0]["q_id"] == "В-1" and data["_meta"]["llm_calls"] == 6
    assert "✓ Верификатор цитат" in capsys.readouterr().out
    assert sorted(p.name for p in out.parent.iterdir()) == ["report.md"]  # в папке отчёта — только отчёт


def test_removed_flags_are_rejected(tmp_path):
    import pytest

    for flag in ("--interactive", "--json"):
        with pytest.raises(SystemExit):
            main.main(["--input", "x.md", "--output", str(tmp_path / "r.md"), flag])


def test_cli_missing_file_and_key(tmp_path, monkeypatch, capsys):
    assert main.main(["--input", str(tmp_path / "nope.md"), "--output", str(tmp_path / "r.md")]) == 2
    doc = tmp_path / "a.md"
    doc.write_text("x", encoding="utf-8")

    def no_key():
        raise ConfigError("Нет ключа LLM")

    monkeypatch.setattr(main, "load_settings", no_key)
    assert main.main(["--input", str(doc), "--output", str(tmp_path / "r.md")]) == 2
    assert "Нет ключа LLM" in capsys.readouterr().err


def test_settings_require_key(tmp_path, monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_PROVIDER", "GEMINI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    try:
        load_settings(env)
    except ConfigError as e:
        assert "aistudio.google.com" in str(e)
    else:
        raise AssertionError("ожидалась ConfigError")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # первый load_dotenv записал пустой ключ
    env.write_text("GEMINI_API_KEY=abc\n", encoding="utf-8")
    s = load_settings(env)
    assert (s.provider, s.model, s.temperature) == ("gemini", "gemini-3.8-flash", 0.0)
