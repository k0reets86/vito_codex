"""Centralized auth broker with method priorities, status tracking and TTL."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.paths import root_path


DEFAULT_METHOD_PRIORITY = {
    "oauth_token": 100,
    "api_key": 90,
    "browser_storage": 80,
    "manual_confirmed": 70,
    "cookie_import": 60,
    "unknown": 10,
}


class AuthBroker:
    def __init__(self, state_path: str | None = None):
        raw = str(state_path or root_path("runtime", "auth_broker_state.json"))
        self._path = Path(raw)
        if not self._path.is_absolute():
            self._path = Path(root_path(raw))
        self._state: dict[str, Any] = {"services": {}, "updated_at": ""}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._state = payload
        except Exception:
            self._state = {"services": {}, "updated_at": ""}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _expiry_iso(ttl_sec: int) -> str:
        ttl = max(60, int(ttl_sec or 0))
        return (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        if not str(expires_at or "").strip():
            return True
        try:
            dt = datetime.fromisoformat(str(expires_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > dt
        except Exception:
            return True

    def set_status(
        self,
        service: str,
        status: str,
        method: str = "unknown",
        detail: str = "",
        ttl_sec: int = 3600,
    ) -> None:
        svc = str(service or "").strip().lower()
        if not svc:
            return
        m = str(method or "unknown").strip().lower()
        st = str(status or "unknown").strip().lower()
        node = {
            "service": svc,
            "status": st,
            "method": m,
            "priority": int(DEFAULT_METHOD_PRIORITY.get(m, DEFAULT_METHOD_PRIORITY["unknown"])),
            "detail": str(detail or "")[:500],
            "updated_at": self._now_iso(),
            "expires_at": self._expiry_iso(ttl_sec),
        }
        self._state.setdefault("services", {})[svc] = node
        self._save()

    def mark_authenticated(self, service: str, method: str, detail: str = "", ttl_sec: int = 3600) -> None:
        self.set_status(service=service, status="authenticated", method=method, detail=detail, ttl_sec=ttl_sec)

    def mark_failed(self, service: str, detail: str = "", ttl_sec: int = 300) -> None:
        self.set_status(service=service, status="failed", method="unknown", detail=detail, ttl_sec=ttl_sec)

    def clear(self, service: str) -> None:
        svc = str(service or "").strip().lower()
        if not svc:
            return
        if svc in self._state.get("services", {}):
            self._state["services"].pop(svc, None)
            self._save()

    def get(self, service: str) -> dict[str, Any]:
        svc = str(service or "").strip().lower()
        node = dict(self._state.get("services", {}).get(svc, {}) or {})
        if not node:
            return {"service": svc, "status": "unknown", "is_valid": False, "expired": True}
        expired = self._is_expired(str(node.get("expires_at") or ""))
        node["expired"] = expired
        node["is_valid"] = (str(node.get("status", "")).lower() == "authenticated") and not expired
        return node

    def is_authenticated(self, service: str) -> bool:
        return bool(self.get(service).get("is_valid"))

