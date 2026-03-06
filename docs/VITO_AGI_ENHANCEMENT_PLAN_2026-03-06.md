# VITO AGI Enhancement Plan (2026-03-06)
Status: ACTIVE
Owner: VITO Core + Owner
Sources:
- Local audit: `input/inbox/screenshots/VITO_AUDIT_2026.docx`
- Skill design guide: `input/inbox/screenshots/Skill_Creator_Guide_RU.pdf`
- OpenClaw skills digest: `input/inbox/screenshots/OpenClaw_Skills_UseCases_RU (1).pdf`
- OpenClaw / ClawHub public materials on GitHub

## Why This Plan Exists
The current master roadmap is still valid, but it is too general for the next jump.
This document narrows the next strategic layer:
- make VITO more autonomous than OpenClaw,
- keep token discipline,
- preserve safety and operator control,
- move toward quasi-AGI behavior through memory, skills, self-learning, self-healing, and real multi-agent execution.

## Ground Truth After Review

### 1. What the local VITO audit got right
- Strong modular architecture, durable orchestration, memory layers, and operator controls are real strengths.
- The main weaknesses are not "lack of modules", but uneven maturity:
  - some agents are still thin LLM wrappers,
  - memory relevance and skill reuse are not yet fully closed-loop,
  - self-healing is promising but still too open-ended,
  - live platform execution is much weaker than internal architecture.

### 2. What must be corrected from the local audit
- Etsy cannot currently be treated as API-first for practical execution.
  Browser-first is the current real path.
- "More providers/models" is not the same as "more intelligence".
  The next gain comes from better skill/runtime orchestration, not from adding expensive models.

### 3. What OpenClaw is genuinely strong at
- Huge skill surface area and breadth of integrations.
- Fast install/use pattern for specialized skills.
- Strong bias toward practical tool execution.
- Wide ecosystem coverage across dev, browser, cloud, docs, commerce, media, voice, IoT, calendar, finance, PDF, security.

### 4. What OpenClaw does worse than VITO must do
- Too much breadth without enough execution discipline.
- Token waste risk from over-triggering skills.
- Safety/governance is weaker than required for owner-grade autonomous operation.
- Skills breadth does not automatically produce high-quality orchestration, evidence, or business reliability.

## Strategic Decision
VITO should not try to "be OpenClaw with more skills".
VITO should become:
- narrower in activation,
- stronger in evidence,
- deeper in execution,
- safer in autonomy,
- better at learning from successful and failed runs,
- more operator-friendly through Telegram.

## What We Borrow From OpenClaw

### A. Skill Matrix v2
Borrow:
- large categorized skill registry idea,
- installable/reusable skill packs,
- explicit domain coverage map.

Adapt for VITO:
- service skills: per platform/service runbooks and contracts,
- helper skills: deterministic utility flows (auth, parsing, packaging, evidence capture),
- persona skills: agent-specific behavior packs,
- recipe skills: end-to-end workflows.

Improvement for VITO:
- every skill must have:
  - trigger description,
  - evidence contract,
  - cost profile,
  - risk level,
  - tests,
  - owner-safe activation rules.

Why this beats OpenClaw:
- fewer accidental activations,
- less token waste,
- stronger repeatability.

### B. Skill Creator discipline
Borrow:
- benchmark-driven skill creation,
- blind comparison,
- analyzer/grader/comparator loop,
- iterative description tuning.

Adapt for VITO:
- every new or updated skill goes through:
  - benchmark prompts,
  - baseline vs skill comparison,
  - factual grader,
  - trigger precision check,
  - owner-facing readiness flag.

Improvement for VITO:
- store skill failures and anti-patterns in memory,
- attach platform-specific success/failure evidence,
- allow promotion only after passing tests and evidence rules.

Why this beats OpenClaw:
- not just many skills, but measurable skill quality.

### C. Wide domain coverage
Borrow:
- domain breadth map from OpenClaw categories.

Adapt for VITO:
- keep business-first priority order:
  - commerce,
  - publishing,
  - research,
  - marketing,
  - analytics,
  - operator workflow,
  - then broader utility domains.

Improvement for VITO:
- no "skill sprawl".
- new domains enter only if they improve owner outcomes, autonomy, or infrastructure resilience.

## What We Do Not Borrow
- Unbounded skill triggering.
- Weak evidence rules.
- Token-heavy behavior that calls LLMs before deterministic tools.
- Unsafe broad tool access by default.
- Illusion of completion without live proof.

## Target State for VITO

### Layer 1. VITO Core as AGI-like orchestrator
VITO Core must:
- understand owner intent from messy natural language,
- hold multi-turn context reliably,
- choose the responsible agent,
- request sub-work from other agents only when needed,
- synthesize final output,
- route verification to the right checker,
- store success/failure patterns back into memory.

Required upgrades:
- intent graph instead of keyword-only interpretation,
- service-context carryover in dialogue,
- owner state + task state + service state unified in one context object,
- final answer discipline: one responsible result owner per workflow.

### Layer 2. Agent maturity upgrade
Every one of the 23 agents must move from "role label" to "operational unit".

Required per-agent standard:
- role contract,
- domain memory,
- allowed tools,
- evidence rules,
- collaboration map,
- skill packs,
- quality criteria,
- anti-pattern memory,
- escalation rules.

Priority agents to deepen first:
- ecommerce_agent
- publisher_agent
- research_agent
- seo_agent
- smm_agent
- legal_agent
- risk_agent
- hr_agent
- quality_judge

