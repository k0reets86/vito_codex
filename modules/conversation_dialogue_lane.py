from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from llm_router import TaskType


async def handle_feedback(engine, text: str) -> dict[str, Any]:
    if engine.memory:
        try:
            engine.memory.save_pattern(
                category="feedback",
                key=f"fb_{int(time.time())}",
                value=text[:500],
                confidence=0.8,
            )
        except Exception:
            pass

    response = await engine.llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=(
            f"{engine.VITO_PERSONALITY}\n\n"
            f"Владелец оставил отзыв: \"{text}\"\n"
            f"Поблагодари коротко и скажи как учтёшь. 2-3 предложения максимум."
        ),
        estimated_tokens=200,
    )

    return {
        "intent": engine.Intent.FEEDBACK.value,
        "response": response or "Спасибо за обратную связь! Учту.",
    }


async def handle_conversation(engine, text: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    light_context = f"Время: {now.strftime('%Y-%m-%d %H:%M UTC')}"
    try:
        daily_spend = engine.llm_router.get_daily_spend()
        light_context += f"\nРасходы сегодня: ${daily_spend:.2f} / ${settings.DAILY_LIMIT_USD:.2f}"
    except Exception:
        pass

    prompt = (
        f"{engine.VITO_PERSONALITY}\n\n"
        f"{light_context}\n\n"
        f"{engine._owner_task_focus_text()}\n\n"
        f"История:\n{engine._format_context()}\n\n"
        f"Владелец: {text}\n\n"
        f"Ответь коротко и по теме. Не добавляй информацию, о которой не спрашивали."
    )

    response = await engine.llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        estimated_tokens=500,
    )

    return {
        "intent": engine.Intent.CONVERSATION.value,
        "response": engine._guard_response(response) or "Привет! Я VITO, твой AI-напарник. Чем могу помочь?",
    }
