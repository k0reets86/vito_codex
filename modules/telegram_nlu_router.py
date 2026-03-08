from __future__ import annotations

import json
import re
from typing import Any


def route_owner_dialogue(text: str, active_task: dict[str, Any] | None) -> dict[str, Any] | None:
    src = str(text or "").strip()
    low = src.lower()
    active = dict(active_task or {})

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
    if not any(tok in low for tok in ("сводк", "summary", "overview")):
        return None
    if not any(tok in low for tok in ("платформ", "platform")):
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
    elif any(tok in low for tok in ("рекоменд", "recommended", "этот", "this one")):
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

    create_like = any(k in low for k in ("создавай", "сделай", "публикуй", "запускай", "launch", "publish", "create"))
    if not create_like or not isinstance(selected, dict):
        return None

    platforms = _extract_platforms(low)
    default_platform = str(selected.get("platform") or "").strip().lower()
    if not platforms:
        platforms = [default_platform or "gumroad"]
    topic = str(selected.get("title") or active.get("selected_research_title") or active.get("text") or "Digital Product Starter Kit").strip()
    return {
        "intent": "system_action",
        "selected": selected,
        "platforms": platforms,
        "response": f"Собираю и запускаю работу на {', '.join(platforms)}: {topic}. Дальше иду в draft-процесс.",
        "actions": [{"action": "run_product_pipeline", "params": {"topic": topic, "platforms": platforms, "auto_publish": True}}],
        "needs_confirmation": False,
    }


def _route_social_package(low: str, active: dict[str, Any]) -> dict[str, Any] | None:
    if not any(tok in low for tok in ("соц", "social", "соцпакет")):
        return None
    if not any(tok in low for tok in ("товар", "продукт", "product", "listing")):
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
        ("gumroad", ("gumroad", "гумроад", "гамроад")),
        ("amazon_kdp", ("kdp", "amazon", "амазон", "кдп")),
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
