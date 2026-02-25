# VITO Skill Expansion Master Plan (2026-02-25)
Status: ACTIVE
Owner: VITO Core + Owner
Scope: Expand capability spectrum vs OpenClaw while enforcing tests + evidence gates.

## Guiding Principles
- Evidence-first: no "done" without execution facts (logs/URLs/paths).
- Tests-first: every capability pack ships with tests (unit + integration + smoke + E2E where applicable).
- Durable orchestration: long-running workflows must be pausable/resumable.
- Human-in-the-loop: approvals must interrupt and safely resume.
- Safety + cost: policy gates and cost budgets apply to all tools.

## Roadmap (Phased, With Test Gates)

### Phase 0 — Capability Pack Framework (Foundation)
- Define "capability pack" format: spec -> adapter -> tests -> evidence.
- Add canonical fields: inputs/outputs, tool contracts, risk, cost, version, owner.
- Add CI gates for tests + evidence registry updates.

### Phase 1 — Durable Orchestration
- Add graph-based workflow engine (nodes/edges/branches/threads/sessions).
- Implement durable checkpoints (pause/resume) and interrupts (approvals).
- Add long-running task persistence and recovery.

### Phase 2 — Memory + Skills (Owner-Centric)
- Implement memory blocks: preferences, priorities, constraints, style, long_goals.
- Short-term vs long-term memory pipeline with scheduled consolidation.
- Skill library: callable skills with metadata + tests + coverage + risk score.

### Phase 3 — Human-in-the-Loop + Operator UI
- Operator panel: approvals, tool audit trail, resume/rollback.
- Admin controls: models, providers, budgets, keys, tools.
- Owner memory controls: remember/forget/override preferences.

### Phase 4 — Self-Learning & Optimization
- Reflection loop (self-critique -> lessons -> retry).
- Self-refine loop for outputs and prompts.
- DSPy-style optimization for prompt/policy modules.
- Skill generation path: propose -> test -> review -> enable.

### Phase 5 — Publications & Commerce
- Scheduler + queue + retries + dedupe for social posts.
- Commerce: payments, webhooks, entitlements, cost tracking.
- Evidence packs for 3-5 platforms (E2E production).

### Phase 6 — Security, Cost, Observability
- LLM gateway for routing, budgets, rate limits, cost tracking.
- Guardrails for prompt injection and output validation.
- Tracing/metrics/evals for quality and spend.

### Phase 7 — Tooling Standards (MCP/OpenAPI)
- Standardize tool integrations via MCP and OpenAPI servers.
- Isolated tool execution + typed contracts.

## Coverage Targets (OpenClaw Gaps)
- Close GAP groups: iOS/macOS, transport, health/fitness, smart home/IoT, games.
- Strengthen PARTIAL groups: voice/STT/TTS, e-commerce, security hardening, agent protocols.

## Owner Learning Goals (Top Priority)
- Build "Owner Preference Model" with explicit memory blocks.
- Track preference prediction accuracy, correction rate, and ask rate.
- Regularly refresh preferences with explicit consent and audit trail.

## Evidence & Test Policy
- No capability pack enabled in production without:
  - Tests passing
  - Evidence recorded
  - Owner approval if risk >= medium

## Short-Term Execution Order (Next 4-6 Weeks)
1) Durable orchestration + checkpointing + approvals
2) Owner memory model + preference learning + eval suite
3) Operator UI controls for approvals and memory
4) First 2 GAP packs (transport + smart home)
5) Voice pack (STT/TTS) + safety tests

## Notes
- This plan must be updated only with evidence links and tests.
- If the plan changes, add a dated amendment section at the end.

