# VITO Remediation Plan (Audit 03.03.2026)

## Goal
Close critical audit gaps and bring VITO from "foundation-only" to stable command execution with verifiable outcomes.

## Progress
- Overall: 99%
- Package P0 (critical security/reproducibility): 100%
- Package P1 (core architecture hardening): 100%
- Package P2 (ops/tooling maturity): 100%
- Package P3 (platform depth and autonomy): 98%

## Package P0 — Critical (Done)
- [x] Replace unsafe `AGENT_SYSTEM_PREAMBLE` with strict trust-boundary preamble.
- [x] Remove `allow_protected=True` bypass in self-improve pipeline.
- [x] Add reproducible dependency file: `requirements.txt`.
- [x] Remove tracked binary/runtime artifacts from git index:
  - `memory/vito_memory.db`
  - `output/ai_side_hustle_cover_1280x720.png`
  - `output/ai_side_hustle_thumb_600x600.png`
- [x] Strengthen `.gitignore` for db/images.

## Package P1 — Core Hardening (In Progress)
- [x] Implement relevance re-rank in memory search:
  - semantic + recency + importance scoring in `search_knowledge`.
- [x] Introduce centralized `PROJECT_ROOT` path layer (`config/paths.py`).
- [x] Migrate key runtime/config modules from hardcoded paths to `PROJECT_ROOT`.
- [x] Migrate remaining hardcoded paths in secondary modules/scripts.
- [x] Add migration lint/check to block new hardcoded root paths (`scripts/check_hardcoded_paths.py` + CI gate).

## Package P2 — DevOps & Reproducibility (In Progress)
- [x] Add `Dockerfile`.
- [x] Add `docker-compose.yml`.
- [x] Add GitHub Actions CI workflow for critical test suites.
- [x] Add smoke CI job for startup (`main.py` import/init).

## Package P3 — Functional Depth (In Progress)
- [x] Implement deterministic command router for top owner intents (status/network/trends/gumroad analytics).
- [x] Add evidence-first completion contract across action outputs (`[status=...]` markers).
- [x] Complete Etsy OAuth2 PKCE write path (platform + token persistence + refresh + tests).
- [x] Replace/upgrade thin agents with tool/API-backed logic (SEO/Translation/Marketing first).
- [x] Consolidate Gumroad support entrypoint: `scripts/gumroad_pipeline.py` (single supported pipeline CLI).
- [x] Acceptance test matrix for "owner command -> execution -> evidence" (`docs/ACCEPTANCE_COMMAND_MATRIX_2026-03-03.md`).

## Exit Criteria for "Ready"
- 95%+ pass on acceptance command suite (real owner phrases with typos/mixed language).
- No unverified completion claims.
- Stable platform auth for Gumroad + Etsy.
- All critical tasks produce machine-verifiable evidence.
