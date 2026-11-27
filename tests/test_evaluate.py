"""eval/evaluate.py: сопоставление по словам и через LLM (фейковая модель)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import evaluate as ev  # noqa: E402

RESULT = json.loads((ROOT / "eval" / "fake_result.json").read_text(encoding="utf-8"))
GOLDEN = {
    "items": [
        {"id": 1, "title": "Месяц по дате покупки ↔ февральский счётчик", "keywords": [["феврал"], ["дат"]]},
        {"id": 2, "title": "Сохранение через GET", "keywords": [["get", "-g"], ["post", "put"]]},
        {"id": 3, "title": "Нет схемы отката", "keywords": [["откат"]]},
    ],
    "questions": [{"id": 1, "title": "Месяц на стыке", "keywords": [["месяц"]]}],
}


def test_keywords():
    s = ev.evaluate(RESULT, GOLDEN)
    assert (s["found"], s["total"], s["questions_found"], s["method"]) == (2, 3, 1, "keywords")


class FakeLLM:
    model = "fake"

    def ask_json(self, prompt, schema):
        assert "R-02/1" in prompt and "В-1" in prompt
        return schema(
            items=[ev.ItemMatch(item_id=1, refs=["R-02/1", "R-99/1"], reason="то же"),
                   ev.ItemMatch(item_id=3, refs=["SET:Полнота"], reason="щедро")],
            questions=[ev.ItemMatch(item_id=1, refs=["В-1"], reason="да")],
        )


def test_llm_mode_filters_unknown_refs():
    s = ev.evaluate(RESULT, GOLDEN, llm=FakeLLM())
    found = {f["id"]: f["hits"] for f in s["found_items"]}
    assert found == {1: ["R-02/1"], 3: ["SET:Полнота"]} and s["method"] == "llm"
    assert s["questions_found"] == 1 and [m["id"] for m in s["missed_items"]] == [2]
