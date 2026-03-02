# VITO Rebaseline Detailed (2026-03-02)
Источник нового ТЗ: `docs/import/google_doc_1Vw0_vBXSWGo4UBiniEQPBs1GrIPrPCEEte8sE2KeOvs.txt`

## 1. Детальное сравнение: текущее состояние vs целевая архитектура

### 1.1 Orchestration
- Статус: `DONE` (база), `IN_PROGRESS` (политики автопродолжения).
- Реализовано: durable workflow sessions, step-state, interrupts, pause/resume/cancel/reset, dashboard-видимость.
- Что не закрыто: полная сквозная передача interrupt context во все handoff-цепочки и финальная стабилизация auto-resume policy.
- Риск: циклы автовозобновления и повторные wake-up после owner-cancel.
- Критерий закрытия: нет повторного auto-resume после `/cancel` до явного `/resume`; у каждого handoff есть audit-поля interrupt metadata.

### 1.2 Memory Architecture
- Статус: `DONE` (основа), `IN_PROGRESS` (quality linkage depth).
- Реализовано: memory blocks, retention classes, TTL (`expires_at`), short->long consolidation, weekly memory report.
- Что не закрыто: более глубокая связь memory quality <-> фактическая успешность skill-применения по горизонту 30-90 дней.
- Риск: накопление слабых/устаревших блоков и деградация при retrieval.
- Критерий закрытия: регулярный quality score per skill с порогами и remediation.

### 1.3 Self-Learning / Self-Evolution
- Статус: `IN_PROGRESS`.
- Реализовано: reflection loop, candidate scoring/readiness, adaptive thresholds per family, test-jobs, flaky policy.
- Что не закрыто: long-horizon outcome tuning, аккуратный decay historical flaky history, единые promotion gates на длинном окне.
- Риск: ложные autopromotion и нестабильные навыки.
- Критерий закрытия: пороги калибруются по outcomes и flaky decay автоматически, без роста regressions.

### 1.4 Tooling Standards / Skill Discovery
- Статус: `PARTIAL`.
- Реализовано: MCP/OpenAPI registry, schema validation, signed/versioned contracts, stage promotion/rollback, governance/reporting.
- Что не закрыто: автономный discovery loop (сканирование источников, candidate intake, approval-gated promotion в runtime).
- Риск: ручной bottleneck обновлений инструментария.
- Критерий закрытия: end-to-end intake pipeline `discover -> validate -> score -> approve -> promote`.

### 1.5 Self-Healing (Pipeline Doctor + Judge)
- Статус: `PARTIAL`.
- Реализовано: локальные элементы self-heal и test discipline.
- Что не закрыто: единый production-safe lifecycle: fault snapshot -> patch generation -> isolated test -> apply/rollback + независимый Judge gate.
- Риск: исправления через ослабление тестов вместо исправления бизнес-логики.
- Критерий закрытия: Judge блокирует test-softening патчи, а pipeline даёт детерминированный apply/rollback.

### 1.6 Security / Zero-Trust / Cost Governance
- Статус: `DONE` (baseline), `IN_PROGRESS` (automation depth).
- Реализовано: prompt-injection guardrails, eval/anomaly, risk alerts, governance weekly aggregation.
- Что не закрыто: расширенные remediation playbooks и acceptance coverage.
- Риск: частичная автоматизация без полного контура corrective actions.
- Критерий закрытия: weekly governance выдаёт actionable remediation и может безопасно применять approved-safe actions.

### 1.7 Revenue Engine
- Статус: `NOT_STARTED` как полный контур из нового ТЗ.
- Реализовано: отдельные блоки, но нет завершённого closed-loop `research -> propose -> approval -> create -> publish -> analyze`.
- Ограничение: social integrations пауза до готовности аккаунтов.
- Критерий закрытия: Gumroad-first pipeline в approval-gated safe mode с evidence.

### 1.8 Stealth Browser / Anti-Fraud
- Статус: `NOT_STARTED` как production-подсистема.
- Реализовано: базовые browser paths.
- Что не закрыто: CDP-level stealth, fingerprint/behavior consistency, risk/legal gating.
- Критерий закрытия: опциональный off-by-default адаптер с policy gates и telemetry.

