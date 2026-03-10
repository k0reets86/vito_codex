from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from config.paths import root_path
from config.settings import settings


def _parse_proxy_entries(raw: str) -> list[str]:
    return [x.strip() for x in str(raw or "").split(",") if x.strip()]


def configured_proxy_pool() -> list[str]:
    return _parse_proxy_entries(getattr(settings, "BROWSER_PROXY_POOL", ""))


def _health_state_path() -> Path:
    return Path(root_path("runtime", "browser_proxy_health.json"))


def _load_health_state() -> dict[str, Any]:
    p = _health_state_path()
    if not p.exists():
        return {"proxies": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            proxies = data.get("proxies")
            if isinstance(proxies, dict):
                return {"proxies": proxies}
    except Exception:
        pass
    return {"proxies": {}}


def _save_health_state(state: dict[str, Any]) -> None:
    p = _health_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _proxy_health(server: str) -> dict[str, Any]:
    state = _load_health_state()
    proxies = state.get("proxies") if isinstance(state, dict) else None
    if not isinstance(proxies, dict):
        return {}
    item = proxies.get(str(server or ""))
    return dict(item) if isinstance(item, dict) else {}


def report_proxy_result(
    server: str,
    *,
    ok: bool,
    service: str = "",
    reason: str = "",
    cooldown_sec: int | None = None,
) -> None:
    srv = str(server or "").strip()
    if not srv:
        return
    cd = int(cooldown_sec or getattr(settings, "BROWSER_PROXY_COOLDOWN_SEC", 900) or 900)
    now = int(time.time())
    state = _load_health_state()
    proxies = state.setdefault("proxies", {})
    cur = proxies.get(srv) if isinstance(proxies, dict) else None
    if not isinstance(cur, dict):
        cur = {}
    if ok:
        cur.update(
            {
                "healthy": True,
                "last_ok_at": now,
                "cooldown_until": 0,
                "fail_count": 0,
                "last_service": str(service or ""),
                "last_reason": str(reason or ""),
            }
        )
    else:
        fail_count = int(cur.get("fail_count", 0) or 0) + 1
        cur.update(
            {
                "healthy": False,
                "last_fail_at": now,
                "cooldown_until": now + max(60, cd * min(fail_count, 3)),
                "fail_count": fail_count,
                "last_service": str(service or ""),
                "last_reason": str(reason or ""),
            }
        )
    proxies[srv] = cur
    _save_health_state(state)


def _available_pool(service: str) -> list[str]:
    pool = configured_proxy_pool()
    if not pool:
        return []
    now = int(time.time())
    healthy: list[str] = []
    for server in pool:
        health = _proxy_health(server)
        cooldown_until = int(health.get("cooldown_until", 0) or 0)
        if cooldown_until and cooldown_until > now:
            continue
        healthy.append(server)
    return healthy or pool


def select_proxy_for_service(service: str, *, task_root_id: str = "", attempt: int = 0) -> dict[str, Any] | None:
    pool = _available_pool(service)
    if not pool:
        return None
    svc = str(service or "generic").strip().lower() or "generic"
    basis = f"{svc}:{task_root_id}:{int(attempt)}"
    idx = int(hashlib.sha256(basis.encode("utf-8")).hexdigest(), 16) % len(pool)
    server = pool[idx]
    health = _proxy_health(server)
    return {
        "server": server,
        "index": idx,
        "service": svc,
        "attempt": int(attempt),
        "pool_size": len(pool),
        "healthy": bool(health.get("healthy", True)),
        "cooldown_until": int(health.get("cooldown_until", 0) or 0),
    }
