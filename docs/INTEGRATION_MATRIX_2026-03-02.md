# VITO Integration Matrix (Google Doc -> Practical VITO Synthesis)
Дата: 2026-03-02  
Источник: `docs/import/google_doc_1Vw0_vBXSWGo4UBiniEQPBs1GrIPrPCEEte8sE2KeOvs.txt`

## Цель матрицы
Не копировать идеи из внешних репозиториев, а отбирать и встраивать только то, что:
- увеличивает автономность и качество исполнения;
- повышает безопасность и управляемость;
- имеет измеримый эффект на ROI/стоимость;
- совместимо с текущей архитектурой VITO.

## Легенда решений
- `ADOPT`: берём почти целиком (с минимальной адаптацией).
- `ADAPT`: берём принцип/паттерн, но реализуем в архитектуре VITO.
- `DEFER`: откладываем до выполнения зависимостей.
- `DROP`: не берём (низкая ценность/высокий риск/правовые ограничения).

---

## 1) Orchestration / Multi-Agent Core

### 1.1 Orchestrator-Workers + Reflexion (LangGraph/CrewAI идеи)
- Решение: `ADAPT`
- Почему: у VITO уже есть `DecisionLoop` + `OrchestrationManager`; полный перенос на внешний фреймворк даст миграционный риск без гарантированной выгоды.
- Как внедряем:
  - сохраняем внутренний state-machine и усиливаем Reflexion-петли на уровне step contracts;
  - фиксируем chain-context (interrupt metadata, ownership, retries) в handoff.
- Куда в коде:
  - `decision_loop.py`
  - `modules/orchestration_manager.py`
  - `modules/step_contract.py`
- Тесты/DoD:
  - handoff-метаданные проходят через весь chain;
  - no silent retries after owner-cancel;
  - регрессии: `tests/test_decision_loop.py`, `tests/test_workflow_state_machine.py`, `tests/test_workflow_threads.py`.

### 1.2 23-role “социология агентов” (CrewAI style role/goal/backstory)
- Решение: `ADAPT`
- Почему: принципы полезны для дисциплины промптов, но переводить систему 1:1 в CrewAI не нужно.
- Как внедряем:
  - унифицируем роль/цель/ограничения в registry-конфиге агентов;
  - добавляем KPI-поля в отчётность operator dashboard.
- Куда:
  - `modules/agent_registry.py` (или текущий registry слой)
  - `dashboard_server.py`
- DoD:
  - роли и KPI видны в dashboard/API;
  - маршрутизация не деградирует.

---

## 2) Memory / RAG / Lifelong Learning

### 2.1 3-layer memory (working + vector + structured DB)
- Решение: `ADOPT` (фактически уже реализовано в VITO базе)
- Состояние: `DONE/IN_PROGRESS`
- Что дожимаем:
  - связь memory-quality с реальной результативностью skill execution.
- Куда:
  - `modules/memory_blocks.py`
  - `modules/memory_manager.py`
  - `modules/memory_skill_reports.py`
- DoD:
  - weekly отчёт содержит quality per skill и remediation signals;
  - retention drift алерты дают actionable шаги.

### 2.2 Experience-driven learning (ELL/EvoAgentX/AgentEvolver идеи)
- Решение: `ADAPT`
- Почему: полезен подход “опыт -> гипотеза -> тест -> promotion”, но без автогенерации сложных graph-mutating пайплайнов на проде.
- Куда:
  - `modules/self_learning.py`
  - `config/self_learning_test_map.py`
- DoD:
  - long-horizon thresholds + flaky decay работают стабильно;
  - auto-promotion не повышает regression rate.

---

## 3) Self-Healing / Reliability

### 3.1 Pipeline Doctor (healing-agent pattern)
- Решение: `ADAPT` (P0)
- Почему: очень высокая практическая ценность.
- Минимальный контур v1:
  - Detect: structured failure snapshot;
  - Diagnose: классификация причины и strategy выбора ремонта;
  - Fix: candidate patch;
  - Test: isolated sandbox run;
  - Apply/Rollback: строго по результатам тестов.
- Куда:
  - `self_healer.py`
  - `decision_loop.py` (триггеры/политики)
  - `modules/step_contract.py` (статусы/контракты ошибок)
- DoD:
  - подтверждённые сценарии авто-ремонта без “сломанных тестов”.

### 3.2 Judge Protocol (ghost pattern)
- Решение: `ADOPT` (P0)
- Почему: обязательный предохранитель против “починки через ослабление тестов”.
- Куда:
  - `judge_protocol.py`
  - `self_healer.py` (gated apply)
- DoD:
  - Judge отклоняет патчи, меняющие бизнес-утверждения и ослабляющие проверки.

### 3.3 Self-healing locators/UI
- Решение: `DEFER` (P2)
- Почему: полезно, но зависит от зрелости browser runtime и правовых/операционных ограничений.
- Зависимости:
  - controlled browser layer;
  - telemetry на неудачные локаторы.

---

## 4) Tooling / MCP / OpenAPI

### 4.1 Typed contracts + signatures + stage governance
- Решение: `ADOPT` (уже есть, продолжаем hardening)
- Состояние: `DONE/IN_PROGRESS`
- Дожим:
  - key rotation cadence checks;
  - expiry alerts;
  - stricter release-bundle verification paths.
