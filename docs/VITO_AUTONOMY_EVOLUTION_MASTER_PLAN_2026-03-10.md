# VITO Autonomy + Evolution Master Plan — 2026-03-10

Статус: `MANDATORY`

Источники:
- `input/inbox/screenshots/VITO_AUTONOMY_PLAN_v2.docx`
- `input/inbox/screenshots/VITO_EVOLUTION_ENGINE.docx`
- `docs/VITO_UPGRADE_MASTER_PLAN_2026-03-09.md`
- `docs/VITO_DELTA_AUDIT_V4_CHECKLIST_2026-03-10.md`
- `docs/VITO_AGENT_IMPLEMENTATION_MASTER_PLAN_2026-03-09.md`

## 0. Правило исполнения

Объем этого плана нельзя самопроизвольно сокращать.
Пункт можно не реализовывать только если:
1. он уже реально закрыт в коде и это доказано тестом/рантаймом;
2. есть внешний/недопустимый блокер;
3. владелец явно снял этот пункт.

Все остальное обязательно к реализации.

## 1. Консолидированный диагноз

Оба документа требуют довести VITO не просто до "сильного ассистента", а до:
- проактивного стратега,
- постоянно обучающейся системы,
- безопасного self-heal / self-improve контура,
- операционного skill-library слоя,
- owner-aware автономии,
- benchmark-driven self-evolution,
- контролируемого apply/rollback цикла.

Главный разрыв на сейчас:
- `Autonomy v2` частично встроен в runtime;
- `Evolution Engine` как полный pipeline (`sandbox -> test -> apply -> rollback -> reflect`) еще не закрыт.

## 2. Что уже закрыто и переиспользуется

### 2.1 Из `VITO_AUTONOMY_PLAN_v2.docx` уже есть база
- `CurriculumAgent`
- `OpportunityScout`
- `SelfEvolver`
- `VITOSkillLibrary`
- `VITOReflector`
- `OwnerModel`
- autonomy runtime hooks
- skill/runbook packs
- post-plan agent uplift

Но это не означает, что Autonomy v2 закрыт полностью. Остаются:
- benchmark-формализация autonomy agents;
- deeper integration в decision loop;
- owner-visible proposal lifecycle;
- archive of improvements;
- stronger daily/weekly autonomy scheduling.

### 2.2 Из `VITO_EVOLUTION_ENGINE.docx` частично уже есть база
- `SelfHealer` + runtime remediation + fail-closed verify path
- `SelfEvolver` как proposal engine
- `AgentEventBus`
- guardrails / prompt guard
- часть browser-safe infrastructure
- часть benchmark infrastructure через agent benchmark matrix

Но отсутствуют как отдельные production subsystems:
- `SandboxManager`
- `ApplyEngine`
- `ModuleDiscovery`
- `VITOBenchmarks`
- `SelfHealerV2`
- `SelfEvolverV2`
- `/health` endpoint
- evolution background loop
- weekly discovery schedule
- AGENTS evolution rules hook
- fail-to-pass patch scoring
- archive of successful improvements

## 3. Целевое состояние

VITO должен уметь:
1. сам генерировать цели и opportunities;
2. сам строить reusable skills и использовать их повторно;
3. после каждого успеха/провала писать reflection и attribution;
4. хранить и обновлять owner model;
5. безопасно лечить runtime ошибки через sandbox + verify;
6. безопасно предлагать и применять self-improvements;
7. находить новые библиотеки/модули и проверять их в sandbox;
8. применять улучшения только после benchmark delta и health check;
9. откатывать изменения автоматически;
10. логировать evolution events и показывать их в dashboard/Telegram.

## 4. Фазы реализации

## Phase AE1 — Evolution Engine Foundations
Сделать:
1. `modules/sandbox_manager.py`
2. `modules/apply_engine.py`
3. `modules/vito_benchmarks.py`
4. `modules/module_discovery.py`
5. `VITO_EVOLUTION_ENABLED` в settings/.env.example
6. `/health` endpoint в dashboard server
7. baseline tests для этих модулей

Definition of done:
- sandbox создается и чистится;
- apply engine умеет safe apply / rollback / health check;
- benchmarks возвращают структурированный score;
- module discovery выдает проверяемых кандидатов.

