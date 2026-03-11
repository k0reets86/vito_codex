from __future__ import annotations

import re

from modules.owner_preference_model import OwnerPreferenceModel


def remember_owner_profile_fact(engine, text: str) -> None:
    """Best-effort extraction of stable owner profile facts from natural speech."""
    source_text = extract_owner_raw_text(text)
    owner_name = extract_owner_name(source_text)
    if not owner_name and is_probable_name_reply(engine, source_text):
        owner_name = source_text.title()
    if not owner_name:
        return
    try:
        OwnerPreferenceModel().set_preference(
            key="owner_name",
            value={"name": owner_name},
            source="owner",
            confidence=1.0,
            notes="extracted_from_chat",
        )
    except Exception:
        pass


def extract_owner_raw_text(text: str) -> str:
    raw = str(text or "").strip()
    if "[REPLY_CONTEXT]" not in raw:
        return raw
    m = re.search(r"owner_reply=(.*)", raw)
    if m:
        return str(m.group(1) or "").strip()
    return raw


def is_probable_name_reply(engine, text: str) -> bool:
    raw = str(text or "").strip()
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\\-]{2,40}", raw):
        return False
    if raw.lower() in {"да", "нет", "ок", "yes", "no", "approve", "reject"}:
        return False
    prompts = ("как тебя зовут", "как вас зовут", "твое имя", "твоё имя", "ваше имя", "your name")
    for turn in reversed(engine._context[-6:]):
        if turn.role != "assistant":
            continue
        if engine._has_keywords(engine._normalize_for_nlu(turn.text), prompts, fuzzy=True):
            return True
    return False


def resolve_owner_name(engine) -> str:
    try:
        pref = OwnerPreferenceModel().get_preference("owner_name")
        if pref and isinstance(pref.get("value"), dict):
            name = str(pref["value"].get("name", "")).strip()
            if name:
                return name
    except Exception:
        pass
    for turn in reversed(engine._context):
        if turn.role != "user":
            continue
        guessed = extract_owner_name(turn.text)
        if guessed:
            return guessed
    return ""


def extract_owner_name(text: str) -> str:
    raw = extract_owner_raw_text(text)
    if not raw:
        return ""
    patterns = [
        r"\bменя\s+зовут\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
        r"\bmy\s+name\s+is\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
        r"\bi\s*am\s+([A-Za-zА-Яа-яЁё\-]{2,40})",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().title()
    return ""
