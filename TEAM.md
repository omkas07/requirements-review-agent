# Инструкция для команды

Общий контекст, архитектура и контракт данных — в [CONTEXT.md](CONTEXT.md), статус задач — в [TASK.md](TASK.md).
Этот файл — что сделать, чтобы начать работу, и как стыковаться с агентами.

## 1. Подготовка (один раз)

```bash
git checkout main && git pull
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

- Python 3.11. Пакеты ставим только в `.venv`, не в системный Python.
- Новая библиотека → добавить строку в `requirements.txt` в том же коммите.
- Ключ: бесплатный на [aistudio.google.com](https://aistudio.google.com/) → Get API key.
  Положить в `.env` в корне строкой `GEMINI_API_KEY=...`. `.env` уже в `.gitignore`, не коммитить.
- Модель по умолчанию — `gemini-3.8-flash` (stable, бесплатный тариф). `gemini-1.5-flash`
  из примера организаторов устарел.

## 2. Как работаем в git

- Своя ветка от `main` → PR в `main`. Прямо в `main` не коммитим.
- Чужие файлы не правим — пишем владельцу (владельцы — в дереве в CONTEXT.md).
- Поля в `validator/domain/models.py` меняются только через Омара.
- Свои строки в `TASK.md` обновляем в том же коммите, что и код.

## 3. Что уже есть

| Что | Где |
|---|---|
| Контракт данных и выход LLM-агентов | `validator/domain/models.py` |
| Критерии ISO/IEEE, финтех-чек-лист, «опасные слова» | `validator/domain/criteria.py` |
| Парсер, 3 эксперта, модератор, агент уточнений | `validator/agents/` |
| Граф LangGraph | `validator/agents/graph.py` |
| Промпты | `validator/prompts/*.md` |
| ТЗ организаторов | `examples/requirements.md` |

Граф проверен на фейковом LLM. На реальном Gemini пока не запускался — нет ключа.

Временно, пока нет `main.py` и адаптеров, агентов можно запустить так:

```bash
python dev/run_graph.py --fake    # без ключа: проверка, что всё проходит
python dev/run_graph.py --cache   # реальный Gemini → reports/agents_output.json
```

Папка `dev/` временная, перед сдачей её удалим.

## 4. Тиммейт 1 — каркас

### Порт LLM — `validator/ports/llm.py`

Агенты вызывают только этот метод:

```python
from typing import Protocol, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMClient(Protocol):
    model: str                                   # имя модели — для паспорта отчёта
    def ask_json(self, prompt: str, schema: type[T]) -> T: ...
```

Требования к адаптерам (`llm_gemini.py`, `llm_openai.py`):

- Возвращают валидный экземпляр `schema`, а не dict и не строку.
- Структурированный вывод по `schema.model_json_schema()`, `temperature=0`.
- Невалидный JSON (`pydantic.ValidationError`) → повтор запроса.
- 429 и 5xx → повтор с паузой; у Gemini в ошибке 429 есть `retryDelay` — ждать столько.
- Gemini: `response_mime_type="application/json"` + `response_json_schema=...`.
  Рабочий пример со всем этим — `dev/llm_dev.py`, можно взять за основу.
- OpenAI: проверить, что схемы с полями по умолчанию (`= []`, `= None`) проходят strict-режим;
  если нет — `json_object` + `schema.model_validate_json(...)`.

После мержа порта Омар удалит `dev/llm_port_stub.py`. Агенты импортируют порт только для
аннотаций типов, так что больше ничего менять не нужно.

### Ридеры

`read(path) -> str` — текст документа как есть, без правок: верификатор сверяет цитаты
с этим текстом. PDF — через `pymupdf` (`import fitz`).

### Верификатор — `validator/agents/verifier.py`

Граф подключит его сам между модератором и агентом уточнений, если модуль экспортирует `node`:

```python
from validator.agents.state import ReviewState
from validator.agents.quotes import normalize, quote_in_document  # можно использовать

def node(state: ReviewState) -> dict:
    document = state["document"]
    moderated = state["moderated"]          # ModeratorOutput
    ...                                     # выбросить Issue, чьей quote нет в документе
    return {"moderated": new_moderated, "warnings": ["Верификатор: выброшено N замечаний: ..."]}
```

- Нормализация в `quotes.normalize`: регистр, пробелы, кавычки «» → ", тире, ё → е,
  разметка `**` `` ` `` `|` `#`. Цитата с «…» делится на фрагменты, каждый ищется по порядку.
- Если у требования выброшены все замечания — поставить `status="ok"` и `suggestion=None`.
- `warnings` складываются (reducer), поэтому возвращаем только новые строки.

### main.py

```python
from validator.agents.graph import run_review

text = reader.read(args.input)
llm = get_llm()                                    # adapters/factory.py по LLM_PROVIDER
state = run_review(llm, text, source=str(args.input), passport={
    "document": str(args.input), "date": ..., "model": llm.model,
    "commit": ...,                                 # git rev-parse --short HEAD
    "mode": "interactive" if args.interactive else "обычный",
})
writer.write(state["report_text"], args.output)
```

Прогресс для CLI — `state["metrics"]` (узел, вызовы LLM, секунды), предупреждения —
`state["warnings"]`. Один прогон — 6 вызовов LLM: парсер, 3 эксперта, модератор, уточнения.

## 5. Тиммейт 2 — отчёт и качество

### Вход сборщика

Пока сборщика нет, Омар выкладывает выход агентов в `reports/agents_output.json`:

```json
{
  "requirements": [ Requirement, ... ],   // в порядке документа, R-01, R-02...
  "set_checks":   [ SetCheck, ... ],      // всегда 8, в порядке: Полнота, Непротиворечивость,
                                          // Выполнимость, Понятность, Валидируемость,
                                          // Ранжированность, Модифицируемость, Трассируемость
  "strengths":    [ "...«цитата»...", ... ],
  "questions":    [ Question, ... ],      // В-1, В-2... — самые важные первыми
  "_meta":        { ... }                 // служебное: вызовы LLM, время, warnings
}
```

Загрузка: `ModeratorOutput.model_validate(data)` и `[Question.model_validate(q) for q in data["questions"]]`;
`_meta` pydantic проигнорирует.

Что важно для шаблона:

- `status`: `ok` → 🟢, `needs_clarification` → 🟡, `blocking` → 🔴. У `ok` замечаний нет.
- `Issue.impact` заполнен только у важных замечаний → блок «⚠️ Если не исправить».
- `Issue.question_id` → ссылка «❓ Вопрос В-N».
- `Question.blocks` не `null` → вопрос блокирующий (🔴, учитывается в вердикте `scoring.py`).
- `Question.related_reqs` — ID требований для строки «Касается».
- Якоря только ASCII: `R-05` → `r-05`; `В-1` (В кириллицей) → `q-1` по номеру.

### Сборщик — `validator/agents/report_builder.py`

Граф подключит его последним узлом, если модуль экспортирует `node`:

```python
def node(state: ReviewState) -> dict:
    moderated = state["moderated"]           # ModeratorOutput
    questions = state.get("questions", [])   # list[Question]
    passport = state.get("passport", {})     # заполняет main.py
    text = render(...)                       # Jinja2, сортировка, scoring
    return {"report_text": text}
```

В файл сборщик не пишет — это делает `main.py` через `ReportWriter`.

### Оценка

`eval/evaluate.py` читает `reports/agents_output.json`: замечания — в `requirements[].issues[]`
(`criterion`, `text`, `quote`), вопросы — в `questions[]`. После каждого прогона — Омару,
что пропущено, что выдумано и где резкий тон (GitHub Issues: `agent-miss`, `false-positive`).

## 6. Перед сдачей

- `python main.py --input examples/requirements.md --output reports/report.md` проходит
  с нуля по README.
- Удалить `dev/`.
- `reports/report.md` — только из прогона агента, руками не правим.
