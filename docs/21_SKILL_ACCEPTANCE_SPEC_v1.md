# VITO Skill Acceptance Spec v1

Дата: 2026-02-25

## Цель
Новый навык не считается принятым, пока не пройдён acceptance-gate.

## Статусы навыка
- `pending` — навык сохранён, но не принят.
- `accepted` — навык прошёл тестовый барьер и может использоваться как надёжный.
- `rejected` — навык отклонён после проверки.

## Acceptance gate
1. Навык записывается в `skill_registry` с `acceptance_status`.
2. Для self-improve/code/fix навыков по умолчанию ставится `pending`, если нет `tests_passed=true`.
3. После прогонов тестов (`self_updater.run_tests`) pending-навыки автоматически переводятся:
 - в `accepted` при зелёных тестах,
 - в `rejected` при красных тестах.
4. События принятия пишутся в `skill_acceptance_events`.
5. Capability packs также регистрируются как навыки со статусом `pending` и проходят тот же acceptance-gate.

## Минимальные требования для принятия
- Успешный тест-барьер (минимум: pytest pass для целевого набора).
- Evidence (отчёт/путь/идентификатор прогона) записан в acceptance событие.

## Команды наблюдения
- `/skills` — показывает acceptance статус навыков.
- `/skills_pending` — список навыков, ожидающих acceptance.

## Отчёты
- `scripts/skill_acceptance_report.py` — срез статуса acceptance.

## Принцип безопасности
Owner-facing отчёты не должны заявлять “навык надёжный/готов”, пока статус не `accepted`.
