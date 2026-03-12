from __future__ import annotations

from config.settings import settings


def emit_startup_warnings(logger) -> None:
    if not str(getattr(settings, "DATABASE_URL", "") or "").strip():
        logger.warning(
            "DATABASE_URL is empty; pgvector/postgres-backed memory is disabled and SQLite fallback will be used",
            extra={"event": "startup_pgvector_disabled"},
        )
    mem0_key = str(getattr(settings, "MEM0_API_KEY", "") or "").strip()
    mem0_enabled = bool(getattr(settings, "MEM0_ENABLED", False))
    if mem0_key and not mem0_enabled:
        logger.warning(
            "MEM0_API_KEY is configured but MEM0_ENABLED is false; mem0 bridge remains disabled",
            extra={"event": "startup_mem0_disabled_with_key"},
        )
