from __future__ import annotations

import difflib
import re
from typing import Any, Optional

from modules.telegram_command_compiler import parse_owner_message_structured


def detect_intent_rules(engine, text: str):
    stripped = text.strip()
    if stripped.startswith('/'):
        return engine.Intent.COMMAND

    lower = stripped.lower()
    normalized = normalize_for_nlu(stripped)
    if '?' in stripped:
        return engine.Intent.QUESTION
    if lower.startswith(("откуда", "почему", "зачем", "как", "кто", "что", "где", "когда", "какой", "какие", "чем")):
        return engine.Intent.QUESTION

    time_words = ("время", "час", "дата", "time", "what time", "date", "сколько время")
    if has_keywords(normalized, time_words, fuzzy=True) and len(lower) < 40:
        return engine.Intent.QUESTION

    approval_words = {"да", "нет", "ок", "ok", "yes", "no", "approve", "reject", "отмена", "одобряю", "отклоняю"}
    if lower in approval_words:
        return engine.Intent.APPROVAL

    info_verbs = ("дай", "покажи", "расскажи", "найди", "найти", "проанализируй", "собери")
    info_targets = ("новост", "тренд", "статист", "аналит", "обзор", "отчет", "отчёт", "сводк", "ниши")
    create_targets = ("создай", "опубликуй", "запусти", "загрузи", "сделай продукт", "сделай товар")
    if has_keywords(normalized, info_verbs, fuzzy=True) and has_keywords(normalized, info_targets, fuzzy=True):
        if not has_keywords(normalized, create_targets, fuzzy=True):
            return engine.Intent.QUESTION

    goal_keywords = [
        "создай", "сделай", "опубликуй", "напиши", "разработай",
        "запусти продукт", "запусти товар", "продукт", "ebook",
        "найди", "найти", "подбери", "собери", "сформируй",
        "отчет", "отчёт", "тренд", "тренды",
        "create", "make", "publish", "build", "launch", "find", "research",
        "write an", "write a", "design", "generate",
    ]
    if has_keywords(normalized, goal_keywords, fuzzy=True):
        return engine.Intent.GOAL_REQUEST

    action_keywords = [
        "запусти агент", "останови", "просканируй", "проанализируй",
        "используй", "переключи", "смени модель", "сканируй тренды",
        "проверь ошибки", "сделай бэкап", "откати", "обнови",
    ]
    self_improve_keywords = [
        "исправь", "почини", "доработай", "улучши код", "улучши",
        "самоисправ", "добавь интеграц", "сделай интеграц",
        "добавь поддержку", "добавь навык",
    ]
    learn_service_keywords = [
        "изучи сервис", "изучи платформ", "найди требования", "добавь знания",
        "документац", "официальные требования",
    ]
    if has_keywords(normalized, self_improve_keywords, fuzzy=True):
        return engine.Intent.SYSTEM_ACTION
    if has_keywords(normalized, learn_service_keywords, fuzzy=True):
        return engine.Intent.SYSTEM_ACTION
    if has_keywords(normalized, action_keywords, fuzzy=True):
        return engine.Intent.SYSTEM_ACTION
    return None


def normalize_for_nlu(text: str) -> str:
    text = (text or '').lower().replace('ё', 'е')
    text = re.sub(r'[^a-zа-я0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def has_keywords(normalized_text: str, keywords: list[str] | tuple[str, ...], fuzzy: bool = False) -> bool:
    if not normalized_text:
        return False
    tokens = normalized_text.split()
    for raw_kw in keywords:
        kw = normalize_for_nlu(str(raw_kw or ''))
        if not kw:
            continue
        if kw in normalized_text:
            return True
        if not fuzzy:
            continue
        if ' ' in kw or len(kw) < 4:
            continue
        for token in tokens:
            if len(token) < 4:
                continue
            if abs(len(token) - len(kw)) > 2:
                continue
            if difflib.SequenceMatcher(None, token, kw).ratio() >= 0.78:
                return True
    return False


def detect_tone(text: str) -> list[str]:
    normalized = normalize_for_nlu(text)
    tones: list[str] = []
    frustrated_markers = (
        "не работает", "бесит", "достало", "тупой", "ошибка", "сломал",
        "не можешь", "не делает", "плохо", "ужас", "wtf",
    )
    urgent_markers = ("срочно", "asap", "немедленно", "прямо сейчас", "горит")
    positive_markers = ("спасибо", "отлично", "супер", "класс", "good", "great")
    if has_keywords(normalized, frustrated_markers, fuzzy=True):
        tones.append("frustrated")
    if has_keywords(normalized, urgent_markers, fuzzy=True):
        tones.append("urgent")
    if has_keywords(normalized, positive_markers, fuzzy=True):
        tones.append("positive")
    return tones


def extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://\S+", text)
    if m:
        return m.group(0).rstrip(".,)")
    m = re.search(r"\b([a-z0-9.-]+\.[a-z]{2,})(/[^\s]*)?\b", text, re.IGNORECASE)
    if m and "@" not in m.group(0):
        return "https://" + m.group(0)
    return None


async def detect_intent_llm(engine, text: str):
    if '?' in text:
        return engine.Intent.QUESTION
    try:
        active = engine.owner_task_state.get_active() if engine.owner_task_state else {}
    except Exception:
        active = {}
    try:
        parsed = await parse_owner_message_structured(text, active, engine.llm_router)
        if parsed:
            detected = {
                "question": engine.Intent.QUESTION,
                "goal_request": engine.Intent.GOAL_REQUEST,
                "system_action": engine.Intent.SYSTEM_ACTION,
                "feedback": engine.Intent.FEEDBACK,
                "conversation": engine.Intent.CONVERSATION,
            }.get(str(parsed.get("intent") or "").strip().lower(), engine.Intent.CONVERSATION)
            if detected == engine.Intent.GOAL_REQUEST and ("?" in text):
                return engine.Intent.QUESTION
            return detected
    except Exception as e:
        engine.logger.debug(f"LLM intent detection failed: {e}", extra={"event": "intent_llm_error"})
    return engine.Intent.CONVERSATION


async def process_by_intent(engine, intent, text: str) -> dict[str, Any]:
    if intent == engine.Intent.COMMAND:
        return {"intent": intent.value, "response": None, "pass_through": True}
    if intent == engine.Intent.APPROVAL:
        return {"intent": intent.value, "response": None, "pass_through": True}
    if intent == engine.Intent.QUESTION:
        result = await engine._handle_question(text)
    elif intent == engine.Intent.GOAL_REQUEST:
        result = await engine._handle_goal_request(text)
    elif intent == engine.Intent.SYSTEM_ACTION:
        result = await engine._handle_system_action(text)
    elif intent == engine.Intent.FEEDBACK:
        result = await engine._handle_feedback(text)
    else:
        result = await engine._handle_conversation(text)
    try:
        if isinstance(result, dict) and isinstance(result.get("response"), str):
            result["response"] = engine._guard_response(result["response"])
    except Exception:
        pass
    return result
