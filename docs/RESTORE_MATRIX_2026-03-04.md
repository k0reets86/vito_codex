# Restore Matrix After Rollback (2026-03-04)

Источник проверки:
- git-коммиты восстановления: `05c0969`, `d10dcc1`, `a37717e`, `8bcb5f0`, `bb07cf2`, `16297ee`
- текущее состояние кода + тесты
- жалобы владельца из диалога/логов

## Итог (объективно)

- Полностью восстановлено: `10`
- Частично восстановлено: `7`
- Не восстановлено / требует доработки: `6`
- Всего пунктов матрицы: `23`
- Фактический прогресс восстановления: `43.5%` (только `full`)
- С учётом `partial`: `73.9%`

Важно: прежняя оценка `88%` была завышена.

## Матрица

| # | Область | Ожидалось до отката | Текущее состояние | Статус | Доказательство |
|---|---|---|---|---|---|
| 1 | Telegram menu/help | Разделы help/daily/rare/system отдельными командами | Реализовано | full | `comms_agent.py` (`_render_help`, `_cmd_help_*`), `a37717e`, `tests/test_comms_agent.py` |
| 2 | Inline auth flow | Кнопки `Войти` + `Я вошел` + `Отмена` для сервисов | Реализовано | full | `comms_agent.py` (`_start_service_auth_flow`, `_handle_callback`), `8bcb5f0` |
| 3 | Amazon auth fallback | При фейле авто-проверки не ломаться, фиксировать ручной вход | Реализовано | full | `comms_agent.py`, `16297ee`, тесты auth_done |
| 4 | Повторный вход Amazon | Не гонять повторный логин при свежем подтверждении | Реализовано | full | `_handle_kdp_login_flow` + тесты в `tests/test_comms_agent.py` |
| 5 | Context status | После `зайди на X` команда `статус` относится к X | Реализовано | full | `_detect_contextual_service_status_request` + тесты |
| 6 | Context inventory | `проверь товары` в контексте сервиса не должен идти в niche research | Реализовано (новый фикс) | full | `_detect_contextual_service_inventory_request`, `_format_service_inventory_snapshot`, тесты |
| 7 | Gemini free mode | Переключатель free/prod + Gemini-first для тестов | Реализовано | full | `_apply_llm_mode`, `config/settings.py`, `bb07cf2` |
| 8 | URL-context research | Пайплайн URL-context с источниками в ответе | Реализовано | full | `modules/research_url_context.py`, `bb07cf2`, `tests/test_research_url_context.py` |
| 9 | Chroma fallback | Не падать на mismatch dimensions | Реализовано | full | `memory/memory_manager.py`, `16297ee` |
| 10 | Browser runtime stability | Падения Chromium в constrained env | Усилено (единый constrained mode) | partial | `BROWSER_CONSTRAINED_MODE`, browser patches, `tests/test_browser_agent.py` |
| 11 | Browser diagnostics | Скрин/HTML при браузерных сбоях | Реализовано | full | `agents/browser_agent.py` (`_capture_failure_artifacts`) |
| 12 | Amazon live-check accuracy | `статус аккаунта` должен быть live, не по шаблону | Реализовано | full | `_format_service_auth_status_live` |
| 13 | “Живое” общение в TG | Минимум техспама, дружелюбный стиль | Частично | partial | есть `humanize` и suppress, но в ряде веток ещё техтекст проскакивает |
| 14 | NLU к корявому вводу | Уверенное понимание опечаток/коротких ответов/сленга | Частично | partial | часть алиасов и контекста есть, полнота ниже цели |
| 15 | Мультиязычность (RU/EN mix) | Стабильная интерпретация mixed-команд | Частично | partial | работает в базовых кейсах, нет системного покрытия |
| 16 | Статусы goals/tasks | Согласованность между `/status`, `/goals`, `/tasks` | Частично | partial | улучшения есть, но были расхождения по жалобам, нужен дополнительный аудит |
| 17 | Финансовые цифры | Единая математика в статусе и по агентам | Не закрыто | missing | конфликт “daily spend vs per-agent total” требует нормализации |
| 18 | Долгие “в работе” задачи | Понятно, выполняется реально или зависло | Частично | partial | нет полного SLA/таймаут-объяснения в owner-ответе |
| 19 | Качество research output | Глубокий анализ, сравнение, оценки/баллы, actionable выводы | Не закрыто | missing | текущие ответы часто короткие/шаблонные по жалобам |
| 20 | Автопубликация по score | Пороговая логика (например, >80) + публикация | Не закрыто | missing | системной реализации “rubric->publish gate” нет |
| 21 | Единый cross-service auth UX | Одинаковый цикл входа/подтверждения для всех платформ | Частично | partial | каркас есть, но deep verification покрыт не для всех |
| 22 | Память владельца в чате | Удержание личного контекста и предпочтений без “забывания” | Частично | partial | модель prefs есть, поведенчески нестабильно |
| 23 | Автономность без лишних подтверждений | Меньше стопов на безопасных действиях | Частично | partial | `AUTONOMY_MAX_MODE` улучшен, но не все ветки дожаты |

## Технический вывод

Основной провал был не в полном отсутствии фич, а в несшитости контуров:
- часть маршрутов шла в правильный flow (auth/context),
- часть в fallback (goal/research),
- из-за этого владелец видел “хаотичное” поведение.

## Приоритет доработки (пакетами)

### Package A (критично, сразу)
1. Нормализация intent-router для owner-команд аккаунтов (status/inventory/actions) с жёстким приоритетом контекста сервиса.
2. Финансовая нормализация: единый источник правды для `/status` и агентных расходов.
3. Anti-stuck слой: явный статус задач `running/stalled/timeout` и человеческое объяснение.

### Package B
1. Quality-gate для research: обязательная структура ответа + score rubric + рекомендации.
2. Rule-based autopublish gate (по score и safety policy), пока в controlled mode.

### Package C
1. Дошлифовка диалога: убрать остаточный техспам в owner-чате.
2. Расширение устойчивости NLU на короткие/корявые/мультиязычные команды.

## Проверка после каждого пакета

- Обязательные тесты:
  - `pytest -q -c /dev/null tests/test_comms_agent.py tests/test_conversation_engine.py tests/test_browser_agent.py`
- Telegram smoke:
  - `зайди на X` -> `я вошел` -> `статус аккаунта` -> `проверь товары`
  - результат должен быть по сервису X, без ухода в ниши/шаблоны.
