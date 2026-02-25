# Capability Pack Execution Spec v1 (2026-02-25)

## Goal
Standardize runtime gating and execution of capability packs.

## Runtime Gate
- Default: pending packs are blocked.
- Override: `CAPABILITY_PACK_ALLOW_PENDING=true`.

## Execution
- All pack executions are recorded to DataLake.
- Pack adapters should return `{status: ok|error, output|error}`.

## Safety
- Pack adapters must not bypass owner approval or cost guards.
- Pack adapters should be low‑risk stubs until fully tested.

