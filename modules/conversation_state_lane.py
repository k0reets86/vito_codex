from __future__ import annotations

from typing import Any


def get_context(engine) -> list[dict[str, Any]]:
    return [
        {
            "role": t.role,
            "text": t.text[:100],
            "intent": t.intent.value if t.intent else None,
            "timestamp": t.timestamp.isoformat(),
        }
        for t in engine._context
    ]


def clear_context(engine) -> None:
    engine._context.clear()
    if engine.conversation_memory:
        try:
            engine.conversation_memory.clear(session_id=engine._session_id)
        except Exception:
            pass
