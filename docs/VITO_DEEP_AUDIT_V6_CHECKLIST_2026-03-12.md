# VITO Deep Audit v6 Checklist

Источник: `input/attachments/VITO AUDIT v6.docx`

Статусы:
- `done`
- `done_already`
- `partial`
- `not_done`
- `blocked_policy`

## P0
- [x] `calendar_knowledge.py` SyntaxError fixed (`done_already`)
- [x] `AgentEventBus` explicit main/dashboard wiring (`done_already`)
- [x] `ETSY_SPEC` added (`done_already`)
- [x] `KDP_SPEC` added (`done_already`)
- [x] `PRINTFUL_SPEC` added (`done_already`)

## P1
- [x] `curriculum_agent` prompt (`done_already`)
- [x] `opportunity_scout` prompt (`done_already`)
- [x] `self_evolver_v2` prompt (`done_already`)
- [x] `self_healer_v2` prompt (`done_already`)
- [x] `platform_onboarding_agent` prompt (`done_already`)
- [x] `SelfEvolverV2` LLM proposals
- [x] `AutonomyOverseer` LLM diagnostics
- [x] `ModuleDiscovery` JSON/API path
- [x] `QualityJudge` enforcement thresholds
- [x] `VITOBenchmarks` scenario benchmarks

## P2
- [x] `pgvector` startup warning when disabled
- [x] `Dockerfile` aligned with patchright-first runtime
- [x] `docs/COMMS_FLOW.md`
- [x] `mem0` auto-enable or explicit startup warning when key exists

## Already present / to confirm
- [x] `PatchGenerator -> Sandbox -> Apply -> rollback` (`done_already`)
- [x] `KnowledgeGraph` (`done_already`)
- [x] `BrowserLLMNavigation` (`done_already`)
- [x] `ParallelOrchestrationRuntime` (`done_already`)
