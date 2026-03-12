from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def build_research_pipeline_action(item: dict[str, Any], fallback_topic: str) -> dict[str, Any]:
    topic = str(item.get("title") or fallback_topic or "Digital Product").strip()[:180]
    platform = str(item.get("platform") or "gumroad").strip().lower() or "gumroad"
    return {
        "action": "run_product_pipeline",
        "params": {
            "topic": topic,
            "platforms": [platform],
            "auto_publish": False,
        },
    }


def remember_research_selection(agent, idx: int, item: dict[str, Any]) -> None:
    if not agent._owner_task_state or not isinstance(item, dict):
        return
    try:
        platform = str(item.get("platform") or "").strip().lower()
        agent._owner_task_state.enrich_active(
            selected_research_option=int(idx or 0),
            selected_research_json=json.dumps(item, ensure_ascii=False),
            selected_research_title=str(item.get("title") or "")[:180],
            selected_research_platform=platform,
        )
    except Exception:
        pass


def prime_research_pending_actions(
    agent,
    *,
    topic: str,
    ideas: list[dict[str, Any]],
    recommended: dict[str, Any] | None = None,
    origin_text: str = "",
) -> None:
    actions: list[dict[str, Any]] = []
    normalized_ideas: list[dict[str, Any]] = []
    recommended_rank = 1
    rec_title = str((recommended or {}).get("title") or "").strip().lower()
    rec_platform = str((recommended or {}).get("platform") or "").strip().lower()
    for pos, raw in enumerate(ideas[:5], start=1):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        rank = int(item.get("rank", pos) or pos)
        item["rank"] = rank
        normalized_ideas.append(item)
        actions.append(build_research_pipeline_action(item, topic))
        if rec_title and str(item.get("title") or "").strip().lower() == rec_title:
            if not rec_platform or str(item.get("platform") or "").strip().lower() == rec_platform:
                recommended_rank = rank
    if not actions:
        actions = [
            {
                "action": "run_product_pipeline",
                "params": {"topic": topic, "platforms": ["gumroad"], "auto_publish": False},
            }
        ]
        normalized_ideas = [{"rank": 1, "title": topic, "platform": "gumroad"}]
        recommended_rank = 1
    agent._pending_system_action = {
        "kind": "research_options",
        "actions": actions,
        "ideas": normalized_ideas,
        "recommended_index": int(recommended_rank or 1),
        "origin_text": origin_text or topic,
    }


def prime_research_pending_actions_from_owner_state(agent, origin_text: str) -> bool:
    if agent._pending_system_action or not agent._owner_task_state:
        return False
    try:
        active = agent._owner_task_state.get_active() or {}
        raw = str(active.get("research_options_json") or "").strip()
        if not raw:
            return False
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            return False
        ideas = [dict(item) for item in parsed[:5] if isinstance(item, dict)]
        if not ideas:
            return False
        recommended_item: dict[str, Any] | None = None
        rec_raw = str(active.get("research_recommended_json") or "").strip()
        if rec_raw:
            rec_val = json.loads(rec_raw)
            if isinstance(rec_val, dict):
                recommended_item = dict(rec_val)
        topic = str(
            active.get("selected_research_title")
            or active.get("text")
            or (ideas[0].get("title") if isinstance(ideas[0], dict) else "")
            or "Digital Product"
        ).strip()
        prime_research_pending_actions(
            agent,
            topic=topic,
            ideas=ideas,
            recommended=recommended_item,
            origin_text=origin_text,
        )
        return True
    except Exception:
        return False


def select_pending_research_option(agent, idx: int) -> dict[str, Any] | None:
    payload = agent._pending_system_action or {}
    if str(payload.get("kind") or "").strip().lower() != "research_options":
        return None
    actions = list(payload.get("actions") or [])
    ideas = list(payload.get("ideas") or [])
    if idx < 1 or idx > len(actions):
        return None
    chosen_action = actions[idx - 1]
    chosen_item = ideas[idx - 1] if idx - 1 < len(ideas) and isinstance(ideas[idx - 1], dict) else {}
    remember_research_selection(agent, idx, chosen_item)
    agent._pending_system_action = {
        "kind": "research_options",
        "actions": [chosen_action],
        "ideas": [chosen_item] if chosen_item else [],
        "recommended_index": 1,
        "origin_text": f"choice:{idx}",
    }
    return chosen_item if isinstance(chosen_item, dict) else None


def has_fresh_service_context(agent, max_age_minutes: int = 180) -> bool:
    if not agent._last_service_context:
        return False
    stamp = str(agent._last_service_context_at or "").strip()
    if not stamp:
        return True
    try:
        dt = datetime.fromisoformat(stamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
        return age_sec <= max(60, int(max_age_minutes) * 60)
    except Exception:
        return True


def get_memory_manager(agent):
    candidates = [getattr(agent, "_conversation_engine", None), getattr(agent, "_decision_loop", None)]
    for obj in candidates:
        mm = getattr(obj, "memory", None) if obj else None
        if mm and hasattr(mm, "save_skill") and hasattr(mm, "save_pattern"):
            return mm
    return None


def record_context_learning(agent, skill_name: str, description: str, anti_pattern: str, method: dict | None = None) -> None:
    mm = get_memory_manager(agent)
    if mm is None:
        return
    try:
        mm.save_skill(
            name=skill_name,
            description=description,
            agent="comms_agent",
            task_type="nlu_context",
            method=method or {},
        )
        mm.save_pattern(
            category="owner_context",
            key=skill_name,
            value=description,
            confidence=0.95,
        )
        mm.save_pattern(
            category="anti_pattern",
            key=f"{skill_name}_anti",
            value=anti_pattern,
            confidence=0.95,
        )
    except Exception:
        pass
