"""Registry for external tool adapters (MCP/OpenAPI) with validation."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from config.settings import settings


class ToolingRegistry:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tooling_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_key TEXT UNIQUE NOT NULL,
                    protocol TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    auth_type TEXT DEFAULT 'none',
                    enabled INTEGER DEFAULT 1,
                    schema_json TEXT DEFAULT '{}',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_adapter(
        self,
        adapter_key: str,
        protocol: str,
        endpoint: str,
        auth_type: str = "none",
        enabled: bool = True,
        schema: dict | None = None,
        notes: str = "",
    ) -> dict:
        errs = self.validate(protocol=protocol, endpoint=endpoint, schema=schema or {})
        if errs:
            return {"ok": False, "errors": errs}
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO tooling_registry
                (adapter_key, protocol, endpoint, auth_type, enabled, schema_json, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(adapter_key) DO UPDATE SET
                  protocol = excluded.protocol,
                  endpoint = excluded.endpoint,
                  auth_type = excluded.auth_type,
                  enabled = excluded.enabled,
                  schema_json = excluded.schema_json,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (
                    adapter_key[:120],
                    protocol[:20],
                    endpoint[:500],
                    auth_type[:30],
                    1 if enabled else 0,
                    json.dumps(schema or {}, ensure_ascii=False)[:5000],
                    notes[:1000],
                ),
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def list_adapters(self, enabled_only: bool = False, limit: int = 200) -> list[dict]:
        conn = self._get_conn()
        try:
            if enabled_only:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_registry
                    WHERE enabled = 1
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_registry
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["schema"] = json.loads(d.get("schema_json") or "{}")
                except Exception:
                    d["schema"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    def delete_adapter(self, adapter_key: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM tooling_registry WHERE adapter_key = ?", (adapter_key,))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def validate(protocol: str, endpoint: str, schema: dict) -> list[str]:
        errs = []
        pr = (protocol or "").strip().lower()
        if pr not in {"mcp", "openapi"}:
            errs.append("protocol must be mcp|openapi")
        ep = (endpoint or "").strip()
        if not ep:
            errs.append("endpoint is required")
        if ep and not (ep.startswith("http://") or ep.startswith("https://") or ep.startswith("stdio://")):
            errs.append("endpoint must be http(s):// or stdio://")
        if not isinstance(schema, dict):
            errs.append("schema must be object")
        if pr == "openapi":
            if "paths" not in schema and "openapi" not in schema:
                errs.append("openapi schema missing openapi/paths")
        if pr == "mcp":
            if "tools" not in schema and "capabilities" not in schema:
                errs.append("mcp schema missing tools/capabilities")
        return errs
