# VITO Execution Efficiency Plan (2026-03-02)

## 1. Принципы высокой продуктивности (КПД)
- Работаем **итерациями-срезами**, а не мелкими модульными правками.
- В каждой итерации: `контракты -> интеграция -> тесты -> evidence`.
- Не переключаемся на следующую волну, пока текущая не имеет стабильного regression green.
- Избегаем переделок: сначала общие контракты/флаги/схемы, потом бизнес-логика, потом UI/API.
- Минимум LLM-запросов: максимум локальных тестов, статических проверок и deterministic code paths.

## 2. Анти-конфликтный порядок изменений
1. `Contracts first`: структуры данных, статусы, policy-gates, флаги конфигурации.
2. `Core flow second`: DecisionLoop/Orchestration/Retry/Cancel логика.
3. `Persistence third`: SQLite tables/ledger/audit trail.
4. `API/UI fourth`: dashboard endpoints и представление.
5. `Tests last-mile`: unit -> integration -> critical regression bundle.

Этот порядок обязателен, чтобы не переписывать ранние правки при подключении следующих модулей.

## 3. Итерации с максимальным полезным выходом

### Iteration 1 (Wave A closure bundle) — `P0`
Цель: закрыть оставшиеся in-flight зависимости одним пакетом.

Состав работ:
- Финализировать interrupt context propagation across handoff chain.
- Укрепить auto-resume policy (loop prevention, cooldown, explicit skip/cancel events).
- Довести memory-skill linkage (единые quality fields для operator/owner).
- Финализировать self-learning long-horizon tuning + flaky decay thresholds.
- Завершить signature-key lifecycle hardening (cadence/expiry/remediation consistency).

DoD:
- Нет повторного спама после `/cancel`.
- Нет резких скачков false promotions в self-learning.
- Key lifecycle health consistently reportable via governance.

Обязательные тесты:
- `pytest -q -c /dev/null tests/test_decision_loop.py tests/test_workflow_interrupts.py tests/test_workflow_state_machine.py tests/test_workflow_threads.py`
- `pytest -q -c /dev/null tests/test_memory_skill_reports.py tests/test_self_learning.py tests/test_self_learning_thresholds.py tests/test_tooling_registry.py`

### Iteration 2 (Self-Healing v1 bundle) — `P0`
Цель: production-safe recovery pipeline без “фикса ценой деградации”.

Состав работ:
- Structured failure snapshot contract (context pack).
- Self-healer remediation pipeline with isolated execution path.
- Judge gate before apply.
- Apply/rollback policy with explicit attempt limits and audit reasons.

DoD:
- 3+ типовых инцидента проходят detect->fix->test->apply/rollback.
- Judge отсекает test-softening patch patterns.

Обязательные тесты:
- `pytest -q -c /dev/null tests/test_self_healer.py tests/test_judge_protocol.py`
- Новый пакет: `tests/test_self_healer_pipeline.py` (добавляется в рамках итерации).
- Regression sanity:
  - `pytest -q -c /dev/null tests/test_decision_loop.py tests/test_conversation_engine.py`

### Iteration 3 (Tooling discovery v1 + governance hardening) — `P1`
Цель: автономный intake инструментов с безопасным продвижением.

Состав работ:
- Discovery scheduler (`discover -> validate -> score -> approve -> promote`).
- Риск-валидация и policy-gated promotion.
- Сшивка с governance weekly report и remediation hints.

DoD:
- Кандидат проходит полный lifecycle до approved stage с журналированием.
- Нулевой обход policy gates.

Обязательные тесты:
- `pytest -q -c /dev/null tests/test_tooling_registry.py tests/test_runtime_remediation.py tests/test_governance_reporter.py`
- Новый пакет: `tests/test_tooling_discovery.py`.

### Iteration 4 (Revenue loop v1, Gumroad-first safe mode) — `P1`
Цель: один рабочий closed-loop с owner approval gate.

Состав работ:
- Research/trend ingestion -> draft generation -> quality scoring -> approval -> publish-prep -> analysis.
- Строгий evidence trail и отчёт owner-facing.

DoD:
- Минимум 1 полный dry-run цикл с артефактами и контролируемыми затратами.

Обязательные тесты:
- Интеграционные workflow tests + queue tests + critical comms tests.

## 4. Экономия токенов и стоимости (обязательный режим)
- Временный runtime режим:
  - `LLM_FORCE_GEMINI_FREE=true`
  - `LLM_ENABLED_MODELS=gemini-2.5-flash-lite`
  - платные модели отключены allow/deny политикой.
- Для диагностики/планирования используем:
  - `pytest`, `rg`, `sqlite` проверки, deterministic scripts.
- Не делаем лишних LLM-calls для задач, которые решаются кодом/правилами.
- В каждом PR/итерации публикуем:
  - список тестов,
  - время/стоимость выполнения (если есть),
  - риски и rollback note.

## 5. Правило “не останавливаться на мелочах”
- Внутри итерации останавливаемся только на:
  - blocker внешних доступов/секретов,
  - критический конфликт архитектурных контрактов.
- Локальные баги/регрессии исправляются в рамках той же итерации до green bundle.

## 6. Контроль системности
- Перед началом каждой итерации:
  - сверка с `INTEGRATION_MATRIX_2026-03-02.md`;
  - проверка, что изменения не ломают следующий шаг.
- После завершения:
  - обновление `PLAN_SKILL_EXPANSION_2026-02-25.md` progress log;
  - обновление `PLAN_PROGRESS_CHECKLIST.md` статусов.
