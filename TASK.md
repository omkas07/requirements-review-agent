\# TASKS — что сделано и что нет



Легенда: \[ ] не начато · \[\~] в работе · \[x] готово

Обновляй свои строки в том же коммите, что и код.

Баги и находки из eval — в GitHub Issues (метки `agent-miss`, `false-positive`, `bug`),

сюда не дублируем.



\## Общее (все вместе, утро 26.11)

\- \[ ] Репозиторий, ветки `agents` (Омар), `core` (Рамазан), `report` (Адильхан)

\- \[ ] `validator/domain/models.py` — контракт

\- \[ ] `eval/fake\_result.json` — заглушка (4 требования, 2 вопроса, 3 проверки набора)



\## Омар — агенты (`agents/`, `prompts/`, `domain/models.py`, `domain/criteria.py`)

\- \[ ] `models.py` — промежуточные модели (ParserOutput, Finding, ExpertOutput, ModeratorOutput, ClarifierOutput)

\- \[ ] `criteria.py` — критерии, финтех-чек-лист, `find\_vague\_words`

\- \[ ] `state.py`, `prompting.py` (string.Template)

\- \[ ] Промпты: `tone.md`, `parser.md`, `expert\_base.md` + 3 роли, `moderator.md`, `clarifier.md`

\- \[ ] Парсер (проверено: порядок документа, цитаты — подстроки)

\- \[ ] Эксперт: разработчик

\- \[ ] Эксперт: тестировщик

\- \[ ] Эксперт: безопасник

\- \[ ] Модератор (статус + impact + set\_checks + strengths)

\- \[ ] Агент уточнений (вопросы + question\_id)

\- \[ ] `graph.py` — сборка LangGraph, `build\_graph(llm)`

\- \[ ] `reports/agents\_output.json` — первый полный выход агентов для Адильхана

\- \[ ] Улучшение промптов по результатам eval



\## Рамазан — каркас (`main.py`, `config.py`, `ports/`, `adapters/`, `verifier.py`, README)

\- \[ ] Структура папок, `examples/requirements.md`

\- \[ ] Порты (Protocol): `LLMClient`, `DocumentReader`, `ReportWriter`

\- \[ ] Чтение Markdown

\- \[ ] Чтение PDF (проверено на PDF-версии ТЗ)

\- \[ ] Клиент Gemini (structured output, temperature=0, ретраи на 429)

\- \[ ] Клиент OpenAI

\- \[ ] `config.py` + `adapters/factory.py` (выбор провайдера по `LLM\_PROVIDER`)

\- \[ ] CLI с прогрессом

\- \[ ] Верификатор цитат + тесты

\- \[ ] Паспорт прогона (дата, модель, коммит, режим)

\- \[ ] `.env.example`, `requirements.txt`, `.gitignore`

\- \[ ] README

\- \[ ] Проверка запуска с нуля по README

\- \[ ] Демо-видео



\## Адильхан — отчёт и качество (`templates/`, `scoring.py`, `report\_builder.py`, `eval/`)

\- \[ ] Шаблон `report.md.j2` по заглушке

\- \[ ] Якоря и двусторонние ссылки (проверено на GitHub)

\- \[ ] `report\_builder.py` — сортировка 🔴→🟡→🟢, порядок разделов, рендер

\- \[ ] `scoring.py` (готовность, сводка) + тесты

\- \[ ] `eval/golden.json` — эталон находок + ожидаемые вопросы

\- \[ ] `eval/evaluate.py` — найдено X из Y, лишних Z, вопросов задано N из M

\- \[ ] `examples/requirements\_2.md` — второе ТЗ + его эталон

\- \[ ] Обратная связь Омару через Issues после каждого прогона

\- \[ ] Замеры: ручное ревью vs агент

\- \[ ] Слайды



\## Контрольные точки

\- \[ ] 26.11 вечер — первый сквозной прогон на реальном ТЗ

\- \[ ] 27.11 18:00 — финальный прогон, коммит `reports/report.md`

\- \[ ] 27.11 21:00 — сдача



\## Блокеры и вопросы

<!-- Пиши сюда, если что-то мешает: дата, кто, что -->

