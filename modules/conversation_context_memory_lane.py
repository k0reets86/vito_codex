from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

MAX_CONTEXT_TURNS = 20


def extract_json(text: str) -> dict | None:
    parsed = text.strip()
    if "```" in parsed:
        for block in parsed.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                parsed = block
                break
    if parsed.startswith("{"):
        return json.loads(parsed)
    return None


def add_turn(engine, role: str, text: str, intent: Any | None = None) -> None:
    from conversation_engine import Turn

    turn = Turn(role=role, text=text, intent=intent)
    engine._context.append(turn)
    if len(engine._context) > MAX_CONTEXT_TURNS:
        engine._context = engine._context[-MAX_CONTEXT_TURNS:]
    persist_turn(engine, turn)


def format_context(engine) -> str:
    from conversation_engine import settings

    if not engine._context:
        return "(начало разговора)"
    turns = max(5, min(20, int(getattr(settings, "CONVERSATION_CONTEXT_TURNS", 10) or 10)))
    lines = []
    for turn in engine._context[-turns:]:
        role_label = "Владелец" if turn.role == "user" else "VITO"
        lines.append(f"{role_label}: {turn.text[:200]}")
    return "\n".join(lines)


def owner_task_focus_text(engine) -> str:
    if not engine.owner_task_state:
        return "Фокус владельца: (не зафиксирован)"
    try:
        active = engine.owner_task_state.get_active()
        if not active:
            return "Фокус владельца: (не зафиксирован)"
        return (
            "Фокус владельца:\n"
            f"- текущая задача: {str(active.get('text', ''))[:260]}\n"
            f"- intent: {str(active.get('intent', ''))[:80]}\n"
            f"- статус: {str(active.get('status', 'active'))[:40]}\n"
            f"- сервис: {str(active.get('service_context', ''))[:80] if active.get('service_context') else 'не зафиксирован'}\n"
            f"- выбранная идея: {str(active.get('selected_research_title', ''))[:160] if active.get('selected_research_title') else 'не выбрана'}"
        )
    except Exception:
        return "Фокус владельца: (не зафиксирован)"


def load_context_from_memory(engine) -> None:
    if not engine.conversation_memory:
        return
    entries = engine.conversation_memory.load(limit=MAX_CONTEXT_TURNS, session_id=engine._session_id)
    loaded: list[Any] = []
    for entry in entries:
        turn = turn_from_entry(entry)
        if turn:
            loaded.append(turn)
    engine._context = loaded[-MAX_CONTEXT_TURNS:]


def turn_from_entry(entry: dict):
    from conversation_engine import Intent, Turn

    role = entry.get("role")
    text = entry.get("text")
    if not role or not text:
        return None
    intent_value = entry.get("intent")
    timestamp = entry.get("timestamp")
    intent = None
    if intent_value:
        try:
            intent = Intent(intent_value)
        except ValueError:
            intent = None
    try:
        ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now(timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)
    return Turn(role=role, text=text, intent=intent, timestamp=ts)


def persist_turn(engine, turn: Turn) -> None:
    if not engine.conversation_memory:
        return
    entry = {
        "role": turn.role,
        "text": turn.text,
        "intent": turn.intent.value if turn.intent else None,
        "timestamp": turn.timestamp.isoformat(),
    }
    try:
        engine.conversation_memory.append(entry, session_id=engine._session_id)
    except Exception:
        pass
