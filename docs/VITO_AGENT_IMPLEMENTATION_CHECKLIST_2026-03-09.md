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

Общий прогресс: `100%`

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
- [x] `QualityGate` для publish/listing/content-required действий
- [x] backward-compatible rollout для новых handoff paths
- Status: `done`
- Weight: `18%`

## Phase J — Core Workflow Wiring
- [x] `W01` digital product sales loop
- [x] `W02` content publication loop
- [x] `W03` monitoring/self-heal loop
- [x] `W04` account/auth loop
- [x] `W05` social launch loop
- [x] `W06` analytics-response loop
- [x] `W07` compliance/risk gating loop
- [x] `W08` skill growth/self-upgrade loop
- [x] runtime traces для handoff chain
- Status: `done`
- Weight: `18%`

## Phase K — Thin-Wrapper Agent Uplift
- [x] `SEOAgent` data/tool uplift
- [x] `MarketingAgent` strategy uplift
- [x] `EconomicsAgent` pricing uplift
- [x] `LegalAgent` TOS/policy uplift
- [x] `RiskAgent` reputation/moderation uplift
- [x] `EmailAgent` real delivery path
- [x] `TranslationAgent` real provider path
- [x] `PartnershipAgent` affiliate/outreach uplift
- Status: `done`
- Weight: `22%`

## Phase L — Tier-2 Agent Hardening
- [x] `TrendScout`
- [x] `ResearchAgent`
- [x] `BrowserAgent`
- [x] `ECommerceAgent`
- [x] `AccountManager`
- [x] `SecurityAgent`
- [x] `DevOpsAgent`
- [x] `VITOCore`
- [x] `ContentCreator`
- [x] `SMMAgent`
- [x] `AnalyticsAgent`
- [x] `PublisherAgent`
- [x] `DocumentAgent`
- [x] `QualityJudge`
- [x] `HRAgent`
- [x] `SelfHealer`
- Status: `done`
- Weight: `20%`

## Phase M — Agent Benchmark Matrix
- [x] fixed benchmark per agent
- [x] cross-agent benchmark per family
- [x] autonomy/data/evidence/collaboration/recovery scorecard
- [x] rerun for all 23 agents
- [x] доказуемое покрытие всех 23 агентов без исключений
- Status: `done`
- Weight: `12%`

## Phase N — Final Judge and Responsibility Graph
- [x] lead/support/verify/block matrix in runtime
- [x] QualityJudge domain scoring
- [x] VITOCore final responsibility enforcement
- [x] block-signals stop unsafe execution
- [x] coverage audit for all required interactions
- Status: `done`
- Weight: `10%`