### Layer 3. Memory that is actually read and reused
Current direction is good but incomplete.

Need:
- memory retrieval weighted by:
  - semantic match,
  - freshness,
  - owner relevance,
  - task family,
  - prior success rate,
  - platform recency.
- separate stores for:
  - owner preferences,
  - execution runbooks,
  - skill lessons,
  - anti-patterns,
  - platform constraints,
  - active workflows.

Critical rule:
- memory is not a warehouse.
- memory must be injected into planning/execution automatically when relevant.

### Layer 4. Self-learning loop
Need a fully closed loop:
1. detect missing capability,
2. research trusted sources,
3. draft candidate skill/runbook,
4. benchmark it,
5. verify on safe test path,
6. promote if evidence is good,
7. attach to responsible agent,
8. reuse automatically later.

Required safeguards:
- no promotion from a single anecdotal success,
- no direct live rollout without acceptance gate,
- anti-skill memory when implementation path failed.

### Layer 5. Self-healing loop
Need VITO to fix itself, but not recklessly.

Required shape:
- failure capture,
- cause classification,
- candidate remediation generation,
- deterministic tests,
- judge gate,
- rollout or rollback,
- lesson recording.

Required restriction:
- command allowlists and risk classes,
- patch sandboxing first,
- no silent unsafe shell actions.

### Layer 6. Browser-first autonomy
This is one of the biggest differentiators for VITO.

Need:
- browser auth broker for all browser-first services,
- cookie/session import and refresh path,
- service-specific login verification,
- reusable working object per platform,
- anti-detection runtime,
- evidence screenshots and DOM traces,
- stable create/edit/publish/delete lifecycle.

Important principle:
- browser runtime must behave like a careful operator, not a blind clicker.

### Layer 7. Telegram as primary owner OS
Telegram is not just a chat.
For this project it is the owner operating console.

Need:
- natural language intent resolution,
- reply-to-message context support,
- zero technical spam in normal mode,
- structured reports only when useful,
- platform-aware context carryover,
- task acceptance -> silent execution -> verified result.

### Layer 8. Token discipline
This is a first-class design principle.

Policy:
- deterministic code/tool checks first,
- cached memory second,
- Gemini free stack for routine cognition,
- stronger paid models only for explicitly high-value stages,
- no repeated summarization of the same material,
- no skill-trigger loops.

## New Workstreams

### Workstream A — Skill Matrix v2
Deliverables:
- unified skill taxonomy: service/helper/persona/recipe,
- per-agent skill ownership map,
- trigger precision tests,
- skill benchmark harness,
- skill acceptance registry.

Expected effect:
- cleaner agent specialization,
- less duplicate logic,
- better reuse,
- lower token burn.

### Workstream B — Agent Runtime Deepening
Deliverables:
- operational contracts for all 23 agents,
- collaboration graph,
- responsible-agent finalization pattern,
- per-agent domain memory packs,
- per-agent improvement backlog.

Expected effect:
- agents stop acting like labels,
- workflows become real multi-agent execution chains.

### Workstream C — Memory/Anti-Memory v2
Deliverables:
- success runbooks,
- anti-pattern memory,
- retrieval re-ranking,
- service-context memory,
- "working object" persistence for platform flows.

Expected effect:
- fewer repeated mistakes,
- less relearning,
- more continuity across sessions.

### Workstream D — Self-Learning / Skill Discovery v2
Deliverables:
- external source scanner,
- candidate skill proposer,
- benchmark runner,
- readiness score,
- agent attachment logic.

Expected effect:
- VITO learns missing capabilities instead of stalling.

### Workstream E — Self-Healing / Judge Pipeline v2
Deliverables:
- failure classifier,
- safe patch candidate flow,
- judge gate,
- anti-regression suite,
- rollback ledger.

Expected effect:
- higher autonomous resilience without unsafe drift.

### Workstream F — Browser Autonomy v2
Deliverables:
- auth broker with TTL and verification,
- cookie import/export pipeline,
- browser anti-detection runtime,
- stable per-platform create/edit/publish flows,
- evidence capture layer.

Expected effect:
- real operational autonomy on blocked/no-API platforms.

### Workstream G — Telegram Owner OS v2
Deliverables:
- intent resolver,
- service-context carryover,
- reply-chain understanding,
- human-style responses,
- silent long-run mode,
- result contracts for owner-facing output.

Expected effect:
- VITO becomes actually usable as owner assistant, not just internally impressive.

## Immediate Priority Order
1. Preserve and stabilize one-working-object-per-platform execution model.
2. Finish Skill Matrix v2 foundation.
3. Deepen agent runtime contracts for the commerce/publishing stack.
4. Complete memory/anti-memory v2 retrieval integration.
5. Deliver self-learning benchmark loop based on Skill Creator discipline.
6. Deliver self-healing judge pipeline.
7. Expand browser autonomy and anti-detection safely.
8. Only after that widen domain/skill surface.

## Success Criteria
- VITO executes better than OpenClaw in owner-critical workflows:
  - clearer intent understanding,
  - lower token cost,
  - safer autonomy,
  - stronger memory reuse,
  - better verified execution,
  - cleaner multi-agent coordination.
- VITO learns and reuses skills instead of re-solving from scratch.
- Telegram interaction feels natural while remaining operator-safe.
- Platform actions are real, evidenced, and repeatable.

## Notes
- OpenClaw is the benchmark for breadth.
- VITO must beat it on depth, control, evidence, and practical autonomy.
- Breadth expansion only makes sense after execution quality is hardened.
