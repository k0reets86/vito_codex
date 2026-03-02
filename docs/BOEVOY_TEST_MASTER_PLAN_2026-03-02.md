# BOEVOY End-to-End Test Master Plan (Gemini-only First)

Status: ACTIVE  
Owner: VITO + Owner  
Mode: Gemini-only (`LLM_FORCE_GEMINI_FREE=true`, `LLM_FORCE_GEMINI_MODEL=gemini-2.5-flash`)

## Rules
- One scenario at a time: no parallel manual tests.
- Every scenario must produce evidence: command output, log lines, DB state, result screenshot/link if applicable.
- No paid multi-model/expensive modules in this phase.
- Self-healer and brainstorm deep tests are postponed to late phase.

## Phase Order
1. Runtime Baseline & Safety Gates
2. Core Dialogue + Task Lifecycle
3. Orchestration + Approvals + Resume/Cancel
4. Memory + Skills + Preferences
5. Tooling/Registry/Discovery (safe mode)
6. Publishing/Platform Dry-Run Flows (postings, registrations with test/sandbox accounts)
7. Revenue/Finance/Observability
8. Deferred modules: self-healer + brainstorm stress tests
9. Provider Expansion: connect remaining keys/services, then restore full router strategy

## Definition of Done (global)
- All checklist items in `docs/BOEVOY_TEST_CHECKLIST_2026-03-02.md` are marked done or explicitly deferred with reason.
- No restart loops / no spam loops / no unbounded queues.
- Evidence is captured for every major module.
- Final smoke run passes after re-enabling full provider router.

## Session Discipline
- At the start of each session: read this file + checklist file first.
- Update checklist and global progress after every completed scenario.
- Report progress to owner in percent after each scenario.
