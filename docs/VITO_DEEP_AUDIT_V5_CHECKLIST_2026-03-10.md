# VITO Deep Audit v5 Checklist

Источник:
- `input/attachments/VITO DEEP AUDIT v5.docx`

Статусы:
- `done`
- `partial`
- `not_done`
- `blocked_policy`

## P0
1. `PatchGenerator` + wiring в `_handle_runtime_error`
- Статус: `done`
- Аргумент: `modules/patch_generator.py` добавлен; `decision_loop._handle_runtime_error()` теперь сам пытается сгенерировать `patch_files` перед healer fallback.

2. `search_episodes()` на pgvector
- Статус: `done`
- Аргумент: `memory/memory_manager.py` теперь пишет `embedding` для эпизодов и использует vector-order path с fallback.

3. `Etsy aiohttp callback server`
- Статус: `done`
- Аргумент: `scripts/etsy_auth_helper.py` уже содержит `oauth-auto` с local callback server и `ETSY_OAUTH_REDIRECT_URI=http://localhost:8765/callback`.

## P1
4. `SkillLibrary.retrieve()` semantic merge
- Статус: `partial`
- Аргумент: semantic merge с Chroma knowledge уже добавлен, но это еще не полный deep semantic retrieval layer с отдельной проверкой recall/precision.

5. `record_lesson()` в BaseAgent / AgentRegistry
- Статус: `done`
- Аргумент: `BaseAgent._record_lesson()` добавлен, `AgentRegistry.dispatch()` его вызывает.

6. `AutonomyOverseer.execute_actions()`
- Статус: `done`
- Аргумент: метод добавлен, `decision_loop` вызывает action loop после `inspect()`.

7. `AgentEventBus` SQLite persistence
- Статус: `done`
- Аргумент: `modules/agent_event_bus.py` теперь пишет события в SQLite и читает `recent()` из persistent store.

8. `Gumroad -> patchright/shared browser runtime`
- Статус: `partial`
- Аргумент: общий human browser runtime и browser policy внедрены, но `platforms/gumroad.py` все еще содержит собственные raw launch helpers и требует полного выравнивания на shared runtime.

## P2
9. `LLM navigation: screenshot -> action`
- Статус: `done`
- Аргумент: добавлен bounded planner `modules/browser_llm_navigation.py` и runtime task `browser_agent.execute_task('suggest_next_action', ...)`, который выбирает следующий шаг из ограниченного action/selector набора на основе `screenshot_path + url + title + body_excerpt`, с safe fallback и тестами.

10. `Knowledge Graph`
- Статус: `done`
- Аргумент: добавлен persistent `KnowledgeGraph` и запись связей `knowledge/lesson -> agent/platform/task_family/skill/goal` встроена в `MemoryManager.store_knowledge()` и `SelfLearningEngine.record_lesson()`.

11. `Instagram via instagrapi`
- Статус: `not_done`
- Аргумент: текущий Instagram path усилен, но `instagrapi`-based operational route не внедрен.

12. `comms_agent` / `conversation_engine` decomposition`
- Статус: `done`
- Аргумент: owner inbox text lane вынесен в `modules/comms_owner_lane.py`, owner continuation/compiler preroute — в `modules/conversation_owner_lane.py`; таргетный regression suite остался зеленым.

## P3
13. `mem0 integration`
- Статус: `done`
- Аргумент: добавлен optional `modules/mem0_bridge.py`, feature flags в settings/env, write-through из `MemoryManager.store_knowledge()` и merge-search в `search_knowledge()`.

14. `LangGraph parallel orchestration`
- Статус: `done`
- Аргумент: добавлен durable DAG-runtime `modules/parallel_orchestration_runtime.py` с persistent run/node state, dependency-aware frontier execution и интеграцией в `DecisionLoop._run_background_maintenance()`, что закрывает parallel orchestration contract на практике, а не только через `asyncio.gather()`.

15. `capability_packs real logic`
- Статус: `done`
- Аргумент: ранее capability packs переведены в structured runtime adapters; это замечание v5 для текущего `main` уже закрыто.

## Дополнительные замечания из аудита
16. `Reflector.top_relevant()` semantic/reranked path
- Статус: `done`
- Аргумент: `modules/reflector.py` теперь сохраняет reflection entries в semantic knowledge layer и в `top_relevant()` смешивает SQLite reflections с semantic hints через memory-backed reranking.

17. `ConversationMemory` flat JSON limits
- Статус: `partial`
- Аргумент: owner/task memory layers усилены, но сам flat session-memory слой не переработан полностью.

18. `MemoryBlocks on-demand consolidation`
- Статус: `partial`
- Аргумент: consolidation engine есть, но явного on-demand path из аудита еще нет.

19. `automatic knowledge write from successful agent tasks`
- Статус: `done`
- Аргумент: `AgentRegistry.dispatch()` теперь автоматически пишет успешные agent outcomes в semantic knowledge layer через `memory.store_knowledge(...)` с lineage-aware metadata (`type=agent_outcome`, `task_root_id`, `agent_work_id`).

20. `9 thin wrapper agents specialization`
- Статус: `partial`
- Аргумент: agent uplift проведен сильно, но audit v5 still pushes deeper specialization; это уже не `not_done`, но еще не потолок.

21. `agent health monitoring`
- Статус: `done`
- Аргумент: добавлен `AgentHealthMonitor`, который агрегирует `DataLake`, `AgentFeedback` и `FailureSubstrate` в runtime health report по агентам с `healthy/degraded/critical` классификацией.

22. `registry.dispatch()` fan-out / parallel delegations`
- Статус: `done`
- Аргумент: `AgentRegistry.dispatch()` теперь исполняет orchestration `delegations` через `asyncio.gather()` с сохранением порядка результатов, fail-safe сбором ошибок и регрессионным тестом на реальный parallel fan-out.

23. `decision_loop` sequential `_maybe_run_*``
- Статус: `done`
- Аргумент: `decision_loop._run_background_maintenance()` введен как parallel fan-out через `asyncio.gather()` для maintenance `_maybe_run_*` lanes; `_tick()` больше не гоняет этот фон строго последовательно.

24. `service session persistence across restarts for each platform`
- Статус: `done`
- Аргумент: добавлен `modules/service_session_registry.py`; `CommsAgent` теперь фиксирует и очищает persistent service session snapshots (`storage_state_path`, `profile_dir`, `verified`) через `_mark_service_auth_confirmed()` / `_clear_service_auth_confirmed()`, что закрывает restart-persistence contract на уровне runtime registry.

25. `captcha solver real integrations`
- Статус: `blocked_policy`
- Аргумент: внешние solver/anti-bot bypass stacks не внедряются в рамках допустимой части.
