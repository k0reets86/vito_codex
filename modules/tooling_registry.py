"""Registry for external tool adapters (MCP/OpenAPI) with validation."""

from __future__ import annotations

import hashlib
import hmac
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
                    adapter_version TEXT DEFAULT '1.0.0',
                    protocol TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    auth_type TEXT DEFAULT 'none',
                    enabled INTEGER DEFAULT 1,
                    schema_json TEXT DEFAULT '{}',
                    contract_hash TEXT DEFAULT '',
                    contract_signature TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(tooling_registry)").fetchall()}
            if "adapter_version" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN adapter_version TEXT DEFAULT '1.0.0'")
            if "contract_hash" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN contract_hash TEXT DEFAULT ''")
            if "contract_signature" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN contract_signature TEXT DEFAULT ''")
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
        adapter_version: str = "1.0.0",
        notes: str = "",
    ) -> dict:
        errs = self.validate(protocol=protocol, endpoint=endpoint, schema=schema or {})
        if errs:
            return {"ok": False, "errors": errs}
        contract_hash = self.compute_contract_hash(
            adapter_key=adapter_key,
            adapter_version=adapter_version,
            protocol=protocol,
            endpoint=endpoint,
            schema=schema or {},
        )
        contract_signature = self.sign_contract_hash(contract_hash)
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO tooling_registry
                (adapter_key, adapter_version, protocol, endpoint, auth_type, enabled, schema_json, contract_hash, contract_signature, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(adapter_key) DO UPDATE SET
                  adapter_version = excluded.adapter_version,
                  protocol = excluded.protocol,
                  endpoint = excluded.endpoint,
                  auth_type = excluded.auth_type,
                  enabled = excluded.enabled,
                  schema_json = excluded.schema_json,
                  contract_hash = excluded.contract_hash,
                  contract_signature = excluded.contract_signature,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (
                    adapter_key[:120],
                    (adapter_version or "1.0.0")[:32],
                    protocol[:20],
                    endpoint[:500],
                    auth_type[:30],
                    1 if enabled else 0,
                    json.dumps(schema or {}, ensure_ascii=False)[:5000],
                    contract_hash,
                    contract_signature,
                    notes[:1000],
                ),
            )
            conn.commit()
            return {"ok": True, "contract_hash": contract_hash, "contract_signature": contract_signature}
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

    def verify_contract(self, adapter_row: dict) -> tuple[bool, str]:
        try:
            expected_hash = self.compute_contract_hash(
                adapter_key=str(adapter_row.get("adapter_key", "")),
                adapter_version=str(adapter_row.get("adapter_version", "1.0.0")),
                protocol=str(adapter_row.get("protocol", "")),
                endpoint=str(adapter_row.get("endpoint", "")),
                schema=adapter_row.get("schema", {}) if isinstance(adapter_row.get("schema"), dict) else {},
            )
            stored_hash = str(adapter_row.get("contract_hash", ""))
            if not stored_hash or stored_hash != expected_hash:
                return False, "contract_hash_mismatch"
            stored_sig = str(adapter_row.get("contract_signature", ""))
            expected_sig = self.sign_contract_hash(stored_hash)
            if not stored_sig or not hmac.compare_digest(stored_sig, expected_sig):
                return False, "contract_signature_mismatch"
            return True, "contract_ok"
        except Exception:
            return False, "contract_verify_error"

    @staticmethod
    def compute_contract_hash(
        adapter_key: str,
        adapter_version: str,
        protocol: str,
        endpoint: str,
        schema: dict,
    ) -> str:
        canonical = json.dumps(
            {
                "adapter_key": adapter_key,
                "adapter_version": adapter_version,
                "protocol": protocol,
                "endpoint": endpoint,
                "schema": schema,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def sign_contract_hash(contract_hash: str) -> str:
        key = (settings.TOOLING_CONTRACT_SECRET or "tooling-contract-local").encode("utf-8")
        msg = (contract_hash or "").encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).hexdigest()

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
