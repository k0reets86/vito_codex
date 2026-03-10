# VITO Deep Audit v5 Plan

Источник:
- `input/attachments/VITO DEEP AUDIT v5.docx`
- текущее состояние репозитория на `2026-03-10`

Статус: `MANDATORY`

## Правило исполнения
Ни один пункт из аудита не может быть самовольно снят, уменьшен или пропущен.
Допустимые статусы только такие:
- `done` — реализовано и проверено
- `partial` — частично реализовано, нужен следующий пакет
- `not_done` — не реализовано
- `blocked_policy` — не реализуется только из-за прямого policy-ограничения

## Цель
Закрыть все actionable замечания из `Deep Audit v5` так, чтобы:
1. память стала реально семантической и эпизодической, а не текстовой;
2. самолечение замыкало петлю `error -> patch -> verify -> apply`;
3. агентные события и знания переживали рестарт;
4. браузерный слой стал умнее и ближе к page-understanding;
5. автономность перешла от `L2 partial` к устойчивому `L3 groundwork`;
6. интеграционные стабы стали operational adapters там, где это допустимо.

## V5-A — Memory / Retrieval
1. `search_episodes()` -> pgvector + embedding persistence
2. `SkillLibrary.retrieve()` -> semantic merge
3. `Reflector.top_relevant()` -> semantic/reranked retrieval
4. cross-layer retrieval plan
5. `Knowledge Graph` groundwork
6. `mem0` evaluation/integration path

## V5-B — Healing / Evolution
1. `PatchGenerator` wired into `_handle_runtime_error`
2. `record_lesson()` pervasive agent path
3. `AutonomyOverseer.execute_actions()` runtime loop
4. `SelfHealerV2` full patch-generation loop
5. agent health monitoring / repeated failure awareness

## V5-C — Eventing / Orchestration
1. `AgentEventBus` SQLite persistence
2. `decision_loop` background fan-out review (`_maybe_run_*` sequential bottleneck)
3. `LangGraph` parallel orchestration evaluation / integration plan
4. `conversation_engine` / `comms_agent` decomposition continuation

## V5-D — Browser / Platform Runtime
1. Gumroad runtime through shared browser policy, not direct raw playwright path
2. `LLM navigation` / screenshot->action groundwork in BrowserAgent
3. service session persistence across restarts review
4. `patchright` owner-grade rollout continuation

## V5-E — Platform / Capability Expansion
1. `capability_packs` from stubs to real runtime logic
2. Instagram operational path (`instagrapi` evaluation or equivalent allowed path)
3. TikTok / LinkedIn / Shopify / Threads reality review against current adapters
4. owner-grade validation expansion for partial platforms

## V5-F — Combat Validation
1. targeted tests for every v5 fix
2. rerun of critical CI bundle
3. updated hard audit/checklist state
4. updated benchmark / live validation where relevant

## Порядок выполнения
1. Закрыть P0/P1 до production-grade, не оставляя их `partial`, если это avoidable.
2. Затем закрывать P2/P3 пакетами без пропусков.
3. После каждого пакета:
   - тесты
   - чеклист
   - коммит
4. В конце:
   - повторная жесткая оценка системы
   - новый список weakest points
