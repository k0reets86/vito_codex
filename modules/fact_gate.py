"""Centralized fact-gate for outbound owner messages.

Goal: prevent "done/published" claims unless there is recent evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from modules.execution_facts import ExecutionFacts


@dataclass
class FactGateDecision:
    allowed: bool
    text: str
    reason: str = ""


RISKY_PATTERNS = [
    "готов и загружен",
    "готов и опубликован",
    "опубликован",
    "опубликовав",
    "загружен",
    "загрузил",
    "опубликовал",
    "создан и загружен",
    "создан и опубликован",
    "завершил интеграцию",
    "успешно опубликовав",
    "выложил продукт",
    "created and published",
    "published on",
    "is live",
]


def _has_inline_evidence(text: str) -> bool:
    lower = (text or "").lower()
    if re.search(r"https?://", lower):
        return True
    if "/home/vito/vito-agent/output/" in lower:
        return True
    if "screenshot" in lower or "скриншот" in lower:
        return True
    return False


def gate_outgoing_claim(text: str, evidence_hours: int = 24) -> FactGateDecision:
    t = text or ""
    lower = t.lower()
    if not any(p in lower for p in RISKY_PATTERNS):
        return FactGateDecision(True, t)

    # If message itself includes evidence links/paths, allow.
    if _has_inline_evidence(t):
        return FactGateDecision(True, t)

    # Otherwise require recent fact evidence.
    try:
        facts = ExecutionFacts()
        if facts.has_publish_evidence_recent(hours=evidence_hours):
            return FactGateDecision(True, t)
    except Exception:
        pass

    return FactGateDecision(
        False,
        "Это пока не подтверждённый факт выполнения. Я могу запустить задачу и вернуться с доказательствами (URL/ID/скрин).",
        reason="missing_evidence",
    )
