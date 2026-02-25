# VITO Skill Expansion Checklist

## Status Snapshot (2026-02-25)
- [x] **Phase 0 — Capability Pack Framework** (spec, CI, acceptance) — foundation in place.
- [x] **Phase 1 — Durable Orchestration** (graph sessions, checkpoints, interrupts, approval gating, `OrchestrationManager`) — implemented and wired into `DecisionLoop` + dashboard sessions + tests.
- [x] **Phase 2 — Memory + Skills** (owner memory blocks, short→long consolidation, `MemorySkillReporter`, weekly retention/output) — covered by `MemoryBlocks`, `MemoryManager`, new reporter and retention script/tests.
- [x] **Phase 3 — Human-in-the-Loop / Operator UI** (approvals, models, budgets, workflow sessions UI) — dashboard endpoints + controls for approvals, operator policy, workflow sessions/resume/cancel/reset.
- [ ] **Phase 4 — Self-Learning & Optimization** (reflection loops, self-refine, DSPy-style optimization, skill generation pipeline) — adaptive threshold tuning started (self_learning_thresholds).
- [ ] **Phase 5 — Publications & Commerce** (autoposting, payments, evidence packs) — pending.
- [ ] **Phase 6 — Security, Cost, Observability** (gateway, guardrails, tracing, governance reports) — pending.
- [ ] **Phase 7 — Tooling Standards (MCP/OpenAPI)** (contracts, signed releases, tooling governance) — pending.

## Ongoing Actions
- Maintaining automated owner preference tracking.
- Preserving durable orchestration context while adding new phases.
- Running targeted tests (`tests/test_memory_manager.py`, `tests/test_memory_skill_reports.py`, `tests/test_orchestration_manager.py`) when components change.
