"""Assess owner-grade platform readiness from sessions, probes and validation reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT
from modules.service_session_registry import load_service_sessions
from modules.platform_validation_registry import load_platform_validation_registry

RUNTIME = PROJECT_ROOT / "runtime"
REPORTS = PROJECT_ROOT / "reports"


@dataclass
class PlatformReadiness:
    service: str
    session_present: bool
    session_verified: bool
    probe_present: bool
    owner_grade_state: str
    can_validate_now: bool
    blocker: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _latest_validation_wave() -> dict[str, Any] | None:
    files = sorted(REPORTS.glob("VITO_PLATFORM_LIVE_VALIDATION_WAVE_*.json"))
    if not files:
        return None
    return _load_json(files[-1])


def _wave_state_map() -> dict[str, str]:
    data = _latest_validation_wave() or {}
    checks = data.get("checks") or []
    state_map: dict[str, str] = {}
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            svc = str(item.get("platform") or "").strip().lower()
            state = str(item.get("state") or "").strip().lower()
            if svc:
                state_map[svc] = state
    return state_map


def _probe_exists(service: str) -> bool:
    mapping = {
        "etsy": RUNTIME / "etsy_owner_grade_probe.json",
        "amazon_kdp": RUNTIME / "kdp_owner_grade_probe.json",
        "printful": RUNTIME / "linked_platform_current_probe.json",
        "gumroad": RUNTIME / "gumroad_zrvfrg_public_probe.json",
        "twitter": RUNTIME / "twitter_gumroad_compose_result.json",
        "pinterest": RUNTIME / "pinterest_after_cleanup_verify" / "result.json",
        "kofi": RUNTIME / "kofi_browser_publish.png",
    }
    path = mapping.get(service)
    return bool(path and path.exists())


def assess_platform_readiness(services: list[str] | None = None) -> list[dict[str, Any]]:
    sessions = load_service_sessions()
    state_map = _wave_state_map()
    registry = load_platform_validation_registry()
    svc_list = services or [
        "etsy",
        "printful",
        "twitter",
        "gumroad",
        "kofi",
        "amazon_kdp",
        "pinterest",
    ]
    results: list[dict[str, Any]] = []
    for raw in svc_list:
        service = str(raw or "").strip().lower()
        row = dict(sessions.get(service) or {})
        session_present = bool(row.get("storage_exists") or row.get("profile_dir"))
        session_verified = bool(row.get("verified_at"))
        probe_present = _probe_exists(service)
        registry_row = dict(registry.get(service) or {})
        owner_grade_state = state_map.get(service) or str(registry_row.get("state") or "unknown")
        blocker = ""
        if not session_present and service in {"etsy", "printful", "twitter", "amazon_kdp"}:
            blocker = "missing_session"
        elif not probe_present:
            blocker = "missing_probe"
        can_validate_now = session_present and probe_present
        if not blocker and owner_grade_state == "blocked":
            blocker = "last_validation_blocked"
        recommended_action = ""
        if blocker == "missing_session":
            recommended_action = f"reauth:{service}"
        elif blocker == "missing_probe":
            recommended_action = f"run_probe:{service}"
        elif blocker == "last_validation_blocked":
            recommended_action = f"owner_grade_validate:{service}"
        elif owner_grade_state != "owner_grade":
            recommended_action = f"owner_grade_validate:{service}"
        results.append(
            PlatformReadiness(
                service=service,
                session_present=session_present,
                session_verified=session_verified,
                probe_present=probe_present,
                owner_grade_state=owner_grade_state,
                can_validate_now=can_validate_now,
                blocker=blocker,
                recommended_action=recommended_action,
            ).to_dict()
        )
    return results
