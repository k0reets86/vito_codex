import json
from typing import Any

from modules.telegram_command_compiler import compile_owner_message


async def handle_owner_preroute(engine, text: str) -> dict[str, Any] | None:
    autonomy_continuation = engine._maybe_continue_from_autonomy_proposals(text)
    if autonomy_continuation is not None:
        _finalize_preroute(engine, text, autonomy_continuation)
        return autonomy_continuation

    if engine.owner_task_state:
        try:
            active = engine.owner_task_state.get_active() or {}
        except Exception:
            active = {}
        routed = await compile_owner_message(text, active, engine.llm_router)
        if routed is not None:
            try:
                engine._ensure_owner_task_state(text, routed.get("intent"))
            except Exception:
                pass
            if routed.get("actions") and not routed.get("needs_confirmation") and not engine._defer_owner_actions:
                try:
                    action_out = await engine._execute_actions(routed.get("actions") or [])
                    if action_out:
                        base = str(routed.get("response") or "").strip()
                        routed["response"] = f"{base}\n{action_out}".strip()
                except Exception:
                    pass
            selected = routed.get("selected")
            selected_idx = int(routed.get("selected_idx") or 0)
            if selected_idx and isinstance(selected, dict):
                try:
                    engine.owner_task_state.enrich_active(
                        selected_research_option=selected_idx,
                        selected_research_json=json.dumps(selected, ensure_ascii=False),
                        selected_research_title=str(selected.get("title") or "")[:180],
                        selected_research_platform=",".join(routed.get("platforms") or []),
                    )
                    engine.owner_model.update_from_decision(selected, approved=True)
                except Exception:
                    pass
            _finalize_preroute(engine, text, routed)
            return routed

    deterministic = await engine._deterministic_owner_route(text)
    if deterministic is not None:
        _finalize_preroute(engine, text, deterministic)
        return deterministic

    research_continuation = engine._maybe_continue_from_research_state(text)
    if research_continuation is not None:
        try:
            engine._ensure_owner_task_state(text, research_continuation.get("intent"))
            engine._add_turn("user", text, engine.Intent.SYSTEM_ACTION)
            if research_continuation.get("response"):
                engine._add_turn("assistant", research_continuation["response"])
                engine.owner_model.update_from_interaction(text, research_continuation["response"])
        except Exception:
            pass
        research_continuation["nlu_tones"] = engine._detect_tone(text)
        return research_continuation
    return None


def _finalize_preroute(engine, text: str, result: dict[str, Any]) -> None:
    try:
        intent_value = result.get("intent")
        engine._ensure_owner_task_state(text, intent_value)
        intent_obj = engine.Intent.SYSTEM_ACTION if intent_value == engine.Intent.SYSTEM_ACTION.value else engine.Intent.QUESTION
        engine._add_turn("user", text, intent_obj)
        if result.get("response"):
            engine._add_turn("assistant", result["response"])
            engine.owner_model.update_from_interaction(text, result["response"])
    except Exception:
        pass
    result["nlu_tones"] = engine._detect_tone(text)
