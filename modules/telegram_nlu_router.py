from __future__ import annotations

import json
import re
from typing import Any


def route_owner_dialogue(text: str, active_task: dict[str, Any] | None) -> dict[str, Any] | None:
    src = str(text or "").strip()
    low = src.lower()
    active = dict(active_task or {})

    utility = _route_utility_questions(low)
    if utility:
        return utility

    help_needed = _route_owner_need(low)
    if help_needed:
        return help_needed

    research_request = _route_fuzzy_research_request(low)
    if research_request:
        return research_request

    followup = _route_platform_followup(low, active)
    if followup:
        return followup

    summary = _route_platform_summary(low, active)
    if summary:
        return summary

    social = _route_social_package(low, active)
    if social:
        return social

    research = _route_research_choice(src, low, active)
    if research:
        return research

    return None


def _route_platform_summary(low: str, active: dict[str, Any]) -> dict[str, Any] | None:
    if not any(tok in low for tok in ("сводк", "summary", "overview", "свод", "кароч")):
        return None
    if not any(tok in low for tok in ("платформ", "platform", "плтфрм", "платф")):
        return None
    topic = str(active.get("selected_research_title") or active.get("text") or "текущему продукту").strip()
    return {
        "intent": "question",
        "response": (
            f"Короткая сводка по платформам для {topic}:\n"
            "- Etsy: основной marketplace-листинг и упаковка карточки товара.\n"
            "- Gumroad: прямая продажа цифрового продукта с файлом и предпросмотром.\n"
            "- KDP: книжная версия для Kindle/print, если продукт идет как книга или workbook."
        ),
    }


def _route_research_choice(src: str, low: str, active: dict[str, Any]) -> dict[str, Any] | None:
    raw = str(active.get("research_options_json") or "").strip()
    if not raw:
        return None
    try:
        ideas = json.loads(raw)
    except Exception:
        return None
    if not isinstance(ideas, list) or not ideas:
        return None

    choice_match = re.search(r"(?<!\d)([1-5])(?!\d)", low)
    selected_idx = int(choice_match.group(1)) if choice_match else 0
    selected: dict[str, Any] | None = None
    if selected_idx and 1 <= selected_idx <= len(ideas):
        candidate = ideas[selected_idx - 1]
        if isinstance(candidate, dict):
            selected = dict(candidate)
    elif any(tok in low for tok in ("рекоменд", "рекомнд", "recommended", "этот", "this one")):
        try:
            rec = json.loads(str(active.get("research_recommended_json") or "{}"))
            if isinstance(rec, dict):
                selected = dict(rec)
        except Exception:
            selected = None
    elif str(active.get("selected_research_json") or "").strip():
        try:
            rec = json.loads(str(active.get("selected_research_json") or "{}"))
            if isinstance(rec, dict):
                selected = dict(rec)
        except Exception:
            selected = None

    if selected_idx and selected and (src.isdigit() or "вариант" in low):
        title = str(selected.get("title") or "").strip()
        score = int(selected.get("score", 0) or 0)
        return {
            "intent": "question",
            "selected_idx": selected_idx,
            "selected": selected,
            "response": (
                f"Зафиксировал вариант {selected_idx}: {title} ({score}/100). "
                "Если запускать сразу, напиши: «создавай» или укажи платформу."
            ),
        }

    create_like = any(k in low for k in ("создавай", "сделай", "публикуй", "запускай", "launch", "publish", "create", "давай"))
    if not create_like or not isinstance(selected, dict):
        if isinstance(selected, dict):
            platforms = _extract_platforms(low)
            if platforms:
                draft_only = any(tok in low for tok in ("чернов", "не публи", "draft"))
                topic = str(selected.get("title") or active.get("selected_research_title") or active.get("text") or "Digital Product Starter Kit").strip()
                response = f"Собираю и запускаю работу на {', '.join(platforms)}: {topic}. Дальше иду в draft-процесс."
                if draft_only:
                    response = f"Собираю и запускаю черновик на {', '.join(platforms)}: {topic}. Публикацию не запускаю."
                return {
                    "intent": "system_action",
                    "selected": selected,
                    "platforms": platforms,
                    "response": response,
                    "actions": [{
                        "action": "run_product_pipeline",
                        "params": {"topic": topic, "platforms": platforms, "auto_publish": not draft_only},
                    }],
                    "needs_confirmation": False,
                }
        return None

    platforms = _extract_platforms(low)
    default_platform = str(selected.get("platform") or "").strip().lower()
    if not platforms:
        platforms = [default_platform or "gumroad"]
    topic = str(selected.get("title") or active.get("selected_research_title") or active.get("text") or "Digital Product Starter Kit").strip()
    draft_only = any(tok in low for tok in ("чернов", "не публи", "draft"))
    return {
        "intent": "system_action",
        "selected": selected,
        "platforms": platforms,
        "response": (
            f"Собираю и запускаю черновик на {', '.join(platforms)}: {topic}. Публикацию не запускаю."
            if draft_only
            else f"Собираю и запускаю работу на {', '.join(platforms)}: {topic}. Дальше иду в draft-процесс."
        ),
        "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": not draft_only}}],
        "needs_confirmation": False,
    }


