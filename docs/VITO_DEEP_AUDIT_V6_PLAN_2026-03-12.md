# VITO Deep Audit v6 Plan

Источник: `input/attachments/VITO AUDIT v6.docx`

Правило исполнения:
- объем не сокращать;
- пункт считается закрытым только если он реализован и проверен;
- если аудит устарел и пункт уже закрыт в коде, фиксировать это как `done_already` с проверкой.

## P0
1. Исправить `modules/calendar_knowledge.py`.
2. Явно закрепить `AgentEventBus` в `main.py` и dashboard.
3. Расширить `config/platform_specs.py` минимум для `Etsy`, `KDP`, `Printful`.

## P1
4. Добавить missing prompts:
   - `curriculum_agent`
   - `opportunity_scout`
   - `self_evolver_v2`
   - `self_healer_v2`
   - `platform_onboarding_agent`
5. Перевести `SelfEvolverV2` на LLM-based proposal generation с безопасным fallback.
6. Добавить `AutonomyOverseer` LLM diagnostics для stuck-cases.
7. Убрать HTML scraping из `ModuleDiscovery`.
8. Добавить enforcement thresholds в `QualityJudge`.
9. Усилить `VITOBenchmarks` реальными scenario-бенчмарками.

## P2
10. Добавить warning path при пустом `DATABASE_URL`, когда `pgvector` отключен.
11. Согласовать `Dockerfile` с `patchright`-стеком.
12. Создать `docs/COMMS_FLOW.md`.
13. Добавить `mem0` auto-enable или явный warning path при наличии ключа.

## Already present / to re-validate
14. `PatchGenerator -> Sandbox -> Apply -> rollback`
15. `KnowledgeGraph`
16. `BrowserLLMNavigation`
17. `ParallelOrchestrationRuntime`

## Verification
- `py_compile` по затронутым модулям
- таргетный `pytest`
- обновление чеклиста после каждого связанного пакета
