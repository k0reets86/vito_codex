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

Общий прогресс: `100%`

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
- [x] Screenshot-first maps for brittle flows
- [x] Multi-profile/session isolation
- [x] Humanization/anti-bot strategy
- [x] OTP/2FA interrupt protocol normalized
- [x] Profile completion runbooks
- [x] Browser stack evaluation (including patchright path)
- Status: `done`
- Weight: `12%`

## Phase F — Agent Specialization and Collaboration
- [x] Collaboration map for all 23 agents
- [x] Owned outcomes / evidence contracts per agent
- [x] Weak-agent hardening tier 1
- [x] Weak-agent hardening tier 2
- [x] Fixed benchmark tasks per agent
- Status: `done`
- Weight: `12%`

## Phase G — Self-Healing and Safe Upgrades
- [x] Failure signatures to remediation candidates
- [x] Verify mode for remediations
- [x] Promotion only after proof
- [x] SelfHealer <-> DevOpsAgent hard wiring audited
- [x] Safe tool allowlist expansion where justified
- Status: `done`
- Weight: `8%`

## Phase H — Full Combat Validation
- [x] Safe regression pack
- [x] Noisy TG pack
- [x] Live owner platform pack
- [x] Duplicate protection pack
- [x] Protected object pack
- [x] 23-agent benchmark audit rerun
- Status: `done`
- Weight: `10%`
