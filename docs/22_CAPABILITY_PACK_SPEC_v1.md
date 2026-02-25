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

