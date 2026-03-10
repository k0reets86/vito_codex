from __future__ import annotations

import hashlib
from typing import Any

from config.settings import settings


def _parse_proxy_entries(raw: str) -> list[str]:
    return [x.strip() for x in str(raw or "").split(",") if x.strip()]


def configured_proxy_pool() -> list[str]:
    return _parse_proxy_entries(getattr(settings, "BROWSER_PROXY_POOL", ""))


def select_proxy_for_service(service: str, *, task_root_id: str = "", attempt: int = 0) -> dict[str, Any] | None:
    pool = configured_proxy_pool()
    if not pool:
        return None
    svc = str(service or "generic").strip().lower() or "generic"
    basis = f"{svc}:{task_root_id}:{int(attempt)}"
    idx = int(hashlib.sha256(basis.encode("utf-8")).hexdigest(), 16) % len(pool)
    server = pool[idx]
    return {
        "server": server,
        "index": idx,
        "service": svc,
        "attempt": int(attempt),
        "pool_size": len(pool),
    }
