from __future__ import annotations

import re
from datetime import datetime, timezone


def extract_research_topic(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"(?i)\b(проведи|сделай|запусти|выполни)\b", "", s).strip()
    s = re.sub(r"(?i)\b(глубокое|глубокий|deep)\b", "", s).strip()
    s = re.sub(r"(?i)\b(исследование|анализ|research)\b", "", s).strip(" :,-")
    return s or "digital product niches for US market"


def extract_product_topic(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"(?i)\b(сделай|создай|запусти|подготовь|оформи)\b", "", s).strip()
    s = re.sub(r"(?i)\b(товар|продукт|под ключ|turnkey|pipeline)\b", "", s).strip(" :,-")
    return s or "Digital Product Starter Kit"


def extract_platforms(text: str) -> list[str]:
    s = str(text or "").lower()
    out: list[str] = []
    for k, v in (
        ("gumroad", "gumroad"),
        ("гумроад", "gumroad"),
        ("etsy", "etsy"),
        ("этси", "etsy"),
        ("етси", "etsy"),
        ("kofi", "kofi"),
        ("ko-fi", "kofi"),
        ("кофи", "kofi"),
        ("amazon", "amazon_kdp"),
        ("kdp", "amazon_kdp"),
        ("амазон", "amazon_kdp"),
    ):
        if k in s and v not in out:
            out.append(v)
    return out or ["gumroad"]


def is_time_query(lower: str) -> bool:
    time_words = ("время", "час", "дата", "time", "what time", "date", "сколько время")
    return any(w in lower for w in time_words) and len(lower) < 60


def format_time_answer() -> str:
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    return (
        f"Сейчас: {now_local.strftime('%Y-%m-%d %H:%M')} (локальное время сервера)\n"
        f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}\n"
        f"День недели: {now_utc.strftime('%A')}"
    )


def extract_target_title(text: str) -> str:
    raw = str(text or "").strip()
    m = re.search(r"[\"“'«](.+?)[\"”'»]", raw)
    if m:
        return str(m.group(1) or "").strip()
    m2 = re.search(r"(?i)(?:заполни|редактируй|fill)\s+(.+)$", raw)
    if m2:
        v = str(m2.group(1) or "").strip()
        v = re.sub(r"(?i)\b(на английском|english|пожалуйста)\b.*$", "", v).strip(" .,:;")
        return v
    return ""


def extract_platform_key(text: str) -> str:
    s = str(text or "").lower()
    mapping = (
        ("amazon_kdp", ("amazon", "амазон", "kdp", "кдп")),
        ("gumroad", ("gumroad", "гумроад", "гамроад")),
        ("etsy", ("etsy", "етси", "этси")),
        ("kofi", ("kofi", "ko-fi", "ko fi", "кофи", "ко-фи", "ко фи")),
        ("printful", ("printful", "принтфул")),
        ("twitter", ("twitter", "x.com", "икс", "твиттер")),
        ("reddit", ("reddit", "реддит")),
        ("pinterest", ("pinterest", "пинтерест")),
        ("threads", ("threads", "тредс", "тхредс")),
    )
    for key, aliases in mapping:
        if any(a in s for a in aliases):
            return key
    return ""


def looks_like_imperative_request(text: str) -> bool:
    s = str(text or "").strip().lower()
    if not s:
        return False
    if s.endswith("?"):
        return False
    verbs = (
        "сделай", "создай", "запусти", "проверь", "найди", "заполни",
        "опубликуй", "удали", "редактируй", "исправь", "почини",
        "зайди", "зайти", "войди", "войти", "открой",
    )
    return any(v in s for v in verbs)
