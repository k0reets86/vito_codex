# VITO Agent Uplift Package 3 Report — 2026-03-10

## Scope

Priority packages:
- `Package 3 — Outcome-Changing Collaboration`
- partial `Package 4 — Commerce Execution Hardening`

Covered runtime areas:
- workflow collaboration assertions
- degraded outcome on missing required support/verify agents
- ecommerce/publisher runtime profiles
- collaboration-aware benchmark rerun

## What changed

### Runtime workflow layer
- [agent_workflow_runtime.py](/home/vito/vito-agent/modules/agent_workflow_runtime.py)
  - added `WORKFLOW_COLLAB_ASSERTIONS` for `W01-W08`
  - runtime now computes:
    - `required_agents`
    - `required_verify_agents`
    - `observed_agents`
    - `missing_agents`
    - `missing_verify_agents`
    - `degraded`
  - workflow `success` now hard-fails on degraded collaboration
  - added safe attribution fallback `capability -> single registered agent` so collaboration traces do not disappear after downstream verify-fail

### Commerce runtime layer
- [commerce_runtime.py](/home/vito/vito-agent/modules/commerce_runtime.py)
  - listing runtime profile
  - publisher runtime profile

### Agent behavior changes
- [ecommerce_agent.py](/home/vito/vito-agent/agents/ecommerce_agent.py)
  - emits `listing_runtime_profile`
  - returns structured collaboration/evidence metadata on both success and verifier-gated failure
- [publisher_agent.py](/home/vito/vito-agent/agents/publisher_agent.py)
  - emits `publisher_runtime_profile`
  - success outputs consistently carry `handled_by`

### Tests adjusted to real contracts
- [test_agent_workflow_runtime.py](/home/vito/vito-agent/tests/test_agent_workflow_runtime.py)
  - workflow doubles upgraded to satisfy current fail-closed runtime contracts
- [test_ecommerce_agent.py](/home/vito/vito-agent/tests/test_ecommerce_agent.py)
- [test_publisher_agent.py](/home/vito/vito-agent/tests/test_publisher_agent.py)

## Validation

Targeted tests:
- `30 passed`

Full reruns:
- megatest: [VITO_AGENT_MEGATEST_2026-03-10_0022UTC.json](/home/vito/vito-agent/reports/VITO_AGENT_MEGATEST_2026-03-10_0022UTC.json)
- benchmark: [VITO_AGENT_BENCHMARK_MATRIX_2026-03-10_0023UTC.json](/home/vito/vito-agent/reports/VITO_AGENT_BENCHMARK_MATRIX_2026-03-10_0023UTC.json)

## Result

What improved:
- collaboration discipline is now runtime-enforced, not descriptive
- missing support/verify agents can degrade workflow success deterministically
- ecommerce/publisher outputs are more operationally inspectable

What did not improve yet:
- overall benchmark remained `7.52`
- `commerce_execution` remained `7.88`, still below target `8.0`

Why score did not move:
- the package mostly hardened orchestration truthfulness and collaboration enforcement
- benchmark bottleneck is now concentrated in:
  - `publisher_agent` recovery depth
  - `vito_core` recovery/collaboration depth
  - `ecommerce_agent` recovery depth

## Next priority

1. deepen `publisher_agent` recovery/runtime evidence
2. deepen `ecommerce_agent` recovery paths beyond verifier output shaping
3. improve `vito_core` responsibility/recovery behavior
4. rerun benchmark until `commerce_execution >= 8.0`
