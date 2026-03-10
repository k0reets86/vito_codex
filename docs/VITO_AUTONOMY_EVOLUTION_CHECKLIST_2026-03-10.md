# VITO Autonomy + Evolution Checklist — 2026-03-10

Правило:
- Ничего не пропускать и не сужать самопроизвольно.
- Статусы только:
  - `done`
  - `partial`
  - `not_done`
  - `paused_blocked`

Общий прогресс: `46%`

## Phase AE1 — Evolution Engine Foundations
1. `SandboxManager`
- Status: `done`
- Почему: реализован модуль `modules/sandbox_manager.py`, поддерживает git worktree create/run/destroy и покрыт тестом.

2. `ApplyEngine`
- Status: `done`
- Почему: реализован модуль `modules/apply_engine.py` со snapshot/health/rollback и тестами.

3. `VITOBenchmarks`
- Status: `done`
- Почему: реализован модуль `modules/vito_benchmarks.py` со структурированным benchmark delta scoring.

4. `ModuleDiscovery`
- Status: `done`
- Почему: реализован модуль `modules/module_discovery.py` с discovery для PyPI/GitHub и ранжированием кандидатов.

5. `VITO_EVOLUTION_ENABLED`
- Status: `done`
- Почему: добавлен в `config/settings.py` и `.env.example`.

6. `/health endpoint`
- Status: `done`
- Почему: `dashboard_server.py` отдает `/health` и `/api/health`.

7. `Baseline tests for evolution foundations`
- Status: `done`
- Почему: добавлены и пройдены тесты для sandbox/apply/benchmarks/discovery/v2 agents/dashboard health.

## Phase AE2 — Self-Healer V2 / Self-Evolver V2
8. `SelfHealerV2`
- Status: `done`
- Почему: реализован `agents/self_healer_v2.py` с sandbox-first heal path и тестом.

9. `SelfEvolverV2`
- Status: `done`
- Почему: реализован `agents/self_evolver_v2.py` с benchmark-driven proposal path и тестом.

10. `Compatibility layer with current runtime`
- Status: `done`
- Почему: `main.py` создает AE1 foundation и прокладывает `self_healer_v2/self_evolver_v2` в runtime/decision loop.

11. `Healing wrapper in decision/execution lanes`
- Status: `done`
- Почему: `decision_loop` теперь использует `self_healer_v2` как primary safe path через `_handle_runtime_error()`, а legacy healer остается controlled fallback внутри `SelfHealerV2`.

12. `Reflection/archive hooks for improvement cycles`
- Status: `done`
- Почему: добавлен формальный `EvolutionArchive`, в который `SelfHealerV2` и `SelfEvolverV2` пишут healing/evolution outcomes; reflections сохраняются параллельно.

## Phase AE3 — Autonomy Runtime Completion
13. `CurriculumAgent formal benchmark coverage`
- Status: `partial`
- Почему: агент есть, но нет отдельного autonomy benchmark lane.

14. `OpportunityScout formal benchmark coverage`
- Status: `partial`
- Почему: агент есть, но нет полного benchmark/runtime score pack.

15. `SelfEvolver autonomy benchmark coverage`
- Status: `partial`
- Почему: runtime есть, но benchmark contract неполный.

16. `Daily/weekly autonomy schedule hooks`
- Status: `partial`
- Почему: части циклов есть, но не как законченный autonomy schedule.

17. `Owner proposal lifecycle`
- Status: `partial`
- Почему: proposals есть, но approval/deferral/execution цикл не формализован полностью.

18. `Archive of successful improvements`
- Status: `not_done`
- Почему: отдельный formal archive не реализован.

19. `SkillLibrary deeply influences planning/runtime`
- Status: `partial`
- Почему: влияние есть, но не везде и не как строгий governor.

## Phase AE4 — Discovery / Overseer / Governance
20. `Weekly automated module discovery`
- Status: `not_done`
- Почему: discovery scheduler отсутствует.

21. `Async Overseer / stuck-loop watcher`
- Status: `not_done`
- Почему: отдельного overseer слоя нет.

22. `Dashboard evolution events`
- Status: `partial`
- Почему: EventBus есть, но отдельного evolution event lane нет.

23. `AGENTS evolution rules in repo`
- Status: `partial`
- Почему: общие rules есть, но evolution-specific layer не оформлен.

24. `Apply-engine security audit trail`
- Status: `not_done`
- Почему: apply engine еще не реализован.

25. `Control-plane secrets discipline for sandbox`
- Status: `not_done`
- Почему: sandbox policy еще не реализована.

## Phase AE5 — Combat Validation
26. `Sandbox/apply/heal/evolve/discovery tests`
- Status: `not_done`
- Почему: зависит от AE1-AE4.

27. `Runtime evolution smoke`
- Status: `not_done`
- Почему: зависит от AE1-AE4.

28. `Fail-to-pass patch validation`
- Status: `not_done`
- Почему: отдельной метрики и сценария пока нет.

29. `Owner-facing evolution summary`
- Status: `not_done`
- Почему: специального summary/reporting lane нет.

30. `Full review against both docs`
- Status: `not_done`
- Почему: выполняется после реализации пунктов выше.

## Already Present And Reused
31. `CurriculumAgent base runtime`
- Status: `done`
- Почему: агент реализован и подключен в main.

32. `OpportunityScout base runtime`
- Status: `done`
- Почему: агент реализован и подключен в main.

33. `OwnerModel`
- Status: `done`
- Почему: реализован и встроен в owner/runtime loops.

34. `VITOReflector`
- Status: `done`
- Почему: reflection subsystem существует и используется.

35. `SkillLibrary`
- Status: `done`
- Почему: библиотека навыков и retrieval уже реализованы.

36. `Autonomy runtime hooks`
- Status: `done`
- Почему: автономные подсистемы уже встроены в decision/conversation/runtime.
