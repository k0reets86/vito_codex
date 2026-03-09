"""Deterministic translation/localization helpers for TranslationAgent."""

from __future__ import annotations

import re
from typing import Any

KNOWN_TERMS = {
    "etsy": "Etsy",
    "gumroad": "Gumroad",
    "printful": "Printful",
    "pinterest": "Pinterest",
    "kdp": "KDP",
    "seo": "SEO",
    "roi": "ROI",
    "cac": "CAC",
    "ltv": "LTV",
    "ai": "AI",
}

LOCALE_PROFILES = {
    "de": {"tone": "precise", "currency": "EUR", "market_hint": "DACH marketplace phrasing"},
    "pl": {"tone": "direct", "currency": "PLN", "market_hint": "Polish ecommerce phrasing"},
    "ua": {"tone": "clear", "currency": "UAH", "market_hint": "Ukrainian local buyer phrasing"},
    "en": {"tone": "neutral", "currency": "USD", "market_hint": "US/global digital goods phrasing"},
}


def extract_glossary_terms(text: str) -> list[str]:
    raw = str(text or "")
    found: list[str] = []
    low = raw.lower()
    for key, term in KNOWN_TERMS.items():
        if key in low and term not in found:
            found.append(term)
    return found


def build_locale_profile(target_lang: str) -> dict[str, Any]:
    lang = str(target_lang or "").strip().lower()
    return dict(LOCALE_PROFILES.get(lang, LOCALE_PROFILES["en"]))


def build_consistency_checks(source_text: str, translated_text: str, terms: list[str]) -> list[dict[str, Any]]:
    src = str(source_text or "")
    out = str(translated_text or "")
    checks: list[dict[str, Any]] = []
    checks.append({"name": "non_empty", "ok": bool(out.strip())})
    checks.append({"name": "length_ratio_reasonable", "ok": 0.35 <= (len(out) / max(len(src), 1)) <= 3.2})
    checks.append({"name": "trailing_punctuation_preserved", "ok": (src[-1:] in ".!?" and out[-1:] in ".!?") or (src[-1:] not in ".!?")})
    checks.append({
        "name": "glossary_terms_preserved",
        "ok": all(term.lower() in out.lower() or term.lower() not in src.lower() for term in terms),
        "terms": list(terms),
    })
    return checks


def build_translation_route(source_lang: str, target_lang: str, text: str) -> dict[str, Any]:
    terms = extract_glossary_terms(text)
    return {
        "provider_route": "glossary_first_then_llm" if terms else "standard_translation",
        "glossary_terms": terms,
        "locale_profile": build_locale_profile(target_lang),
        "risk_flags": ["script_mismatch"] if _has_script_mismatch(source_lang, target_lang, text) else [],
    }


def build_listing_localization_notes(listing_data: dict[str, Any], target_lang: str) -> dict[str, Any]:
    title = str((listing_data or {}).get("title") or "")
    description = str((listing_data or {}).get("description") or "")
    terms = extract_glossary_terms(f"{title}\n{description}")
    return {
        "glossary_terms": terms,
        "locale_profile": build_locale_profile(target_lang),
        "preserve_tokens": [t for t in terms if t in {"Etsy", "Gumroad", "Printful", "KDP", "SEO", "ROI", "CAC", "LTV", "AI"}],
        "listing_sections": [k for k, v in (listing_data or {}).items() if str(v or "").strip()],
    }


def _has_script_mismatch(source_lang: str, target_lang: str, text: str) -> bool:
    src = str(source_lang or "").strip().lower()
    tgt = str(target_lang or "").strip().lower()
    raw = str(text or "")
    cyrillic = bool(re.search(r"[А-Яа-яІіЇїЄєҐґ]", raw))
    latin = bool(re.search(r"[A-Za-z]", raw))
    if src in {"ru", "ua"} and tgt in {"en", "de", "pl"}:
        return cyrillic and not latin
    if src in {"en", "de", "pl"} and tgt in {"ru", "ua"}:
        return latin and not cyrillic
    return False
