from __future__ import annotations

from llm_router import TaskType
from modules.owner_preference_model import OwnerPreferenceModel
from modules.prompt_guard import wrap_untrusted_text


async def quick_gumroad_analytics(engine) -> str:
    if not engine.agent_registry:
        return ""
    try:
        result = await engine.agent_registry.dispatch("sales_check", platform="gumroad")
    except Exception:
        return ""
    if not result or not getattr(result, "success", False):
        return ""
    data = getattr(result, "output", {}) or {}
    gm = data.get("gumroad", data)
    if not isinstance(gm, dict):
        return ""
    if gm.get("error"):
        return f"Gumroad: доступ есть, но аналитика вернула ошибку: {gm.get('error')}"
    sales = int(gm.get("sales", 0) or 0)
    revenue = float(gm.get("revenue", 0.0) or 0.0)
    products = int(gm.get("products_count", 0) or 0)
    return (
        "Gumroad (live):\n"
        f"- Продажи: {sales}\n"
        f"- Выручка: ${revenue:.2f}\n"
        f"- Продуктов: {products}"
    )


async def handle_question(engine, text: str) -> dict:
    lower = text.strip().lower()
    normalized = engine._normalize_for_nlu(text)
    if engine._has_keywords(normalized, ("как меня зовут", "мое имя", "моё имя", "забыл мое имя", "my name"), fuzzy=True):
        owner_name = engine._resolve_owner_name()
        if owner_name:
            return {
                "intent": engine.Intent.QUESTION.value,
                "response": f"Тебя зовут {owner_name}.",
            }
        return {
            "intent": engine.Intent.QUESTION.value,
            "response": "Пока не вижу в памяти твоего имени. Напиши: 'меня зовут ...', и я запомню.",
        }
    if any(w in lower for w in ("откуда", "почему ты", "почему вы", "ты писал", "ты написал", "ты сказала", "ты говорил")):
        return {
            "intent": engine.Intent.QUESTION.value,
            "response": "У меня нет подтверждённых данных о публикации/создании. Это было ошибочное сообщение. Исправляю: без факта выполнения больше так не пишу.",
        }
    gumroad_kw = ("gumroad", "гумроад", "гамроад")
    analytics_kw = ("стат", "statistics", "analytics", "продаж", "revenue", "выручк", "доход")
    if engine._has_keywords(normalized, gumroad_kw, fuzzy=True) and engine._has_keywords(normalized, analytics_kw, fuzzy=True):
        live = await engine._quick_gumroad_analytics()
        if live:
            return {
                "intent": engine.Intent.QUESTION.value,
                "response": live,
            }
    if engine._is_time_query(lower):
        return {
            "intent": engine.Intent.QUESTION.value,
            "response": engine._format_time_answer(),
        }
    try:
        quick = engine._quick_answer(text, lower)
    except TypeError:
        quick = engine._quick_answer(lower)
    if quick:
        return {
            "intent": engine.Intent.QUESTION.value,
            "response": quick,
        }

    context_from_memory = engine._build_operational_memory_context(text, include_errors=True)
    try:
        prefs = OwnerPreferenceModel().list_preferences(limit=5)
        if prefs:
            pref_lines = "\n".join(f"- {p.get('pref_key')}: {p.get('value')}" for p in prefs)
            context_from_memory += f"\n\nПредпочтения владельца:\n{pref_lines}"
    except Exception:
        pass

    system_context = engine._format_system_context()
    prompt = (
        f"{engine.VITO_PERSONALITY}\n\n"
        f"=== ПОЛНОЕ СОСТОЯНИЕ СИСТЕМЫ ===\n{system_context}\n"
        f"=== КОНЕЦ СОСТОЯНИЯ ===\n\n"
        f"История разговора:\n{engine._format_context()}\n\n"
        f"{context_from_memory}\n\n"
        f"Вопрос владельца: {wrap_untrusted_text(text)}\n\n"
        f"ВАЖНО: отвечай с КОНКРЕТНЫМИ цифрами и данными из системы выше. "
        f"Не говори что данных нет — они есть в состоянии системы."
    )

    response = await engine.llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        estimated_tokens=800,
    )

    return {
        "intent": engine.Intent.QUESTION.value,
        "response": engine._guard_response(response) if response else "Не удалось получить ответ. Попробуй переформулировать.",
    }
