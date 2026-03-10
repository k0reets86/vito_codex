from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm_router import TaskType


@dataclass(slots=True)
class BrowserActionCandidate:
    action: str
    selector: str = ""
    value: str = ""
    label: str = ""
    priority: int = 50

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value,
            "label": self.label,
            "priority": self.priority,
        }


def _safe_fallback(candidates: list[BrowserActionCandidate]) -> dict[str, Any]:
    if not candidates:
        return {
            "action": "clarify",
            "selector": "",
            "value": "",
            "confidence": 0.0,
            "reason": "no_candidates",
        }
    ranked = sorted(candidates, key=lambda item: int(item.priority or 50))
    chosen = ranked[0]
    return {
        "action": chosen.action,
        "selector": chosen.selector,
        "value": chosen.value,
        "confidence": 0.35,
        "reason": "fallback_first_candidate",
    }


def _parse_navigation_json(raw: str, candidates: list[BrowserActionCandidate]) -> dict[str, Any]:
    fallback = _safe_fallback(candidates)
    try:
        payload = json.loads(raw or "{}")
    except Exception:
        return fallback
    action = str(payload.get("action") or "").strip()
    selector = str(payload.get("selector") or "").strip()
    value = str(payload.get("value") or "").strip()
    confidence = float(payload.get("confidence") or 0.0)
    reason = str(payload.get("reason") or "").strip()
    valid_actions = {cand.action for cand in candidates}
    if action not in valid_actions:
        return fallback
    for cand in candidates:
        if cand.action == action and selector and cand.selector and selector != cand.selector:
            # do not allow LLM to invent a different selector for a bounded candidate
            return fallback
    return {
        "action": action,
        "selector": selector,
        "value": value,
        "confidence": confidence,
        "reason": reason or "llm_navigation_choice",
    }


async def suggest_browser_action(
    *,
    llm_router,
    service: str,
    url: str,
    screenshot_path: str,
    title: str,
    body_excerpt: str,
    candidates: list[BrowserActionCandidate],
) -> dict[str, Any]:
    if not llm_router:
        return _safe_fallback(candidates)
    candidate_payload = [item.to_dict() for item in candidates]
    prompt = (
        "Ты browser-navigation planner внутри VITO.\n"
        "Тебе дан screenshot_path, url, title, body_excerpt и ограниченный список допустимых действий.\n"
        "Нельзя придумывать новых действий или новых селекторов.\n"
        "Верни только JSON формата:\n"
        '{"action":"...", "selector":"...", "value":"...", "confidence":0.0, "reason":"..."}\n\n'
        f"service={service}\n"
        f"url={url}\n"
        f"screenshot_path={screenshot_path}\n"
        f"title={title}\n"
        f"body_excerpt={body_excerpt[:2000]}\n"
        f"candidates={json.dumps(candidate_payload, ensure_ascii=False)}\n"
    )
    raw = await llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        system_prompt="Return strict JSON only. Choose exactly one allowed browser action.",
        estimated_tokens=500,
    )
    return _parse_navigation_json(raw or "", candidates)
