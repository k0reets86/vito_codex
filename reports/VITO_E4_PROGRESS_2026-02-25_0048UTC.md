# E4 Progress (2026-02-25 00:48 UTC)

## Что закрыто в этой итерации
- Добавлен guard на `Gumroad daily_limit` в `decision_loop.py`:
  - если есть недавний `platform:publish` со статусом `daily_limit`, новые попытки блокируются на 18 часов.
- Добавлен API в `ExecutionFacts`:
  - `recent_status_exists(action, status, hours)`.
- Добавлен тест:
  - `tests/test_execution_facts.py`.
- В платформенные publish-классы ранее добавлены `ExecutionFacts`-записи (etsy/kofi/wordpress/twitter/printful).

## Тесты
- `pytest -q -c /dev/null tests/test_execution_facts.py tests/test_decision_loop.py` → `31 passed`
- `pytest -q -c /dev/null tests -k "not integration_offline"` → `477 passed, 1 skipped, 67 deselected`

## Сервис
- `vito.service` после рестарта: `active (running)`

## Текущие остаточные блокеры для 10/10
1. Внешний `Telegram getUpdates Conflict` (другой polling client с тем же токеном).
2. Платформенные write-limits (Gumroad daily cap) — теперь есть cooldown/guard, но лимит остается внешним ограничением.

## Следующий шаг E4
- Зафиксировать единый production smoke-пакет для 3–5 платформ с evidence и автоматическим итоговым scorecard.
