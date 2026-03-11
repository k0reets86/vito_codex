from __future__ import annotations

from typing import Optional


def guard_response_signal(response: Optional[str]) -> Optional[str]:
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


def guard_response(engine, response: Optional[str]) -> Optional[str]:
    signal = guard_response_signal(response)
    if signal != "__verify_execution_facts__":
        return signal
    try:
        from modules.execution_facts import ExecutionFacts
        facts = ExecutionFacts()
        if not facts.recent_exists(
            actions=["publisher_agent:publish", "browser_agent:form_fill", "ecommerce_agent:listing_create", "platform:publish"],
            hours=24,
        ):
            return "Это было предложение, а не факт выполнения. Если хочешь, запущу это сейчас."
    except Exception:
        return "Это было предложение, а не факт выполнения. Если хочешь, запущу это сейчас."
    return response
