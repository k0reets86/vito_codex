# VITO Autonomy + Evolution Checklist — 2026-03-10

Правило:
- Ничего не пропускать и не сужать самопроизвольно.
- Статусы только:
  - `done`
  - `partial`
  - `not_done`
  - `paused_blocked`

Общий прогресс: `100%`

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
- Status: `done`
- Почему: добавлен formal autonomy benchmark layer (`modules/autonomy_benchmark_matrix.py`), `CurriculumAgent` теперь отдает `runtime_profile` и `used_skills`, покрыт тестами и входит в matrix scoring.

14. `OpportunityScout formal benchmark coverage`
- Status: `done`
- Почему: `OpportunityScout` теперь использует `SkillLibrary`, отдает `runtime_profile` и `used_skills`, включен в formal autonomy benchmark matrix.

15. `SelfEvolver autonomy benchmark coverage`
- Status: `done`
- Почему: `SelfEvolverV2` теперь отдает `runtime_profile`, `archive_ref`, `used_skills`, а benchmark contract формализован через autonomy matrix.

16. `Daily/weekly autonomy schedule hooks`
- Status: `done`
- Почему: добавлен `modules/autonomy_schedule.py`, `DecisionLoop` переведен на persistent due-check/mark-run для scout/curriculum/self-evolver циклов.

17. `Owner proposal lifecycle`
- Status: `done`
- Почему: добавлен `modules/autonomy_proposals.py`, `ConversationEngine` умеет показывать предложения, фиксировать выбор, approve/defer/reject и запускать их как goal-backed execution.

18. `Archive of successful improvements`
- Status: `done`
- Почему: `EvolutionArchive` уже встроен в `SelfHealerV2/SelfEvolverV2`, а autonomy proposal lifecycle теперь имеет persistent execution history в `AutonomyProposalStore`.

19. `SkillLibrary deeply influences planning/runtime`
- Status: `done`
- Почему: `CurriculumAgent`, `OpportunityScout`, `SelfEvolverV2` теперь используют retrieval из `SkillLibrary`, возвращают `used_skills` и записывают skill-use в runtime.

## Phase AE4 — Discovery / Overseer / Governance
20. `Weekly automated module discovery`
- Status: `done`
- Почему: `decision_loop.py` теперь имеет `_maybe_run_evolution_discovery()`, использует `ModuleDiscovery`, пишет результаты в memory и `EvolutionEventStore`.

21. `Async Overseer / stuck-loop watcher`
- Status: `done`
- Почему: добавлен `modules/autonomy_overseer.py`, `DecisionLoop` периодически запускает overseer и пишет findings в evolution events.

22. `Dashboard evolution events`
- Status: `done`
- Почему: добавлен `EvolutionEventStore`, endpoint `/api/evolution_events` и dashboard visibility card в `dashboard_server.py`.

23. `AGENTS evolution rules in repo`
- Status: `done`
- Почему: в `AGENTS.md` добавлен отдельный раздел `Evolution rules` с обязательными runtime/governance правилами.

24. `Apply-engine security audit trail`
- Status: `done`
- Почему: добавлен `modules/evolution_audit.py`, `ApplyEngine` теперь пишет signed audit trail на success/fail/exception.

25. `Control-plane secrets discipline for sandbox`
- Status: `done`
- Почему: `SandboxManager` теперь запускает subprocesses с sanitized env allowlist через `EVOLUTION_SANDBOX_ALLOWED_ENV`.

## Phase AE5 — Combat Validation
26. `Sandbox/apply/heal/evolve/discovery tests`
- Status: `done`
- Почему: AE5-пакет закрыт таргетным regression suite (`6 passed`) и покрывает fail-to-pass, summary, events, audit, overseer и decision-loop integration.

27. `Runtime evolution smoke`
- Status: `done`
- Почему: standalone раннер `scripts/autonomy_evolution_combat_validation.py` успешно выполняет runtime smoke и генерирует боевой AE5 report.

28. `Fail-to-pass patch validation`
- Status: `done`
- Почему: добавлен `modules/fail_to_pass_validation.py`, отдельный тест и включение в AE5 combat-validation сценарий.

29. `Owner-facing evolution summary`
- Status: `done`
- Почему: добавлен `modules/evolution_summary.py`, который строит и сохраняет owner-facing markdown summary; раннер пишет `VITO_EVOLUTION_OWNER_SUMMARY_<ts>.md`.

30. `Full review against both docs`
- Status: `done`
- Почему: AE1-AE5 доведены до code+tests+combat-validation; весь консолидированный план по двум документам реализован и проверен.

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
