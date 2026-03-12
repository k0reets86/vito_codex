from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def resolve_button_command(button_map: dict[str, str], text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw in button_map:
        return button_map[raw]
    normalized = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9_ ]+", " ", raw).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    aliases = {
        "статус": "status",
        "в работе": "tasks",
        "цели": "goals",
        "расходы": "spend",
        "новая цель": "goal",
        "задачи": "tasks",
        "исследовать": "research_hub",
        "создать": "goal",
        "платформы": "platforms_hub",
        "входы": "auth_hub",
        "сводка": "report",
        "отчёт": "report",
        "отчет": "report",
        "еще": "more",
        "ещё": "more",
        "помощь": "help",
        "ежедневные": "help_daily",
        "редкие": "help_rare",
        "системные": "help_system",
        "главная": "start",
        "home": "start",
        "main": "start",
        "menu": "help",
        "daily": "help_daily",
        "daily commands": "help_daily",
        "rare": "help_rare",
        "system": "help_system",
        "system commands": "help_system",
    }
    return aliases.get(normalized)


def detect_service_login_request(
    text: str,
    service_catalog: dict[str, dict[str, Any]],
    extract_custom_login_target,
    extract_loose_site_target,
) -> str:
    s = str(text or "").strip().lower()
    if not s:
        return ""
    has_action = any(
        x in s
        for x in (
            "зайди",
            "зайти",
            "войди",
            "вход",
            "логин",
            "login",
            "auth",
            "авториза",
            "войти",
            "открой",
            "обнови сес",
            "обновить сес",
            "refresh session",
            "перелогин",
            "перевойти",
        )
    )
    if not has_action:
        return ""
    for service, meta in service_catalog.items():
        keys = tuple(meta.get("aliases") or ())
        if any(k in s for k in keys):
            return service
    custom = extract_custom_login_target(s)
    if custom:
        return f"custom:{custom}"
    loose = extract_loose_site_target(s)
    if loose:
        return f"custom:{loose}"
    return ""


def detect_service_from_text(
    text: str,
    service_catalog: dict[str, dict[str, Any]],
    extract_custom_login_target,
    extract_loose_site_target,
) -> str:
    s = str(text or "").strip().lower()
    if not s:
        return ""
    for service, meta in service_catalog.items():
        keys = tuple(meta.get("aliases") or ())
        if any(k in s for k in keys):
            return service
    custom = extract_custom_login_target(s)
    if custom:
        return f"custom:{custom}"
    loose = extract_loose_site_target(s)
    if loose:
        return f"custom:{loose}"
    return ""


def service_auth_meta(service: str, service_catalog: dict[str, dict[str, Any]]) -> tuple[str, str]:
    svc = str(service or "").strip().lower()
    if svc.startswith("custom:"):
        target = svc.split(":", 1)[1].strip()
        if target.startswith("http://") or target.startswith("https://"):
            auth_url = target
            host = urlparse(target).netloc or target
        else:
            host = target
            auth_url = f"https://{target}"
        return f"Сайт {host}", auth_url
    meta = service_catalog.get(svc) or {}
    title = str(meta.get("title") or service)
    url = str(meta.get("url") or "")
    return title, url


def is_manual_auth_service(service: str, service_catalog: dict[str, dict[str, Any]]) -> bool:
    svc = str(service or "").strip().lower()
    if svc.startswith("custom:"):
        return True
    meta = service_catalog.get(svc) or {}
    return bool(meta.get("manual_fallback", False))


def requires_strict_auth_verification(service: str, settings_obj) -> bool:
    svc = str(service or "").strip().lower()
    if svc == "twitter":
        mode = str(getattr(settings_obj, "TWITTER_MODE", "api") or "api").strip().lower()
        return mode not in {"browser", "browser_only"}
    if svc == "gumroad":
        mode = str(getattr(settings_obj, "GUMROAD_MODE", "api") or "api").strip().lower()
        return mode not in {"browser", "browser_only"}
    return svc in {"amazon_kdp", "etsy", "printful", "kofi"}


def touch_service_context(agent, service: str) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    agent._last_service_context = svc
    agent._last_service_context_at = datetime.now(timezone.utc).isoformat()
    agent._sync_owner_task_service_context(svc)
    agent._save_auth_state()
    agent._record_context_learning(
        skill_name="service_context_tracking",
        description=(
            "После команд входа запоминай последний сервис и используй его как контекст для коротких уточнений "
            "вроде 'статус', 'проверь аккаунт', 'вход ок?'."
        ),
        anti_pattern=(
            "Плохо: терять контекст и трактовать короткое 'статус' как общий статус VITO, "
            "когда владелец только что говорил о конкретной платформе."
        ),
        method={"service": svc},
    )


