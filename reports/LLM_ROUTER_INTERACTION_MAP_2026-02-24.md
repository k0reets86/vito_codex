# Карта взаимодействий LLM Router (VITO)
Дата: 2026-02-24

## 1) Актуальные роли моделей
- `Gemini 2.5 Flash Lite` (`gemini-flash`): рутина, классификация, суммаризация, недорогие ответы.
- `Claude Sonnet 4.6` (`claude-sonnet`): качественные коммерческие тексты и карточки товаров.
- `OpenAI o3` (`gpt-o3`): кодинг, рефакторинг, self-heal/починка.
- `Perplexity Sonar Pro` (`perplexity`): исследования с источниками.
- `Claude Opus 4.6` (`claude-opus`): стратегические задачи высокого уровня.
- `GPT-5` (`gpt-5`): стратегический fallback и критик в brainstorm-цикле.
- `OpenRouter`: аварийный fallback, когда direct API недоступен.

## 2) TaskType -> модель (приоритет + fallback)
- `ROUTINE`: Gemini -> GPT-4o-mini -> Haiku
- `CONTENT`: Sonnet -> Haiku -> Gemini
- `CODE`: o3 -> Sonnet -> GPT-5
- `RESEARCH`: Perplexity -> Gemini -> Sonnet
- `STRATEGY`: Opus -> GPT-5 -> Sonnet
- `SELF_HEAL`: o3 -> Sonnet -> GPT-5

## 3) Порядок выполнения запроса (routing pipeline)
1. Входящий запрос получает `TaskType` (через intent/capability/classify_step).
2. `LLMRouter.select_model(...)` выбирает первую разрешённую модель по карте.
3. Проверка кэша (`llm_cache`) для `ROUTINE/CONTENT`.
4. Проверка бюджета (`DAILY_LIMIT_USD`) + финансовый guard через `FinancialController`.
5. Если оценка > $1 — owner approval через `CommsAgent`.
6. Вызов провайдера direct API.
7. При недоступности direct API — fallback в OpenRouter.
8. При ошибках/перегрузке (429/5xx/overloaded) — retry с backoff и переход к следующей модели в цепочке.
9. Успех: запись расходов в `spend_log`, bridge в `FinancialController`, запись кэша.
10. Неуспех всех моделей: `all_models_failed`.

## 4) Где в системе это применяется
- `conversation_engine.py`: intent/диалог, в основном `TaskType.ROUTINE`.
- `decision_loop.py`: классификация шага (`RESEARCH/STRATEGY/CODE/CONTENT/ROUTINE`) и fallback через LLM.
- `agents/vito_core.py`: orchestration fallback и `_map_to_task_type(...)`.
- `main.py`: weekly planner и системные summary вызовы.
- `judge_protocol.py`: стратегический мультиролевой brainstorm.

## 5) Brainstorm (стратегический контур)
Используется для стратегических задач (по команде или триггерам планирования):
1. Sonnet — генерация идеи.
2. Perplexity — исследование и факты.
3. GPT-5 — критика/альтернативы.
4. Opus — стратегическая глубина.
5. Perplexity — факт-чек спорных тезисов.
6. Opus — финальный синтез плана.

## 6) Изменения, внесённые сейчас
- Уточнены роли моделей под твои правила:
  - качественные тексты товаров => Sonnet first;
  - кодинг/починка/самолечение => o3 first;
  - стратегический контур сохранён через Brainstorm + Strategy on Opus.
- Добавлены fallback-цепочки по всем `TaskType` (раньше почти везде была 1 модель).
- Обновлён тест `tests/test_llm_router.py` под актуальный `claude-opus-4-6`.

## 7) Проверка
- Тесты: `pytest -q -c /dev/null tests/test_llm_router.py`
- Результат: `21 passed`.

## 8) Файлы, изменённые в этой итерации
- `llm_router.py`
- `tests/test_llm_router.py`

