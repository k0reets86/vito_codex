from __future__ import annotations

from typing import Any

from modules.conversation_owner_lane import handle_owner_preroute
from modules.conversation_intake_lane import maybe_handle_fast_url_route as _maybe_handle_fast_url_route_impl
from modules.conversation_intake_lane import bootstrap_owner_turn as _bootstrap_owner_turn_impl


async def process_message(engine, text: str) -> dict[str, Any]:
    """Основной owner-facing pipeline обработки сообщения."""
    engine._remember_owner_profile_fact(text)
    try:
        engine.owner_model.update_from_interaction(str(text or ""))
    except Exception:
        pass
    if engine.cancel_state and engine.cancel_state.is_cancelled():
        return {
            "intent": "conversation",
            "response": "Выполнение задач на паузе. Отправь /resume, чтобы продолжить.",
        }
    fast_route = await _maybe_handle_fast_url_route_impl(engine, text)
    if fast_route is not None:
        return fast_route
    preroute = await handle_owner_preroute(engine, text)
    if preroute is not None:
        return preroute

    tones = engine._detect_tone(text)
    intent = engine._detect_intent_rules(text)
    if intent is None:
        intent = await engine._detect_intent_llm(text)

    _bootstrap_owner_turn_impl(engine, text, intent, tones)

    result = await engine._process_by_intent(intent, text)

    if result.get("actions") and not result.get("needs_confirmation", False) and not engine._defer_owner_actions:
        action_results = await engine._execute_actions(result["actions"])
        if action_results:
            friendly = engine._owner_friendly_action_results(action_results)
            result["response"] = (result.get("response") or "") + "\n\n" + friendly

    if result.get("response"):
        engine._add_turn("assistant", result["response"])

    result["nlu_tones"] = tones
    return result
