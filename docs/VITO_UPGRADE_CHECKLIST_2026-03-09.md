# VITO Upgrade Checklist — 2026-03-09

Правило ведения:
- После каждого завершенного этапа показывать владельцу:
  - что сделано
  - что осталось
  - общий прогресс в процентах
- Статусы только:
  - `not_started`
  - `in_progress`
  - `done`
  - `paused_blocked`

Общий прогресс: `58%`

## Phase A — Execution Guardrails + Final Verifier
- [x] Hard object protection для всех platform adapters
- [x] Task-root hard binding везде
- [x] No implicit fallback to existing objects
- [x] Platform DoD contracts in code
- [x] Final verifier above adapter/agent/core
- [x] Regression tests on false done / duplicate create / protected objects
- Status: `done`
- Weight: `18%`

## Phase B — Telegram Command Compiler
- [x] Отдельный Telegram NLU Router module
- [x] Rule-first parse
- [x] Gemini 2.5 Flash structured parser
- [x] Context window + fuzzy matching
- [x] Clarification mode
- [x] Response normalization
- [x] Noisy TG regressions
- Status: `done`
- Weight: `14%`

## Phase C — Memory That Governs Runtime
- [x] Unified memory layers map
- [x] Executable platform runbook packs
- [x] Relevance/reranking activated everywhere needed
- [x] Error stores consolidation
- [x] mem0 feasibility decision and integration plan
- [x] Lessons must mutate runtime behavior
- Status: `done`
- Weight: `14%`

## Phase D — Deep Research Engine
- [x] Iterative research loop
- [x] raw/synthesis/judge split
- [x] Full research artifact persistence
- [x] Top ideas + score + risks + platform recommendation
- [x] TG delivery of condensed + full report
- Status: `done`
- Weight: `12%`

## Phase E — MegaBrowser 2.0
- [ ] Screenshot-first maps for brittle flows
- [ ] Multi-profile/session isolation
- [ ] Humanization/anti-bot strategy
- [ ] OTP/2FA interrupt protocol normalized
- [ ] Profile completion runbooks
- [ ] Browser stack evaluation (including patchright path)
- Status: `not_started`
- Weight: `12%`

## Phase F — Agent Specialization and Collaboration
- [ ] Collaboration map for all 23 agents
- [ ] Owned outcomes / evidence contracts per agent
- [ ] Weak-agent hardening tier 1
- [ ] Weak-agent hardening tier 2
- [ ] Fixed benchmark tasks per agent
- Status: `not_started`
- Weight: `12%`

## Phase G — Self-Healing and Safe Upgrades
- [ ] Failure signatures to remediation candidates
- [ ] Verify mode for remediations
- [ ] Promotion only after proof
- [ ] SelfHealer <-> DevOpsAgent hard wiring audited
- [ ] Safe tool allowlist expansion where justified
- Status: `not_started`
- Weight: `8%`

## Phase H — Full Combat Validation
- [ ] Safe regression pack
- [ ] Noisy TG pack
- [ ] Live owner platform pack
- [ ] Duplicate protection pack
- [ ] Protected object pack
- [ ] 23-agent benchmark audit rerun
- Status: `not_started`
- Weight: `10%`
