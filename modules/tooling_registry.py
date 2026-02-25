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
                    adapter_stage TEXT DEFAULT 'accepted',
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
                CREATE TABLE IF NOT EXISTS tooling_release_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_key TEXT NOT NULL,
                    adapter_version TEXT DEFAULT '1.0.0',
                    from_stage TEXT DEFAULT '',
                    to_stage TEXT DEFAULT '',
                    actor TEXT DEFAULT 'system',
                    reason TEXT DEFAULT '',
                    snapshot_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS tooling_contract_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_key TEXT NOT NULL,
                    proposed_version TEXT NOT NULL,
                    proposed_contract_hash TEXT NOT NULL,
                    proposed_contract_signature TEXT NOT NULL,
                    payload_json TEXT DEFAULT '{}',
                    requested_by TEXT DEFAULT 'system',
                    status TEXT DEFAULT 'pending',
                    decision_reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    decided_at TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tooling_contract_approvals_status
                ON tooling_contract_approvals (status, created_at DESC);
                """
            )
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(tooling_registry)").fetchall()}
            if "adapter_version" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN adapter_version TEXT DEFAULT '1.0.0'")
            if "adapter_stage" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN adapter_stage TEXT DEFAULT 'accepted'")
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
        adapter_stage: str = "accepted",
        notes: str = "",
    ) -> dict:
        errs = self.validate(protocol=protocol, endpoint=endpoint, schema=schema or {})
        if errs:
            return {"ok": False, "errors": errs}
        stage = self._normalize_stage(adapter_stage)
        if not stage:
            return {"ok": False, "errors": ["adapter_stage_invalid"]}
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
                (adapter_key, adapter_version, adapter_stage, protocol, endpoint, auth_type, enabled, schema_json, contract_hash, contract_signature, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(adapter_key) DO UPDATE SET
                  adapter_version = excluded.adapter_version,
                  adapter_stage = excluded.adapter_stage,
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
                    stage,
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

    def request_contract_rotation(
        self,
        adapter_key: str,
        protocol: str,
        endpoint: str,
        schema: dict | None = None,
        adapter_version: str = "1.0.0",
        auth_type: str = "none",
        enabled: bool = True,
        notes: str = "",
        requested_by: str = "system",
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
        payload = {
            "adapter_key": adapter_key,
            "adapter_version": adapter_version,
            "adapter_stage": "staging",
            "protocol": protocol,
            "endpoint": endpoint,
            "auth_type": auth_type,
            "enabled": bool(enabled),
            "schema": schema or {},
            "notes": notes,
        }
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO tooling_contract_approvals
                (adapter_key, proposed_version, proposed_contract_hash, proposed_contract_signature, payload_json, requested_by, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    adapter_key[:120],
                    (adapter_version or "1.0.0")[:32],
                    contract_hash,
                    contract_signature,
                    json.dumps(payload, ensure_ascii=False)[:20000],
                    requested_by[:120],
                ),
            )
            conn.commit()
            return {"ok": True, "approval_id": int(cur.lastrowid), "contract_hash": contract_hash}
        finally:
            conn.close()

    def list_contract_approvals(self, status: str = "pending", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_contract_approvals
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_contract_approvals
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.get("payload_json") or "{}")
                except Exception:
                    d["payload"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    def approve_contract_rotation(self, approval_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM tooling_contract_approvals WHERE id = ? AND status = 'pending'",
                (int(approval_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "approval_not_found"}
            payload = json.loads(row["payload_json"] or "{}")
            # Apply approved adapter config
            applied = self.upsert_adapter(
                adapter_key=str(payload.get("adapter_key", "")).strip(),
                adapter_version=str(payload.get("adapter_version", "1.0.0")).strip() or "1.0.0",
                adapter_stage=str(payload.get("adapter_stage", "staging")).strip() or "staging",
                protocol=str(payload.get("protocol", "")).strip().lower(),
                endpoint=str(payload.get("endpoint", "")).strip(),
                auth_type=str(payload.get("auth_type", "none")).strip(),
                enabled=bool(payload.get("enabled", True)),
                schema=payload.get("schema", {}) if isinstance(payload.get("schema", {}), dict) else {},
                notes=str(payload.get("notes", "")),
            )
            if not applied.get("ok"):
                return {"ok": False, "error": "apply_failed", "details": applied.get("errors", [])}
            conn.execute(
                """
                UPDATE tooling_contract_approvals
                SET status = 'approved',
                    decision_reason = ?,
                    decided_at = datetime('now')
                WHERE id = ?
                """,
                (f"approved_by:{approver}; {reason}"[:500], int(approval_id)),
            )
            # Snapshot release history event: pending -> staging applied
            conn.execute(
                """
                INSERT INTO tooling_release_history
                (adapter_key, adapter_version, from_stage, to_stage, actor, reason, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("adapter_key", ""))[:120],
                    str(payload.get("adapter_version", "1.0.0"))[:32],
                    "pending",
                    str(payload.get("adapter_stage", "staging"))[:32],
                    str(approver)[:120],
                    ("approval_apply " + str(reason or ""))[:500],
                    json.dumps(payload, ensure_ascii=False)[:20000],
                ),
            )
            conn.commit()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"approve_failed:{e}"}
        finally:
            conn.close()

    def reject_contract_rotation(self, approval_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE tooling_contract_approvals
                SET status = 'rejected',
                    decision_reason = ?,
                    decided_at = datetime('now')
                WHERE id = ? AND status = 'pending'
                """,
                (f"rejected_by:{approver}; {reason}"[:500], int(approval_id)),
            )
            conn.commit()
            if int(cur.rowcount or 0) <= 0:
                return {"ok": False, "error": "approval_not_found"}
            return {"ok": True}
        finally:
            conn.close()

    def has_pending_rotation(self, adapter_key: str) -> bool:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT 1
                FROM tooling_contract_approvals
                WHERE adapter_key = ? AND status = 'pending'
                LIMIT 1
                """,
                (adapter_key,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def promote_adapter(self, adapter_key: str, to_stage: str, actor: str = "owner", reason: str = "") -> dict:
        stage = self._normalize_stage(to_stage)
        if not stage:
            return {"ok": False, "error": "stage_invalid"}
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM tooling_registry WHERE adapter_key = ?", (adapter_key,)).fetchone()
            if not row:
                return {"ok": False, "error": "adapter_not_found"}
            cur_stage = str(row["adapter_stage"] or "accepted")
            if cur_stage == stage:
                return {"ok": True, "noop": True}
            if not self._valid_transition(cur_stage, stage):
                return {"ok": False, "error": f"invalid_transition:{cur_stage}->{stage}"}
            snap = dict(row)
            conn.execute(
                "UPDATE tooling_registry SET adapter_stage = ?, updated_at = datetime('now') WHERE adapter_key = ?",
                (stage, adapter_key),
            )
            conn.execute(
                """
                INSERT INTO tooling_release_history
                (adapter_key, adapter_version, from_stage, to_stage, actor, reason, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adapter_key[:120],
                    str(row["adapter_version"] or "1.0.0")[:32],
                    cur_stage[:32],
                    stage[:32],
                    actor[:120],
                    reason[:500],
                    json.dumps(snap, ensure_ascii=False)[:20000],
                ),
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def rollback_adapter(self, adapter_key: str, actor: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT from_stage, to_stage
                FROM tooling_release_history
                WHERE adapter_key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (adapter_key,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "no_release_history"}
            target_stage = str(row["from_stage"] or "").strip()
            if not target_stage:
                return {"ok": False, "error": "rollback_target_missing"}
            return self.promote_adapter(adapter_key=adapter_key, to_stage=target_stage, actor=actor, reason=f"rollback:{reason}"[:500])
        finally:
            conn.close()

    def list_release_history(self, adapter_key: str = "", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if adapter_key:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_release_history
                    WHERE adapter_key = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (adapter_key, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_release_history
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["snapshot"] = json.loads(d.get("snapshot_json") or "{}")
                except Exception:
                    d["snapshot"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        s = str(stage or "").strip().lower()
        return s if s in {"staging", "accepted", "production", "retired"} else ""

    @staticmethod
    def _valid_transition(from_stage: str, to_stage: str) -> bool:
        graph = {
            "staging": {"accepted", "retired"},
            "accepted": {"production", "retired"},
            "production": {"accepted", "retired"},
            "retired": set(),
        }
        if from_stage == to_stage:
            return True
        return to_stage in graph.get(from_stage, set())

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