def sync_owner_task_service_context(agent, service: str) -> None:
    if not agent._owner_task_state:
        return
    svc = str(service or "").strip().lower()
    if not svc:
        return
    try:
        agent._owner_task_state.enrich_active(service_context=svc)
    except Exception:
        pass


def service_storage_state_path(service: str, storage_state_path_for_service, settings_obj, project_root: Path) -> Path | None:
    svc = str(service or "").strip().lower()
    p = storage_state_path_for_service(svc)
    if p is not None:
        return p
    raw = ""
    mapping = {
        "threads": ("THREADS_STORAGE_STATE_FILE", "runtime/threads_storage_state.json"),
        "instagram": ("INSTAGRAM_STORAGE_STATE_FILE", "runtime/instagram_storage_state.json"),
        "facebook": ("FACEBOOK_STORAGE_STATE_FILE", "runtime/facebook_storage_state.json"),
        "tiktok": ("TIKTOK_STORAGE_STATE_FILE", "runtime/tiktok_storage_state.json"),
        "linkedin": ("LINKEDIN_STORAGE_STATE_FILE", "runtime/linkedin_storage_state.json"),
        "youtube": ("YOUTUBE_STORAGE_STATE_FILE", "runtime/youtube_storage_state.json"),
    }
    if svc in mapping:
        env_name, default = mapping[svc]
        raw = str(getattr(settings_obj, env_name, default) or default)
    if not raw:
        return None
    p2 = Path(raw)
    if not p2.is_absolute():
        p2 = project_root / p2
    return p2


def has_cookie_storage_state(agent, service: str, since_iso: str = "") -> tuple[bool, str]:
    p = agent._service_storage_state_path(service)
    if p is None:
        return False, "no_storage_path"
    if not p.exists():
        return False, "storage_missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cookies = data.get("cookies") if isinstance(data, dict) else None
        if not isinstance(cookies, list) or not cookies:
            return False, "cookies_missing"
        if since_iso:
            try:
                req_dt = datetime.fromisoformat(str(since_iso))
                if req_dt.tzinfo is None:
                    req_dt = req_dt.replace(tzinfo=timezone.utc)
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                if mtime < req_dt:
                    return False, "storage_not_updated_after_login"
            except Exception:
                pass
        return True, "storage_cookies_ok"
    except Exception:
        return False, "storage_parse_failed"


def mark_service_auth_confirmed(
    agent,
    service: str,
    settings_obj,
    get_browser_runtime_profile,
    capture_session_snapshot,
) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    agent._service_auth_confirmed[svc] = datetime.now(timezone.utc).isoformat()
    try:
        ttl_sec = int(getattr(settings_obj, "AUTH_SESSION_TTL_SEC", 10800) or 10800)
        agent._auth_broker.mark_authenticated(svc, method="manual_confirmed", detail="owner_confirmed", ttl_sec=ttl_sec)
    except Exception:
        pass
    try:
        profile = get_browser_runtime_profile(svc)
        capture_session_snapshot(
            svc,
            storage_state_path=profile.storage_state_path,
            profile_dir=profile.persistent_profile_dir,
            verified=True,
        )
    except Exception:
        pass
    agent._save_auth_state()


def clear_service_auth_confirmed(agent, service: str, clear_service_session) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    if svc in agent._service_auth_confirmed:
        agent._service_auth_confirmed.pop(svc, None)
        try:
            agent._auth_broker.clear(svc)
        except Exception:
            pass
        try:
            clear_service_session(svc)
        except Exception:
            pass
        agent._save_auth_state()


def auth_interrupt_prompt(service: str, get_browser_runtime_profile, get_profile_completion_runbook) -> str:
    profile = get_browser_runtime_profile(service)
    completion = get_profile_completion_runbook(service)
    base = str(profile.get("otp_prompt") or f"Для {service} нужен ручной вход в browser-сессии.")
    route = str(completion.get("route") or "").strip()
    if completion.get("requires_profile_completion") and route:
        return f"{base} Если платформа упирается в незаполненный профиль, сначала пройди: {route}"
    return base
