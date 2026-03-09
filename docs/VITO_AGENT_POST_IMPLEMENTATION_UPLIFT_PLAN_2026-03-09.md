# VITO Agent Post-Implementation Uplift Plan — 2026-03-09

Статус: `MANDATORY_NEXT`

Основание:
- `reports/VITO_AGENT_BENCHMARK_MATRIX_2026-03-09_2333UTC.json`
- `reports/VITO_AGENT_POST_IMPLEMENTATION_REVIEW_2026-03-09.md`

## Цель

Поднять агентный слой после завершения `Phase I-N` с текущих `6.89/10` до устойчивого диапазона `8.5+/10`.

## Пакет 1 — Recovery Depth Uplift

Приоритет: `P0`

Цель:
- поднять `recovery_quality` у всех семейств, начиная с самых слабых.

Сделать:
1. Для каждого агента добавить типовые failure signatures.
2. Для каждого агента добавить `retry / reroute / escalate / block` runbook decisions.
3. Привязать recovery paths к `AgentEventBus` и `failure_substrate`.
4. Добавить recovery-aware benchmark scenarios.

Агенты первого приоритета:
- `browser_agent`
- `translation_agent`
- `economics_agent`
- `account_manager`
- `legal_agent`

Критерий:
- каждый из пяти получает минимум `+1.2` к `recovery_quality`

## Пакет 2 — Data/Tool Depth Uplift

Приоритет: `P0`

Цель:
- убрать остаточную "умную оболочку" и сделать data/tool path primary.

Сделать:
1. `translation_agent`
   - richer cache/provider routing
   - quality consistency checks
2. `economics_agent`
   - real competitor / margin / pricing signal fusion
3. `legal_agent`
   - executable TOS/policy packs
4. `account_manager`
   - stronger auth state model
   - platform-specific auth remediation packs
5. `partnership_agent`
   - richer candidate search + scoring inputs

Критерий:
- каждый агент из списка должен получить `data_usage >= 7.0`

## Пакет 3 — Outcome-Changing Collaboration

Приоритет: `P1`

Цель:
- handoff должен менять результат, а не только логироваться.

Сделать:
1. Для каждого workflow задать обязательные collaboration assertions.
2. Если обязательный support/verify agent не сработал, итоговый результат считается degraded.
3. Добавить cross-agent benchmark tasks с проверкой влияния handoff на outcome.

Критерий:
- `collaboration_quality` у семейств `content_growth` и `governance_resilience` >= `7.5`

## Пакет 4 — Commerce Execution Hardening

Приоритет: `P1`

Цель:
- поднять `commerce_execution` выше `8.0`

Сделать:
1. `browser_agent` recovery packs
2. `account_manager` auth remediation packs
3. `ecommerce_agent` deeper platform rule/runbook execution
4. `publisher_agent` richer evidence + retry/escalation behavior

Критерий:
- `commerce_execution.total_score >= 8.0`

## Пакет 5 — Family Re-Benchmark and Kill List

Приоритет: `P1`

Сделать:
1. После каждого пакета прогонять benchmark matrix.
2. Вести kill-list агентов ниже `7.0`.
3. Пока agent/family ниже порога, следующий uplift пакет обязателен.

## Запреты

- Нельзя снова расширять число агентов вместо углубления behavior.
- Нельзя считать "structured output" равным зрелости.
- Нельзя переходить к новым красивым подсистемам, пока `browser_agent`, `account_manager`, `translation_agent`, `economics_agent`, `legal_agent` не перестанут быть основными тормозами.