- Куда:
  - `modules/tooling_registry.py`
  - `modules/tooling_runner.py`

### 4.2 Autonomous skill discovery loop
- Решение: `ADAPT` (P1)
- Почему: ключевой дифференциатор против ручного install-flow.
- Контур:
  - discover sources -> parse spec -> schema/risk validate -> candidate score -> approval -> promote.
- Куда:
  - новый модуль `modules/tooling_discovery.py` (план)
  - интеграция в `decision_loop.py`
- DoD:
  - end-to-end intake с аудитом.

---

## 5) Security / Zero-Trust

### 5.1 Prompt-Guard + untrusted-data isolation
- Решение: `ADOPT` (уже внедрено, усиливаем policy coverage)
- Куда:
  - `modules/llm_guardrails.py`
  - `llm_router.py`
- DoD:
  - внешние данные маркируются и не могут исполнять инструкции.

### 5.2 Least-privilege / policy gates / human approvals
- Решение: `ADOPT`
- Куда:
  - `modules/operator_policy.py`
  - `modules/tooling_runner.py`
  - `comms_agent.py` approval flows
- DoD:
  - high-risk действия не проходят без явного допуска.

### 5.3 Sandboxing generated code
- Решение: `ADAPT`
- Почему: нужен контролируемый runtime и audit, без “широких” привилегий.
- Куда:
  - sandbox worker path в tooling runtime;
  - self-healer isolated environment.

---

## 6) Proactivity / Scheduling / Anti-Spam

### 6.1 ProactiveAgent ideas
- Решение: `ADAPT` (с жёсткими owner-ограничениями)
- Принцип:
  - инициативность полезна только при measurable utility;
  - по умолчанию тихий режим;
  - `/cancel` = полная пауза proactive/cron до `/resume`.
- Куда:
  - `main.py` scheduler/proactive gates
  - `comms_agent.py` notification policy
  - `modules/cancel_state.py`
- DoD:
  - отсутствие повторного спама после отмены.

---

## 7) Revenue Engine

### 7.1 Upwork/Fiverr autonomous bidding
- Решение: `DEFER` (P2)
- Почему: высокая правовая/операционная нагрузка и anti-fraud риски; сначала безопасный Gumroad-first контур.

### 7.2 QualityJudge with scoring gates
- Решение: `ADOPT` (P1)
- Почему: прямой контроль качества и снижение мусорных публикаций.
- Куда:
  - `agents/quality_judge.py` (или текущий quality module)
  - workflow routing в `decision_loop.py`
- DoD:
  - score-gated переходы `<60 -> redo`, `60-79 -> owner approval`, `80+ -> ready`.

### 7.3 Gumroad-first closed loop
- Решение: `ADAPT` (P1)
- Почему: owner priority + минимальный go-to-market риск.
- Контур:
  - trend research -> product draft -> quality gate -> owner approval -> publish prep -> performance review.

---

## 8) Stealth Browser / Anti-Detection

### 8.1 nodriver/CDP/fingerprint ideas
- Решение: `DEFER` (P2, guarded)
- Почему: потенциально полезно, но высокий risk/legal surface.
- Политика:
  - off-by-default;
  - explicit owner approval;
  - ограниченные probes;
  - строгий журнал действий.

### 8.2 Accessibility tree parsing
- Решение: `ADAPT` (P2)
- Почему: снижение токенов и устойчивость к DOM-шума.
- Условие:
  - только в легитимных automation сценариях.

---

## 9) Finance / Cost Governance

### 9.1 Model arbitrage + strict caps
- Решение: `ADOPT`
- Состояние: в работе.
- Что делаем:
  - deterministic caps per capability;
  - anomaly-based remediation.

### 9.2 Revolut deep integration
- Решение: `DEFER`
- Почему: требует отдельного security/reliability контура и compliance-проверки.

---

## 10) Что НЕ заимствуем “как есть”
- Полные миграции на внешние фреймворки без доказанной выгоды.
- Агрессивные stealth/anti-detection практики без юридической и policy-оценки.
- Автоизменения прод-кода без Judge + sandbox + regression gates.
- Любые “демо-ориентированные” трюки без measurable business impact.

---

## 11) Канонический приоритет внедрения (синтез)
1. `P0`: Wave A closure (in-flight критичные блоки).
2. `P0`: Self-Healing v1 (Pipeline Doctor + Judge).
3. `P1`: Autonomous Tooling Discovery v1.
4. `P1`: Gumroad-first Revenue Loop + QualityGate.
5. `P2`: Stealth/Browser advanced + Finance deep integration.

---

## 12) Контроль “ничего важного не пропустить”
Для каждой идеи из Google Doc обязательны поля:
- `Value`: как помогает owner goals.
- `Fit`: куда в текущей архитектуре встраивается.
- `Risk`: безопасность/право/стоимость.
- `Evidence`: какие тесты и артефакты доказывают работоспособность.
- `Decision`: ADOPT/ADAPT/DEFER/DROP.

Эта матрица является рабочим фильтром перед любым внедрением.
