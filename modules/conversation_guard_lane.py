from __future__ import annotations

from typing import Optional


def guard_response(response: Optional[str]) -> Optional[str]:
    """Prevent unverified completion claims in free-form responses."""
    if not response:
        return response
    lower = response.lower()
    risky_phrases = [
        "готов и загружен", "готов и опубликован", "опубликован", "загружен",
        "создан и загружен", "создан и опубликован", "я загрузил", "я опубликовал",
        "already uploaded", "already published", "is live", "published on",
    ]
    if any(p in lower for p in risky_phrases):
        return "__verify_execution_facts__"
    return response
