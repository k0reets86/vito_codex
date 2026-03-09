# VITO Agent Implementation Checklist — 2026-03-09

Правило ведения:
- после каждого завершенного этапа показывать:
  - что сделано
  - что осталось
  - общий прогресс в процентах
- статусы только:
  - `not_started`
  - `in_progress`
  - `done`
  - `paused_blocked`

Общий прогресс: `18%`

Жесткое правило:
- `done` по этому плану возможен только если охвачены все 23 агента, все обязательные связи и все 8 workflow.
- частичное покрытие не считается завершением.

## Phase I — Agent Interaction Substrate
- [x] `BaseAgent.ask(...)`
- [x] `BaseAgent.delegate(...)`
- [x] registry привязан ко всем агентам
- [x] `NEEDS` / `CAPABILITIES` декларации для всех агентов
- [x] runtime validation capability -> benchmark/evidence
- [x] event/signal layer для handoff
- [ ] `QualityGate` для publish/listing/content-required действий
- [x] backward-compatible rollout для новых handoff paths
- Status: `done`
- Weight: `18%`

## Phase J — Core Workflow Wiring
- [ ] `W01` digital product sales loop
- [ ] `W02` content publication loop
- [ ] `W03` monitoring/self-heal loop
- [ ] `W04` account/auth loop
- [ ] `W05` social launch loop
- [ ] `W06` analytics-response loop
- [ ] `W07` compliance/risk gating loop
- [ ] `W08` skill growth/self-upgrade loop
- [ ] runtime traces для handoff chain
- Status: `not_started`
- Weight: `18%`

## Phase K — Thin-Wrapper Agent Uplift
- [ ] `SEOAgent` data/tool uplift
- [ ] `MarketingAgent` strategy uplift
- [ ] `EconomicsAgent` pricing uplift
- [ ] `LegalAgent` TOS/policy uplift
- [ ] `RiskAgent` reputation/moderation uplift
- [ ] `EmailAgent` real delivery path
- [ ] `TranslationAgent` real provider path
- [ ] `PartnershipAgent` affiliate/outreach uplift
- Status: `not_started`
- Weight: `22%`

## Phase L — Tier-2 Agent Hardening
- [ ] `BrowserAgent`
- [ ] `ECommerceAgent`
- [ ] `AccountManager`
- [ ] `VITOCore`
- [ ] `ContentCreator`
- [ ] `SMMAgent`
- [ ] `AnalyticsAgent`
- [ ] `PublisherAgent`
- [ ] `DocumentAgent`
- [ ] `QualityJudge`
- [ ] `HRAgent`
- [ ] `SelfHealer`
- Status: `not_started`
- Weight: `20%`

## Phase M — Agent Benchmark Matrix
- [ ] fixed benchmark per agent
- [ ] cross-agent benchmark per family
- [ ] autonomy/data/evidence/collaboration/recovery scorecard
- [ ] rerun for all 23 agents
- [ ] доказуемое покрытие всех 23 агентов без исключений
- Status: `not_started`
- Weight: `12%`

## Phase N — Final Judge and Responsibility Graph
- [ ] lead/support/verify/block matrix in runtime
- [ ] QualityJudge domain scoring
- [ ] VITOCore final responsibility enforcement
- [ ] block-signals stop unsafe execution
- [ ] coverage audit for all required interactions
- Status: `not_started`
- Weight: `10%`