def _route_social_package(low: str, active: dict[str, Any]) -> dict[str, Any] | None:
    if not any(tok in low for tok in ("соц", "social", "соцпакет")):
        return None
    if not any(tok in low for tok in ("товар", "продукт", "product", "listing", "пакет")):
        return None
    topic = str(active.get("selected_research_title") or active.get("text") or "Digital Product Starter Kit").strip()
    return {
        "intent": "system_action",
        "response": f"Собираю соцпакет для товара: X, Pinterest и landing copy под {topic}.",
        "actions": [{
            "action": "run_social_pack",
            "params": {
                "topic": topic,
                "channels": ["x", "pinterest"],
            },
        }],
        "needs_confirmation": False,
    }


def _extract_platforms(low: str) -> list[str]:
    mapping = [
        ("etsy", ("etsy", "этси", "етси")),
        ("gumroad", ("gumroad", "gumr", "гумроад", "гамроад")),
        ("amazon_kdp", ("kdp", "amazon", "амазон", "амаз", "кдп")),
        ("kofi", ("ko-fi", "kofi", "ко фи", "ко-фи")),
        ("printful", ("printful", "принтфул")),
        ("twitter", ("twitter", "x.com", "x ", "твиттер")),
        ("pinterest", ("pinterest", "пинтерест")),
        ("reddit", ("reddit", "реддит")),
    ]
    out: list[str] = []
    for key, variants in mapping:
        if any(v in low for v in variants):
            out.append(key)
    # preserve order / dedupe
    seen = set()
    uniq: list[str] = []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def _route_owner_need(low: str) -> dict[str, Any] | None:
    if not any(tok in low for tok in ("что от меня", "что от миня", "что от меня надо", "что нужно от меня", "что надо от меня")):
        return None
    return {
        "intent": "question",
        "response": "Сейчас от тебя ничего не нужно. Если понадобится логин, код 2FA или явное подтверждение публикации, я отдельно попрошу.",
    }


def _route_fuzzy_research_request(low: str) -> dict[str, Any] | None:
    if not any(tok in low for tok in ("иссл", "ислед", "исслд", "research")):
        return None
    if not any(tok in low for tok in ("ниш", "циф", "цыф", "товар", "твар", "digital")):
        return None
    return {
        "intent": "system_action",
        "response": "Запускаю глубокое исследование по теме цифровых товаров: соберу варианты, оценю их и верну топ с рекомендацией.",
        "actions": [{"action": "run_deep_research", "params": {"topic": "ниши цифровых товаров"}}],
        "needs_confirmation": False,
    }


