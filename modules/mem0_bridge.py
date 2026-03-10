"""Optional mem0 bridge layered on top of VITO memory."""

from __future__ import annotations

from typing import Any

from config.logger import get_logger
from config.settings import settings

logger = get_logger("mem0_bridge", agent="mem0_bridge")


class Mem0Bridge:
    def __init__(self, backend: Any | None = None):
        self._backend = backend
        self._enabled = bool(getattr(settings, "MEM0_ENABLED", False))
        self._user_id = str(getattr(settings, "MEM0_USER_ID", "vito_owner") or "vito_owner")
        self._collection = str(getattr(settings, "MEM0_COLLECTION", "vito_runtime") or "vito_runtime")
        if self._backend is None and self._enabled:
            self._backend = self._build_backend()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._backend is not None

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self.enabled or not str(text or "").strip():
            return False
        payload = metadata or {}
        try:
            if hasattr(self._backend, "add"):
                self._backend.add(
                    text,
                    user_id=self._user_id,
                    metadata=payload,
                    collection_name=self._collection,
                )
                return True
            if hasattr(self._backend, "add_memory"):
                self._backend.add_memory(
                    text=text,
                    user_id=self._user_id,
                    metadata=payload,
                    collection_name=self._collection,
                )
                return True
        except Exception as exc:
            logger.warning(f"mem0 add failed: {exc}", extra={"event": "mem0_add_failed"})
        return False

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.enabled or not str(query or "").strip():
            return []
        try:
            if hasattr(self._backend, "search"):
                rows = self._backend.search(
                    query=query,
                    user_id=self._user_id,
                    collection_name=self._collection,
                    limit=int(limit),
                )
            elif hasattr(self._backend, "search_memory"):
                rows = self._backend.search_memory(
                    query=query,
                    user_id=self._user_id,
                    collection_name=self._collection,
                    limit=int(limit),
                )
            else:
                return []
            out: list[dict[str, Any]] = []
            for row in rows or []:
                item = dict(row) if isinstance(row, dict) else {"text": str(row)}
                item.setdefault("source", "mem0")
                out.append(item)
            return out[:limit]
        except Exception as exc:
            logger.warning(f"mem0 search failed: {exc}", extra={"event": "mem0_search_failed"})
            return []

    def _build_backend(self) -> Any | None:
        api_key = str(getattr(settings, "MEM0_API_KEY", "") or "").strip()
        try:
            from mem0 import MemoryClient  # type: ignore
            if api_key:
                return MemoryClient(api_key=api_key)
        except Exception:
            pass
        try:
            from mem0 import Memory  # type: ignore
            return Memory()
        except Exception:
            logger.info("mem0 backend unavailable; bridge disabled", extra={"event": "mem0_unavailable"})
            return None
