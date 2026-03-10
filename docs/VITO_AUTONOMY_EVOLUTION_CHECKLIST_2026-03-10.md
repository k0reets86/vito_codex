# VITO Autonomy + Evolution Checklist — 2026-03-10

Правило:
- Ничего не пропускать и не сужать самопроизвольно.
- Статусы только:
  - `done`
  - `partial`
  - `not_done`
  - `paused_blocked`

Общий прогресс: `18%`

## Phase AE1 — Evolution Engine Foundations
1. `SandboxManager`
- Status: `not_done`
- Почему: отдельного production-ready модуля пока нет.

2. `ApplyEngine`
- Status: `not_done`
- Почему: отдельного safe apply/rollback engine пока нет.

3. `VITOBenchmarks`
- Status: `not_done`
- Почему: существующая agent matrix не закрывает модульный self-improvement benchmark.

4. `ModuleDiscovery`
- Status: `not_done`
- Почему: runtime-discovery pipeline отсутствует.

5. `VITO_EVOLUTION_ENABLED`
- Status: `not_done`
- Почему: отдельного флага в settings/.env.example нет.

6. `/health endpoint`
- Status: `not_done`
- Почему: dashboard не отдает отдельный `/health`.

7. `Baseline tests for evolution foundations`
- Status: `not_done`
- Почему: тестового пакета для этих модулей еще нет.

## Phase AE2 — Self-Healer V2 / Self-Evolver V2
8. `SelfHealerV2`
- Status: `not_done`
- Почему: есть сильный `SelfHealer`, но не v2-контур с sandbox/apply flow.

9. `SelfEvolverV2`
- Status: `not_done`
- Почему: есть autonomy self_evolver, но нет benchmark/apply successor.

10. `Compatibility layer with current runtime`
- Status: `not_done`
- Почему: main/decision_loop пока не умеют работать с v2 execution layer.

11. `Healing wrapper in decision/execution lanes`
- Status: `partial`
- Почему: старый self-healer уже привязан, но не через v2 sandbox lifecycle.

12. `Reflection/archive hooks for improvement cycles`
- Status: `partial`
- Почему: reflections есть, но improvement archive formalized не закрыт.

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
