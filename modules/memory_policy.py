"""Memory save/forget policy with auditable decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryPolicyDecision:
    action: str
    reason: str
    importance: float
    ttl_days: int


def decide_save(doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> MemoryPolicyDecision:
    meta = metadata or {}
    memory_type = str(meta.get("type", "")).strip().lower()
    source = str(meta.get("source", "")).strip().lower()
    force_save = bool(meta.get("force_save", False))
    clean_text = (text or "").strip()

    if force_save:
        return _decision("save", "force_save", memory_type)

    if not clean_text:
        return MemoryPolicyDecision(action="forget", reason="empty_text", importance=0.0, ttl_days=0)

    # Keep short but meaningful artifacts (e.g., titles/versions); drop only near-empty fragments.
    if len(clean_text) < 3 and memory_type not in {"owner_preference"}:
        return MemoryPolicyDecision(action="forget", reason="too_short", importance=0.05, ttl_days=7)

    if memory_type in {"debug", "heartbeat", "noop"} or source in {"debug", "heartbeat"}:
        return MemoryPolicyDecision(action="forget", reason="operational_noise", importance=0.05, ttl_days=3)

    return _decision("save", "policy_default", memory_type)


def _decision(action: str, reason: str, memory_type: str) -> MemoryPolicyDecision:
    if memory_type == "owner_preference":
        return MemoryPolicyDecision(action=action, reason=reason, importance=0.95, ttl_days=3650)
    if memory_type in {"lesson", "lesson_fail"}:
        return MemoryPolicyDecision(action=action, reason=reason, importance=0.8, ttl_days=365)
    if memory_type in {"goal", "goal_result"}:
        return MemoryPolicyDecision(action=action, reason=reason, importance=0.65, ttl_days=180)
    if memory_type in {"research", "research_learn"}:
        return MemoryPolicyDecision(action=action, reason=reason, importance=0.55, ttl_days=120)
    return MemoryPolicyDecision(action=action, reason=reason, importance=0.5, ttl_days=90)
