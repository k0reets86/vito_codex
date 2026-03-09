# mem0 Feasibility Decision — 2026-03-09

Статус: `APPROVED_FOR_PHASED_EVALUATION`

Источники:
- https://github.com/mem0ai/mem0
- https://docs.mem0.ai/

## Решение

`mem0` не должен заменять текущую память VITO.

Он подходит только как дополнительный слой shared-memory/long-term recall поверх уже существующих систем:
- `owner_task_state`
- `MemoryManager`
- `MemoryBlocks`
- `FailureMemory`
- `ExecutionFacts`
- `PlaybookRegistry`

## Почему не замена

У VITO уже есть критичные runtime-инварианты:
- `task_root_id`
- hard object protection
- platform quality gates
- executable runbook packs
- failure substrate

`mem0` не покрывает эти доменные гарантии и не должен становиться новой source-of-truth системой.

## Где mem0 может дать реальную пользу

1. Long-term owner preference recall
2. Cross-session project continuity
3. Compressed retrieval for large historic context
4. Shared retrieval layer for multi-agent collaboration

## Где mem0 нельзя ставить в центр

1. Platform object routing
2. Publish success verification
3. Protected object decisions
4. Duplicate prevention
5. Action-step truth

## Рекомендованный путь внедрения

1. Сначала завершить `Phase C` базовыми средствами текущей архитектуры.
2. Потом сделать маленький интеграционный пакет:
   - adapter `modules/mem0_bridge.py`
   - feature flag `MEM0_ENABLED`
   - write-through only for:
     - owner preferences
     - durable project summaries
     - long-horizon lessons
3. Read path включать только после сравнения качества retrieval против текущего `MemoryManager`.
4. Никогда не использовать `mem0` как единственный источник для runtime decisions.

## Критерий go/no-go

`mem0` внедряется дальше только если:
- снижает промахи retrieval,
- не ломает deterministic routing,
- не подменяет текущие hard gates,
- дает measurable improvement в owner continuity.

Иначе остается необязательным дополнительным слоем.
