# Capability Pack Spec v1 (2026-02-25)

## Goal
Standardize how new skills are defined, tested, and accepted.

## Structure
Each capability pack must include:
- `spec`: name, category, description, inputs/outputs, risk, cost
- `adapter`: implementation glue (tools/platforms)
- `tests`: unit + integration + smoke (+ E2E when possible)
- `evidence`: execution facts (logs/paths/urls)

## Required Fields
- name
- category
- inputs
- outputs
- version
- risk_score (0..1)
- tests_coverage (0..1)
- acceptance_status (pending/accepted/rejected)
- evidence (path/url/id)

## Acceptance Rules
- Tests must pass
- Evidence must be recorded
- Owner approval required if risk >= medium

## Registry Mapping
- Stored in `skill_registry`
- Tests discovered via `tests/` naming
- Evidence stored in `execution_facts`

## Scaffold Script
Use `scripts/create_capability_pack.py <name> <category>` to generate a pack skeleton.

## Sync Script
Use `scripts/sync_capability_packs.py [root]` to register packs into SkillRegistry.

## Report Script
Use `scripts/capability_pack_report.py` to generate a pack status report.

## Run Script
Use `scripts/run_capability_pack.py <name> [json_input]` to execute a pack.

## Validation Script
Use `scripts/validate_capability_packs.py` to validate required fields.

## Acceptance Script
Use `scripts/accept_capability_packs.py --tests-passed --evidence <report>` to accept pending packs.

## Runtime Gate
By default, pending packs are blocked at runtime unless `CAPABILITY_PACK_ALLOW_PENDING=true`.

## Manual Event Script
Use `scripts/register_capability_pack_event.py <name> --status <success|failed>` for manual logging.
