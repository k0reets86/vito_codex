# VITO Execution Roadmap (0% -> 100%)
Status: ACTIVE
Owner: VITO Core + Owner
Linked strategy:
- `docs/VITO_AGI_ENHANCEMENT_PLAN_2026-03-06.md`
- `docs/PLAN_SKILL_EXPANSION_2026-02-25.md`
- `docs/BOEVOY_TEST_MASTER_PLAN_2026-03-02.md`

## Execution Rule
- Work in large packages, not micro-fixes.
- Do not optimize one agent in isolation unless the package also updates:
  - its collaboration rules,
  - its memory contract,
  - its orchestration role,
  - its test path.
- Every package must leave the system more integrated than before.
- Progress must be tracked by package completion percentage, not by raw commit count.

## Global Outcome
Move VITO from partially autonomous multi-agent system to a controlled quasi-AGI operator that:
- understands owner intent from Telegram naturally,
- routes work across 23 agents correctly,
- learns new capabilities,
- heals failures safely,
- remembers successful and failed runbooks,
- executes browser-first real-world tasks with evidence,
- stays efficient on token usage.

## Package Structure

### Package 1 — Agent Foundation Rebuild
Progress band: `0% -> 20%`

Goal:
- Rebuild the internal operating layer for all 23 agents so they behave as coordinated units, not just labels.

Scope:
- Skill Matrix v2 foundation:
  - `service skills`
  - `helper skills`
  - `persona skills`
  - `recipe skills`
- Unified agent contract for all 23 agents:
  - role
  - owned outcomes
  - required evidence
  - allowed tools
  - collaboration graph
  - memory inputs/outputs
  - escalation rules
- Orchestration map:
  - which agent leads each major workflow
  - which agents are support roles
  - who acts as final verifier

Definition of done:
- Every agent has explicit runtime contract.
- Skill taxonomy exists in code/config, not just in docs.
- Cross-agent collaboration map is wired into orchestration path.
- No owner-critical workflow is left without a responsible final checker.

Key risk if skipped:
- isolated upgrades will keep breaking each other.

### Package 2 — Memory / Anti-Memory v2
Progress band: `20% -> 40%`

Goal:
- Make VITO actually reuse experience instead of just storing it.

Scope:
- Split memory into:
  - owner memory
  - skill memory
  - runbook memory
  - anti-pattern memory
  - platform memory
  - workflow state memory
- Retrieval re-ranking by:
  - semantic relevance
  - freshness
  - importance
  - task family
  - prior success/failure rate
- Inject memory into planning and execution automatically.
- Add working-object persistence for platforms:
  - one draft/listing/post per test flow

Definition of done:
- Memory retrieval affects live execution decisions.
- Failed paths are stored and consulted before retries.
- Successful runbooks are preferred in repeated tasks.

Key risk if skipped:
- VITO keeps relearning and repeating mistakes.

### Package 3 — Self-Learning v2
Progress band: `40% -> 58%`

Goal:
- Close the loop from “missing capability” to “usable new skill”.

Scope:
- Source intake:
  - official docs
  - GitHub
  - curated forum/community sources
- Candidate skill generation
- Skill benchmark harness
- Skill grader / comparator / analyzer pipeline
- Skill acceptance and promotion path
- Automatic attachment of promoted skill to responsible agent(s)

Definition of done:
- VITO can propose, test, score, and promote a new skill with evidence.
- Skill promotion is blocked if tests/evidence are weak.
- Anti-skill memory is created for failed implementations.

Key risk if skipped:
- “Self-learning” stays conceptual, not operational.

### Package 4 — Self-Healing v2
Progress band: `58% -> 72%`

Goal:
- Make VITO capable of repairing failures safely and repeatably.

Scope:
- Structured failure capture
- Root-cause classification
- Safe remediation candidates
- Sandbox test run
- Judge gate
- Rollback / promote logic
- Failure lesson persistence into anti-memory

Definition of done:
- A failure can produce a tested remediation path.
- Unsafe commands are blocked or escalated.
- Successful fixes become reusable repair runbooks.

Key risk if skipped:
- healing remains dangerous or ineffective.

### Package 5 — Browser Autonomy v2 + Telegram Owner OS v2
Progress band: `72% -> 88%`

Goal:
- Make owner interaction and browser execution behave like one coherent operating system.

Scope:
- Browser auth broker:
  - cookie/session import
  - TTL
  - verification
  - fallback routes
- Anti-detection runtime improvements
- One-working-object-per-platform enforcement
- Telegram owner OS:
  - natural intent resolution
  - service-context carryover
  - reply-to-message context
  - zero technical spam mode
  - result-contract replies

Definition of done:
- Telegram commands drive real multi-agent execution.
- Browser-first services use stable working objects and verified state.
- Owner sees human-readable outcomes, not system noise.

Key risk if skipped:
- VITO remains technically capable but operationally frustrating.

### Package 6 — System Integration + Bоевoy Validation
Progress band: `88% -> 100%`

Goal:
- Prove the whole system works as one organism.

Scope:
- Cross-agent integration tests
- End-to-end Telegram owner simulations
- Browser-first platform scenarios
- Research -> create -> publish -> analyze loops
- Cleanup, knowledge capture, commits, final audit

Definition of done:
- Major workflows are verified end-to-end with evidence.
- Agent collaboration works under realistic Telegram-driven scenarios.
- Failures are documented into anti-memory; successes into skill/runbook memory.

Key risk if skipped:
- architecture improves, but real autonomy remains unproven.

## Cross-Package Invariants
- No package may weaken owner control.
- No package may increase technical Telegram spam.
- No package may add uncontrolled token usage.
- No package may promote unverified skills into live execution.
- No package may claim success without evidence.

## Execution Order (Strict)
1. Package 1
2. Package 2
3. Package 3
4. Package 4
5. Package 5
6. Package 6

## Progress Tracking
- `0%` start
- `20%` Package 1 done
- `40%` Package 2 done
- `58%` Package 3 done
- `72%` Package 4 done
- `88%` Package 5 done
- `100%` Package 6 done

## Current Status
- Current active package: `Package 6 — System Integration + Bоевoy Validation`
- Current global progress: `88%`

## Latest Delivered Foundation
- Package 1 core is now wired in code:
  - unified operational contracts for all 23 agents
  - Skill Matrix v2 rebuilt on top of contracts instead of loose heuristics
  - workflow map derived from contract roles (`lead/support/verify`)
  - registry runtime now injects contract + focused memory context into execution
  - dashboard exposes `/api/agent_contracts` and richer `/api/agents`
- Package 2 has started:
  - agent-focused memory retrieval added (`get_agent_memory_context`)
  - memory blocks can now be queried by agent/domain
  - runtime can pass agent-specific memory context into task execution
  - playbook lookup now prefers higher-success strategies for the responsible agent/task
  - platform knowledge is searchable and injected into agent memory context
- Package 3 delivered:
  - self-learning lessons/candidates now track `source_agent`, `domain_role`, and structured evidence
  - candidate optimization uses agent playbook success and recent failure pressure
  - promotion evidence now preserves responsible agent/domain context
  - self-learning summary now shows source-agent learning distribution
- Package 4 delivered:
  - runtime remediation events now persist `source_agent`, `task_family`, and `source`
  - failure-aware safe-action planner added for security/tooling/cost/self-learning/revenue incidents
  - self-healer now returns and escalates structured safe-action suggestions
- Package 5 delivered:
  - Telegram reply-to now restores service context before conversation processing
  - owner task state now persists and enriches `service_context`
  - service context is visible in owner focus/status output across comms + conversation engine