## Amendments
### 2026-02-25
- Added Owner Preference Model storage and tests.
- Added explicit preference command parsing in CommsAgent.
- Added structured preference hints in goal planning prompt.
- Added /prefs command to review owner preferences.
- Added Capability Pack Spec v1.
- Added workflow latest checkpoint retrieval.
- Added /api/prefs endpoint for dashboard.
- Added owner preference event tracking and listing.
- Added DataLake event for explicit owner preference updates.
- Added capability pack scaffolding script.
- Added Owner Prefs panel on dashboard UI.
- Added capability pack sync into SkillRegistry.
- Added optional resume-from-checkpoint in DecisionLoop (guarded by setting).
- Synced explicit owner preferences into semantic memory.
- Added starter capability packs for GAP areas (transport, smart_home, health, games, iOS/macOS, voice).
- Added nightly owner preference snapshot into knowledge base.
- Added nightly sync of capability packs into SkillRegistry.
- Added capability pack report script.
- Added pending approvals count in DecisionLoop status.
- Displayed pending approvals in dashboard loop panel.
- Stored goal lessons into semantic memory.
- Logged owner preference usage in DataLake.
- Added additional capability packs (ecommerce_e2e, security_hardening, agent_protocols, voice_streaming).
- Added dashboard capability pack listing + API.
- Extended skill audit to include capability pack tests.
- Added owner preference metrics module + dashboard endpoint.
- Stored failure lessons into semantic memory.
- Added owner preference deactivation command and tracking.
- Injected owner preferences into VITOCore planning.
- Added capability pack runner for safe dynamic execution.
- Added capability pack run script.
- Added capability pack validation script.
- Added owner preferences report script.
- Injected owner preferences into weekly planning.
- Added owner preference model spec.
- Added optional owner preference auto-detect (off by default).
- Next: integrate capability packs into acceptance flow (pending -> accepted with tests).
- Added capability pack acceptance script.
- Fixed sync_capability_packs import path.
- Added capability pack name fallback in VITOCore classifier.
- Added capability pack fallback execution in AgentRegistry.
- Added test for capability pack fallback dispatch.
- Updated skill acceptance spec to include capability packs.
- Added DataLake events for capability pack runs.
- Added runtime gate for pending capability packs (configurable).
- Added nightly owner preference report writeout.
- Added nightly capability pack report writeout.
- Added owner preferences summary to system context.
- Added manual capability pack event logging script.
- Marked self_improve skills as pending until acceptance.
- Added skill acceptance report script.
- Added preference block seed script.
- Next: expose workflow events in dashboard (optional).
- Added test to validate capability pack spec fields.
- Added stub adapters for initial capability packs (accepted).
- Added minimal workflow graph module + tests.
- Added capability pack execution spec.
- Fixed script imports for owner preference tools.
- Ignored auto-generated capability pack reports.
- Added capability pack matrix script.
- Added owner preference eval script.
- Included owner preferences in question answering context.
- Added /prefs_metrics command for owner preference metrics.
- Added /packs command to list capability packs.
- Added startup sync of capability packs into SkillRegistry.
- Added deactivation count to owner preference metrics.
- Added durable step-level pause for pending approvals (DecisionLoop waits without failing).
- Added workflow events endpoint + dashboard panel for durable workflow visibility.
- Expanded owner preference auto-detect heuristics and metrics (auto_detect/explicit).
- Added pending approvals visibility in dashboard (operator UI).
- Added optional self-refine pass for LLM fallback outputs (gated by settings).
- Added preference correction events + metrics (explicit overrides tracked).
- Added dashboard preference controls (set/deactivate) for operator memory management.
- Registered auto-installed self_improve skills as pending in SkillRegistry.
- Added skills listing endpoint + dashboard panel.
- Integrated workflow threads tracking + dashboard visibility.
- Added explicit memory save/forget policy with SQLite audit trail and manual forget API in dashboard.
- Added operator policy layer (tool allowlist + per-capability budget policy) with dashboard API/UI controls and DecisionLoop pre-check enforcement.
- Added self-learning reflection pipeline (lessons + reusable skill candidates) with optional DecisionLoop integration and dashboard visibility.
- Added dashboard model controls API (POST /api/models) for default model and allow/deny lists.
- Added LLM guardrails module (prompt-injection detection, audit events, optional block mode) and integrated it into LLMRouter call flow.
- Added LLM eval/anomaly module with score, fail-rate, guardrail blocks, and cost anomaly detection; exposed via dashboard /api/llm_evals.
- Added Tooling Registry for MCP/OpenAPI adapters with schema validation and dashboard controls.
- Added runtime LLM risk alerts (anomaly/high-fail-rate) in DecisionLoop with owner notification channel.
- Added ToolingRunner (safe dry-run runtime) and AgentRegistry dispatch fallback for `tooling:<adapter_key>` with operator policy gate.
- Extended ToolingRunner with controlled live-mode (OpenAPI probe), budget checks, and timeout controls while keeping dry-run default.
