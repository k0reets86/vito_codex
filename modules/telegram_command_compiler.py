from __future__ import annotations

import json
import re
from typing import Any, Optional

from llm_router import TaskType
from modules.telegram_nlu_router import route_owner_dialogue


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if "```" in raw:
        for block in raw.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                raw = block
                break
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalize_platforms(items: Any) -> list[str]:
    aliases = {
        "etsy": "etsy",
        "этси": "etsy",
        "етси": "etsy",
        "gumroad": "gumroad",
        "гумроад": "gumroad",
        "гумр": "gumroad",
        "amazon_kdp": "amazon_kdp",
        "amazon": "amazon_kdp",
        "amz": "amazon_kdp",
        "амазон": "amazon_kdp",
        "амаз": "amazon_kdp",
        "kdp": "amazon_kdp",
        "кдп": "amazon_kdp",
        "printful": "printful",
        "принтфул": "printful",
        "kofi": "kofi",
        "ko-fi": "kofi",
        "кофи": "kofi",
        "ко фи": "kofi",
        "twitter": "twitter",
        "x": "twitter",
        "x.com": "twitter",
        "твиттер": "twitter",
        "твитер": "twitter",
        "pinterest": "pinterest",
        "пинтерест": "pinterest",
        "пинтрест": "pinterest",
        "reddit": "reddit",
        "реддит": "reddit",
    }
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = aliases.get(str(item or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _normalize_intent(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in {"question", "goal_request", "system_action", "feedback", "conversation"}:
        return raw
    compat = {
        "goal": "goal_request",
        "goalrequest": "goal_request",
        "system": "system_action",
        "action": "system_action",
    }
    return compat.get(raw, "conversation")


def _build_structured_prompt(text: str, active_task: dict[str, Any] | None) -> str:
    active = dict(active_task or {})
    selected_title = str(active.get("selected_research_title") or "").strip()
    active_text = str(active.get("text") or "").strip()
    active_platform = str(active.get("selected_research_platform") or "").strip()
    return (
        "Ты parser owner-команд для VITO. "
        "Нужно разобрать сообщение владельца в строгий JSON для command compiler.\n"
        "Отвечай только одним JSON-объектом без markdown.\n\n"
        "Схема:\n"
        "{\n"
        '  "intent": "question|goal_request|system_action|feedback|conversation",\n'
        '  "task_family": "deep_research|product_pipeline|platform_task|social_pack|platform_summary|status|clarification|generic",\n'
        '  "platforms": ["etsy|gumroad|amazon_kdp|printful|kofi|twitter|pinterest|reddit"],\n'
        '  "topic": "short topic or empty",\n'
        '  "selected_option": 0,\n'
        '  "target_policy": "new_object|current_task_object|explicit_target|none",\n'
        '  "auto_publish": false,\n'
        '  "needs_confirmation": false,\n'
        '  "needs_clarification": false,\n'
        '  "clarification_question": "",\n'
        '  "short_response": "",\n'
        '  "confidence": 0.0\n'
        "}\n\n"
        "Правила:\n"
        "- Если сообщение неоднозначно, ставь needs_clarification=true.\n"
        "- Не выдумывай платформы, если их нет в тексте или контексте.\n"
        "- Для коротких команд типа 'давай на этси' используй active context.\n"
        "- Для шумных сообщений с опечатками все равно заполни JSON.\n"
        "- Если это запуск действия, intent=system_action.\n"
        "- Если это просто вопрос, intent=question.\n\n"
        f"Active task title: {selected_title or active_text or 'n/a'}\n"
        f"Active task platform hint: {active_platform or 'n/a'}\n"
        f"Message: {text}\n"
    )


async def parse_owner_message_structured(
    text: str,
    active_task: dict[str, Any] | None,
    llm_router,
) -> dict[str, Any] | None:
    if llm_router is None:
        return None
    prompt = _build_structured_prompt(text, active_task)
    raw = await llm_router.call_llm(
        task_type=TaskType.ROUTINE,
        prompt=prompt,
        estimated_tokens=220,
    )
    if not raw:
        return None
    parsed = _extract_json_object(raw)
    if not parsed:
        # backward compatibility with old one-token replies
        token = str(raw or "").strip().upper().replace(" ", "_")
        if token in {"QUESTION", "GOAL_REQUEST", "SYSTEM_ACTION", "FEEDBACK", "CONVERSATION"}:
            return {
                "intent": _normalize_intent(token),
                "task_family": "generic",
                "platforms": [],
                "topic": "",
                "selected_option": 0,
                "target_policy": "none",
                "auto_publish": False,
                "needs_confirmation": False,
                "needs_clarification": False,
                "clarification_question": "",
                "short_response": "",
                "confidence": 0.51,
            }
        return None
    parsed["intent"] = _normalize_intent(parsed.get("intent"))
    parsed["task_family"] = str(parsed.get("task_family") or "generic").strip().lower()
    parsed["platforms"] = _normalize_platforms(parsed.get("platforms"))
    parsed["topic"] = str(parsed.get("topic") or "").strip()[:180]
    parsed["selected_option"] = int(parsed.get("selected_option") or 0)
    parsed["target_policy"] = str(parsed.get("target_policy") or "none").strip().lower()
    parsed["auto_publish"] = bool(parsed.get("auto_publish"))
    parsed["needs_confirmation"] = bool(parsed.get("needs_confirmation"))
    parsed["needs_clarification"] = bool(parsed.get("needs_clarification"))
    parsed["clarification_question"] = str(parsed.get("clarification_question") or "").strip()
    parsed["short_response"] = str(parsed.get("short_response") or "").strip()
    try:
        parsed["confidence"] = float(parsed.get("confidence") or 0.0)
    except Exception:
        parsed["confidence"] = 0.0
    return parsed


def _build_compiled_action(parsed: dict[str, Any], active_task: dict[str, Any] | None) -> dict[str, Any] | None:
    active = dict(active_task or {})
    platforms = list(parsed.get("platforms") or [])
    topic = str(parsed.get("topic") or active.get("selected_research_title") or active.get("text") or "").strip()
    family = str(parsed.get("task_family") or "generic").strip().lower()
    auto_publish = bool(parsed.get("auto_publish"))
    short_response = str(parsed.get("short_response") or "").strip()

    if parsed.get("needs_clarification"):
        return {
            "intent": "question",
            "response": short_response or parsed.get("clarification_question") or "Уточни, что именно запускать и на какой платформе.",
            "needs_confirmation": False,
            "compiler_source": "structured_clarification",
            "parsed": parsed,
        }

    if family == "platform_summary":
        return {
            "intent": "question",
            "response": short_response or "Соберу короткую сводку по платформам для текущей задачи.",
            "compiler_source": "structured_question",
            "parsed": parsed,
        }

    if family == "status":
        return {
            "intent": "question",
            "response": short_response or "Показываю текущий статус и активные задачи.",
            "compiler_source": "structured_question",
            "parsed": parsed,
        }

    if family == "deep_research":
        return {
            "intent": "system_action",
            "response": short_response or f"Запускаю глубокое исследование: {topic or 'текущая тема'}.",
            "actions": [{"action": "run_deep_research", "params": {"topic": topic or "текущая тема"}}],
            "needs_confirmation": bool(parsed.get("needs_confirmation")),
            "compiler_source": "structured_action",
            "parsed": parsed,
        }

    if family == "social_pack":
        channels = platforms or ["twitter", "pinterest"]
        return {
            "intent": "system_action",
            "response": short_response or f"Собираю соцпакет для {topic or 'текущего товара'}.",
            "actions": [{"action": "run_social_pack", "params": {"topic": topic or "текущий товар", "channels": channels}}],
            "needs_confirmation": bool(parsed.get("needs_confirmation")),
            "compiler_source": "structured_action",
            "parsed": parsed,
        }

    if family == "product_pipeline":
        return {
            "intent": "system_action",
            "response": short_response or (
                f"Собираю и запускаю работу на {', '.join(platforms) or 'платформе по контексту'}: {topic or 'новый продукт'}."
            ),
            "actions": [{
                "action": "run_product_pipeline",
                "params": {
                    "topic": topic or "Digital Product Starter Kit",
                    "platforms": platforms or ["gumroad"],
                    "auto_publish": auto_publish,
                },
            }],
            "needs_confirmation": bool(parsed.get("needs_confirmation")),
            "compiler_source": "structured_action",
            "parsed": parsed,
        }

    if family == "platform_task" and platforms:
        return {
            "intent": "system_action",
            "response": short_response or f"Запускаю задачу на платформе {platforms[0]}.",
            "actions": [{"action": "run_platform_task", "params": {"platform": platforms[0], "request": topic or active.get('__current_text') or ''}}],
            "needs_confirmation": bool(parsed.get("needs_confirmation")),
            "compiler_source": "structured_action",
            "parsed": parsed,
        }

    if parsed.get("intent") == "question":
        return {
            "intent": "question",
            "response": short_response or "Уточни запрос, если нужен запуск действия, или задай вопрос точнее.",
            "compiler_source": "structured_question",
            "parsed": parsed,
        }
    return None


async def compile_owner_message(
    text: str,
    active_task: dict[str, Any] | None,
    llm_router,
) -> dict[str, Any] | None:
    ruled = route_owner_dialogue(text, active_task)
    if ruled is not None:
        ruled["compiler_source"] = "rule_first"
        return ruled

    raw = str(text or "").strip()
    low = raw.lower()
    # Do not spend a structured parse on obvious plain questions; let question
    # handling and legacy intent detection keep their behavior.
    if "?" in raw and not any(tok in low for tok in ("созд", "сдел", "запус", "опубл", "пост", "листинг", "товар")):
        return None
    platformish = any(
        tok in low
        for tok in (
            "etsy", "этси", "етси",
            "gumroad", "гумроад", "гумр",
            "amazon", "амаз", "kdp", "кдп",
            "printful", "принтфул",
            "ko-fi", "kofi", "ко фи", "кофи",
            "twitter", "твиттер", "твитер", "x.com",
            "pinterest", "пинтерест", "пинтрест",
            "reddit", "реддит",
            "соц", "social",
        )
    )
    if len(raw) > 14 and not platformish:
        return None

    parsed = await parse_owner_message_structured(text, active_task, llm_router)
    if not parsed:
        return None

    # force clarification on ambiguous short commands without enough grounding
    if (
        len(raw) <= 14
        and parsed.get("intent") == "system_action"
        and not parsed.get("platforms")
        and not parsed.get("topic")
        and parsed.get("confidence", 0.0) < 0.8
    ):
        parsed["needs_clarification"] = True
        parsed["clarification_question"] = "Уточни платформу или объект, с которым работать."

    return _build_compiled_action(parsed, active_task)