## Phase AE2 — Self-Healer V2 / Self-Evolver V2
Сделать:
1. `agents/self_healer_v2.py`
2. `agents/self_evolver_v2.py`
3. адаптер совместимости со старым `SelfHealer`/`SelfEvolver`
4. wiring в `main.py`
5. healing execution wrapper для decision loop / critical runtime lane
6. reflection hooks на success/failure improvement cycle

Definition of done:
- ошибки лечатся через diagnose -> patch -> sandbox -> verify -> apply;
- self-improve proposals проходят benchmark gate;
- старый runtime не ломается.

## Phase AE3 — Autonomy Runtime Completion
Сделать:
1. formal benchmark coverage для:
   - `curriculum_agent`
   - `opportunity_scout`
   - `self_evolver`
2. daily/weekly autonomy schedule hooks
3. owner proposal lifecycle:
   - proposal -> owner visibility -> approval/deferral -> execution
4. archive of successful improvements and reflections
5. stronger use of `skill_library` in planning/runtime

Definition of done:
- autonomy triad работает не как декоративный слой, а как operational subsystem.

## Phase AE4 — Discovery / Overseer / Governance
Сделать:
1. weekly automated module discovery
2. async overseer / stuck-loop watcher
3. dashboard/event visibility for evolution events
4. AGENTS evolution rules in repo
5. apply-engine security checks and signed audit trail
6. control-plane discipline for secrets in sandbox

Definition of done:
- evolution loop наблюдаем, безопасен и ограничен policy gates.

## Phase AE5 — Combat Validation
Сделать:
1. tests for sandbox/apply/heal/evolve/discovery
2. runtime smoke of evolution loop
3. failure-to-pass validation for at least one controlled patch path
4. owner-facing evolution summary/report
5. full checklist review against both documents

Definition of done:
- оба документа закрыты не по описанию, а по коду, тестам и сценарию.

## 5. Пересечения и как их закрывать

### 5.1 Пересечение `SelfEvolver`
- из Autonomy v2 он уже существует как proposal/strategy layer;
- из Evolution Engine нужен еще benchmark/apply/sandbox layer.
Решение:
- не делать второй конфликтующий агент;
- ввести `SelfEvolverV2` как расширение/совместимый successor;
- старый `SelfEvolver` использовать как autonomy-facing слой, а `V2` как execution engine.

### 5.2 Пересечение `Reflector`
- текущий `VITOReflector` сохраняем;
- расширяем его для healing/improvement archive вместо дублирования.

### 5.3 Пересечение benchmark-слоя
- существующая `agent benchmark matrix` не заменяет `VITOBenchmarks`;
- новая подсистема должна мерить модульные и self-improvement deltas.

## 6. Внешние паттерны, которые берем

Из `VITO_AUTONOMY_PLAN_v2.docx`:
- Voyager: curriculum + skill library
- OpenClaw: human-readable skills + self-writing
- AgentEvolver: self-questioning / self-attribution
- Reflexion: verbal reflection loop
- Self-Refine: generator/critic/refiner chain

Из `VITO_EVOLUTION_ENGINE.docx`:
- SICA / self-improving coding agent
- Gödel Agent self-improvement loop
- SWE-ReX / Open SWE sandbox patterns
- git worktree per experiment
- fail-to-pass patch scoring
- async overseer / stuck loop watch
- archive of improvements

## 7. Что запрещено
- нельзя делать второй параллельный autonomy stack, который конфликтует с текущим runtime;
- нельзя внедрять self-improvement без sandbox/verify/apply gates;
- нельзя считать proposal engine полноценным evolution engine;
- нельзя закрывать пункт без теста и runtime evidence.

## 8. Definition of Success

План считается выполненным только когда:
- оба документа сведены в один runtime-consistent контур;
- `SandboxManager`, `ApplyEngine`, `VITOBenchmarks`, `ModuleDiscovery`, `SelfHealerV2`, `SelfEvolverV2` реально существуют и интегрированы;
- autonomy triad имеет benchmark/runtime coverage;
- evolution events наблюдаемы;
- safe apply/rollback путь работает;
- checklist по обоим документам доведен до `done/blocked` без скрытых хвостов.
