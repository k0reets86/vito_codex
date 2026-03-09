# VITO Must-Have Execution Plan — 2026-03-09

Статус: MANDATORY

Это не список пожеланий. Это обязательный план, от которого нельзя отходить, пока каждый пункт не реализован и не подтвержден тестами.

## 1. Execution Invariants First

### 1.1 Hard object protection
- Published/live/protected objects never auto-edit.
- Any update requires explicit `target_id` or same `task_root_id`.
- No fallback to "last existing object".

### 1.2 One object per task
- One platform object per platform per `task_root_id`.
- After first create, platform enters `update-only` mode.
- Second create inside same task must hard-fail.

### 1.3 Platform-specific Definition of Done
For every platform keep executable contract:
- required text fields
- required media fields
- required file fields
- required category/tags/attributes
- required evidence
- reload verification
- public/editor verification

Without all of these the result is `not_done`.

## 2. Telegram as Command Compiler, not chat

### 2.1 Rule-first parse
The TG layer must resolve before free reasoning:
- number choice
- platform name
- target id
- continue/stop/update/create verbs
- owner approval / 2FA / payment-risk states

### 2.2 Structured parser
Gemini or another model must output strict schema:
- intent
- platform
- task_family
- selected_option
- target_policy
- risk_level
- needs_confirmation

### 2.3 Runbook resolver
No free-form platform reasoning after parse.
Only:
- choose runbook
- attach task_root_id
- attach invariants
- execute
- verify

## 3. Platform Knowledge must become executable

For each platform store not only notes, but executable runbook packs:
- create path
- update path
- publish path
- delete/archive path
- screenshot map
- selector map
- anti-patterns
- required final checks
- known external gates

Priority order:
1. Etsy
2. Gumroad
3. Printful -> Etsy
4. KDP ebook/paperback/hardcover
5. Ko-fi
6. Pinterest
7. X
8. Reddit

## 4. Mandatory Final Verifier

Introduce a dedicated final verifier stage:
- not adapter status
- not optimistic recipe status
- only `screenshot + reload + DOM/state + URL + evidence`

This verifier must sit above:
- platform adapter
- ecommerce agent
- publisher queue
- vito_core final response

## 5. Weak-agent strengthening order

### Tier 1
- browser_agent
- ecommerce_agent
- account_manager
- vito_core

### Tier 2
- document_agent
- hr_agent
- devops_agent

For each weak agent:
- real capability contract
- memory inputs/outputs
- anti-patterns
- failure causes
- fixed benchmark tasks
- pass threshold

## 6. Self-learning must promote runtime behavior, not notes

Required:
- lesson -> candidate -> test -> promotion -> enforcement
- promoted lesson must alter runtime route or gate
- lessons that do not change execution behavior do not count as learning success

## 7. Self-healing must target browser/platform execution too

Required:
- detect repeated browser failure signatures
- suggest alternate save path / alternate route / alternate editor
- test in sandboxed verify mode
- promote only if verified

## 8. Test policy

### 8.1 Every meaningful package must have
- unit tests
- regression tests
- at least one scenario test

### 8.2 Required recurring scenarios
- owner noisy TG scenario
- owner live platform scenario
- duplicate prevention scenario
- protected object scenario
- no-file/no-media false-success scenario

### 8.3 Stop condition
No package is complete until:
- code passes
- scenario passes
- evidence exists
- checklist updated

## 9. External implementation references

Use these as architectural reference points, not as cargo cult:
- LangGraph persistence and durable execution:
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/langgraph/durable-execution
- Temporal workflow execution:
  - https://docs.temporal.io/workflow-execution
- Rasa assistant memory / flows:
  - https://rasa.com/docs/pro/build/assistant-memory/
  - https://rasa.com/docs/pro/build/writing-flows/
- Gemini structured output:
  - https://ai.google.dev/gemini-api/docs/structured-output
- Anthropic effective agents:
  - https://www.anthropic.com/engineering/building-effective-agents
- MCP tool contracts / scoping:
  - https://modelcontextprotocol.io/docs/concepts/tools

## 10. What not to do anymore

- No early "done" on partial listing.
- No mixing simulator success with platform success.
- No implicit reuse of old objects.
- No new platform expansion before execution discipline is stronger.
- No treating knowledge logs as completed runtime learning.

## 11. Immediate next mandatory sequence

1. Clean and commit current enforcement + audit package.
2. Freeze platform DoD contracts for Etsy and Gumroad in executable form.
3. Add final verifier stage above adapter/agent/core.
4. Re-audit weak agents with fixed benchmark tasks.
5. Re-run live platform scenarios only after the verifier is in place.
6. Only then return to broad owner TG live tests.