### 1.9 Finance Deepening
- Статус: `NOT_STARTED` на уровне bank-grade глубины из нового ТЗ.
- Реализовано: budget checks и базовый P&L контур.
- Что не закрыто: расширенный deterministic budget rail, anomaly-driven remediation, full daily financial loop.
- Критерий закрытия: стабильный daily P&L + auto-detection cost anomalies + safe remediation.

## 2. Детальный новый план (принят как ТЗ)

### 2.1 Wave A (P0): Closure текущих критичных in-flight задач
- Цель: закрыть уже начатые блоки, не расширяя ветвление.
- Подзадача A1: Interrupt context на весь handoff chain.
- Подзадача A2: Auto-resume policies без повторного спама и loop-повторов.
- Подзадача A3: Memory-skill quality linkage с owner-facing метриками.
- Подзадача A4: Self-learning long-horizon threshold tuning + flaky decay.
- Подзадача A5: Signature key lifecycle hardening (cadence/expiry alerts).
- DoD: все A1-A5 закрыты с тестами и без регрессий базового цикла.
- Test gates: `tests/test_decision_loop.py`, `tests/test_workflow_interrupts.py`, `tests/test_memory_skill_reports.py`, `tests/test_self_learning.py`, `tests/test_self_learning_thresholds.py`, `tests/test_tooling_registry.py`.

### 2.2 Wave B (P0): Self-Healing v1
- Цель: production-safe self-healing pipeline.
- Подзадача B1: Fault snapshot contract (stack/context/function args).
- Подзадача B2: Patch proposal в isolated sandbox.
- Подзадача B3: Judge protocol для блокировки “плохих” патчей.
- Подзадача B4: Apply/rollback с лимитом попыток и audit trail.
- DoD: 3+ сценария падения закрываются автономно, без нарушения тестовой базы.
- Test gates: `tests/test_self_healer_pipeline.py`, `tests/test_judge_protocol.py`, регрессии доменных тестов.

### 2.3 Wave C (P1): Autonomous Skill Discovery v1
- Цель: автономный intake новых tool capabilities.
- Подзадача C1: Discovery scheduler (MCP/OpenAPI/Git sources).
- Подзадача C2: Schema + risk validation.
- Подзадача C3: Candidate scoring и approval workflow.
- Подзадача C4: Promotion в tooling registry с контрактной подписью.
- DoD: candidate проходит полный путь до approved stage с журналированием.
- Test gates: `tests/test_tooling_discovery.py`, расширенные `tests/test_tooling_registry.py`.

### 2.4 Wave D (P1): Revenue Engine v1 (Gumroad-first)
- Цель: первый рабочий контур monetization по новому ТЗ.
- Подзадача D1: TrendScout + competitor scan.
- Подзадача D2: Product draft + QualityJudge scoring.
- Подзадача D3: Owner approval gate.
- Подзадача D4: Publish preparation (safe mode) + post-analysis.
- DoD: один полный approval-gated цикл с evidence artifacts.
- Test gates: интеграционные сценарии workflow и publisher queue.

### 2.5 Wave E (P2): Stealth Browser Hardening
- Цель: controlled stealth path, выключенный по умолчанию.
- Подзадача E1: CDP adapter path.
- Подзадача E2: fingerprint/behavior policy.
- Подзадача E3: explicit legal/safety gate + telemetry.
- DoD: adapter доступен, но gated/off-by-default, с контролируемыми пробами.
- Test gates: contract/policy tests + guarded live-probe tests.

### 2.6 Wave F (P2): Financial Governance Deepening
- Цель: жёсткая управляемость расходов.
- Подзадача F1: deterministic budget caps per pipeline.
- Подзадача F2: daily P&L snapshots и drift monitoring.
- Подзадача F3: anomaly remediation actions (safe set).
- DoD: предсказуемые daily cost rails и корректные owner alerts.
- Test gates: `financial_controller` unit/integration + governance tests.

## 3. Приоритет исполнения
1. Закрыть Wave A полностью.
2. Выпустить Wave B в production-safe виде.
3. Запустить Wave C intake-loop.
4. Выполнить Wave D Gumroad-first цикл.
5. Затем Wave E и Wave F.

## 4. Политика на период доработки
- LLM режим: только free Gemini 2.5 (временный cost-safe режим).
- Уведомления: cron/proactive спам отключён, пауза сохраняется до явного `/resume`.
- Social integrations: остаются на паузе до готовности аккаунтов владельца.