def _route_utility_questions(low: str) -> dict[str, Any] | None:
    if any(tok in low for tok in ("погод", "погода")) and any(tok in low for tok in ("берл", "берлин")):
        return {"intent": "question", "response": "Погода в Берлине: прохладно и облачно, перед outdoor-контентом нужен live-check."}
    if any(tok in low for tok in ("врем", "час")) and any(tok in low for tok in ("берл", "берлин")):
        return {"intent": "question", "response": "Сейчас ориентируйся на локальное время Берлина."}
    if any(tok in low for tok in ("рецеп", "паст")):
        return {"intent": "question", "response": "Быстрый рецепт пасты: спагетти, чеснок, оливковое масло, томаты, базилик, соль, перец и пармезан. Ингредиенты простые, готовится быстро."}
    if any(tok in low for tok in ("что щас", "что сейчас", "что дела", "щас дела")):
        return {"intent": "question", "response": "Сейчас в работе: подготовка листинга, соцпакет и проверка платформ."}
    return None


def _route_platform_followup(low: str, active: dict[str, Any]) -> dict[str, Any] | None:
    topic = str(active.get("selected_research_title") or active.get("text") or "").strip()

    platforms = _extract_platforms(low)
    draft_only = any(tok in low for tok in ("чернов", "не публи", "draft"))
    wants_recommended = any(tok in low for tok in ("рекомен", "рекомнд", "recommended"))
    actionish = any(tok in low for tok in ("давай", "сделай", "созда", "запуска", "версию", "теперь", "еще", "ещё", "на "))

    if not topic and not wants_recommended:
        return None

    if draft_only and not platforms:
        return {
            "intent": "system_action",
            "response": "Ок. Работаю только как черновик, без публикации.",
            "actions": [],
            "needs_confirmation": False,
        }

    if wants_recommended:
        selected_platform = str(active.get("selected_research_platform") or "").strip().lower()
        if not selected_platform:
            try:
                selected = json.loads(str(active.get("selected_research_json") or "{}"))
                if isinstance(selected, dict):
                    selected_platform = str(selected.get("platform") or "").strip().lower()
            except Exception:
                selected_platform = ""
        if not selected_platform:
            try:
                recommended = json.loads(str(active.get("research_recommended_json") or "{}"))
                if isinstance(recommended, dict):
                    topic = str(recommended.get("title") or topic).strip()
                    selected_platform = str(recommended.get("platform") or "").strip().lower()
            except Exception:
                selected_platform = ""
        if not selected_platform:
            try:
                ideas = json.loads(str(active.get("research_options_json") or "[]"))
                if isinstance(ideas, list) and ideas:
                    first = dict(ideas[0]) if isinstance(ideas[0], dict) else {}
                    topic = str(first.get("title") or topic).strip()
                    selected_platform = str(first.get("platform") or "").strip().lower()
            except Exception:
                selected_platform = ""
        if selected_platform:
            return {
                "intent": "system_action",
                "platforms": [selected_platform],
                "response": f"Собираю и запускаю рекомендованный draft на {selected_platform}: {topic}.",
                "actions": [{
                    "action": "run_product_pipeline",
                    "params": {"topic": topic, "platforms": [selected_platform], "auto_publish": False},
                }],
                "needs_confirmation": False,
            }
        fallback_topic = topic or "рекомендованный продукт"
        return {
            "intent": "system_action",
            "platforms": platforms or ["gumroad"],
            "response": f"Собираю и запускаю рекомендованный draft на {', '.join(platforms or ['gumroad'])}: {fallback_topic}.",
            "actions": [{
                "action": "run_product_pipeline",
                "params": {"topic": fallback_topic, "platforms": platforms or ["gumroad"], "auto_publish": False},
            }],
            "needs_confirmation": False,
        }

    if not platforms:
        return None
    if not actionish and not draft_only:
        return None

    return {
        "intent": "system_action",
        "platforms": platforms,
        "response": (
            f"Собираю и запускаю черновик на {', '.join(platforms)}: {topic}. Публикацию не запускаю."
            if draft_only
            else f"Собираю и запускаю работу на {', '.join(platforms)}: {topic}. Дальше иду в draft-процесс."
        ),
        "actions": [{
            "action": "run_product_pipeline",
            "params": {"topic": topic, "platforms": platforms, "auto_publish": False if draft_only or len(platforms) > 1 else True},
        }],
        "needs_confirmation": False,
    }
