from __future__ import annotations


def set_session(engine, session_id: str | None) -> None:
    sid = str(session_id or "default").strip() or "default"
    if sid == engine._session_id:
        return
    engine._session_id = sid
    engine._load_context_from_memory()


def set_defer_owner_actions(engine, enabled: bool) -> None:
    engine._defer_owner_actions = bool(enabled)
