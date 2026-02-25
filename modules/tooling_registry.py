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
                    contract_key_id TEXT DEFAULT '',
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
                    bundle_hash TEXT DEFAULT '',
                    bundle_signature TEXT DEFAULT '',
                    release_key_id TEXT DEFAULT '',
                    snapshot_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS tooling_signature_policy (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    contract_active_key_id TEXT DEFAULT '',
                    release_active_key_id TEXT DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS tooling_key_rotation_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_type TEXT NOT NULL,
                    requested_key_id TEXT NOT NULL,
                    requested_by TEXT DEFAULT 'system',
                    reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    decision_reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    decided_at TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tooling_key_rotation_status
                ON tooling_key_rotation_requests (status, created_at DESC);
                CREATE TABLE IF NOT EXISTS tooling_stage_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_stage TEXT DEFAULT '',
                    requested_by TEXT DEFAULT 'system',
                    reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    decision_reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    decided_at TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tooling_stage_approvals_status
                ON tooling_stage_approvals (status, created_at DESC);
                CREATE TABLE IF NOT EXISTS tooling_contract_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_key TEXT NOT NULL,
                    proposed_version TEXT NOT NULL,
                    proposed_contract_hash TEXT NOT NULL,
                    proposed_contract_signature TEXT NOT NULL,
                    proposed_contract_key_id TEXT DEFAULT '',
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
            if "contract_key_id" not in cols:
                conn.execute("ALTER TABLE tooling_registry ADD COLUMN contract_key_id TEXT DEFAULT ''")
            rel_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tooling_release_history)").fetchall()}
            if "bundle_hash" not in rel_cols:
                conn.execute("ALTER TABLE tooling_release_history ADD COLUMN bundle_hash TEXT DEFAULT ''")
            if "bundle_signature" not in rel_cols:
                conn.execute("ALTER TABLE tooling_release_history ADD COLUMN bundle_signature TEXT DEFAULT ''")
            if "release_key_id" not in rel_cols:
                conn.execute("ALTER TABLE tooling_release_history ADD COLUMN release_key_id TEXT DEFAULT ''")
            appr_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tooling_contract_approvals)").fetchall()}
            if "proposed_contract_key_id" not in appr_cols:
                conn.execute("ALTER TABLE tooling_contract_approvals ADD COLUMN proposed_contract_key_id TEXT DEFAULT ''")
            self._ensure_signature_policy(conn)
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
        contract_signature, contract_key_id = self.sign_contract_hash(contract_hash)
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO tooling_registry
                (adapter_key, adapter_version, adapter_stage, protocol, endpoint, auth_type, enabled, schema_json, contract_hash, contract_signature, contract_key_id, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                  contract_key_id = excluded.contract_key_id,
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
                    contract_key_id,
                    notes[:1000],
                ),
            )
            conn.commit()
            return {
                "ok": True,
                "contract_hash": contract_hash,
                "contract_signature": contract_signature,
                "contract_key_id": contract_key_id,
            }
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
        contract_signature, contract_key_id = self.sign_contract_hash(contract_hash)
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
                (adapter_key, proposed_version, proposed_contract_hash, proposed_contract_signature, proposed_contract_key_id, payload_json, requested_by, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    adapter_key[:120],
                    (adapter_version or "1.0.0")[:32],
                    contract_hash,
                    contract_signature,
                    contract_key_id,
                    json.dumps(payload, ensure_ascii=False)[:20000],
                    requested_by[:120],
                ),
            )
            conn.commit()
            return {
                "ok": True,
                "approval_id": int(cur.lastrowid),
                "contract_hash": contract_hash,
                "contract_key_id": contract_key_id,
            }
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
            ok_sig, sig_reason = self.verify_contract_signature(
                contract_hash=str(row["proposed_contract_hash"] or ""),
                contract_signature=str(row["proposed_contract_signature"] or ""),
                contract_key_id=str(row["proposed_contract_key_id"] or ""),
            )
            if not ok_sig:
                return {"ok": False, "error": sig_reason}
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
        return self._promote_adapter(adapter_key=adapter_key, to_stage=to_stage, actor=actor, reason=reason, require_policy=True)

    def _promote_adapter(
        self,
        adapter_key: str,
        to_stage: str,
        actor: str = "owner",
        reason: str = "",
        require_policy: bool = True,
    ) -> dict:
        stage = self._normalize_stage(to_stage)
        if not stage:
            return {"ok": False, "error": "stage_invalid"}
        if require_policy and stage == "production" and bool(getattr(settings, "TOOLING_REQUIRE_PRODUCTION_APPROVAL", True)):
            if not self._has_approved_stage_request(adapter_key, action="promote", target_stage=stage):
                return {"ok": False, "error": "production_approval_required"}
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
            bundle = self._build_release_bundle(snapshot=snap, from_stage=cur_stage, to_stage=stage, actor=actor, reason=reason)
            bundle_hash = self._hash_release_bundle(bundle)
            bundle_sig, release_key_id = self._sign_release_bundle(bundle_hash)
            conn.execute(
                "UPDATE tooling_registry SET adapter_stage = ?, updated_at = datetime('now') WHERE adapter_key = ?",
                (stage, adapter_key),
            )
            conn.execute(
                """
                INSERT INTO tooling_release_history
                (adapter_key, adapter_version, from_stage, to_stage, actor, reason, bundle_hash, bundle_signature, release_key_id, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adapter_key[:120],
                    str(row["adapter_version"] or "1.0.0")[:32],
                    cur_stage[:32],
                    stage[:32],
                    actor[:120],
                    reason[:500],
                    bundle_hash,
                    bundle_sig,
                    release_key_id,
                    json.dumps(snap, ensure_ascii=False)[:20000],
                ),
            )
            if require_policy and stage == "production":
                self._consume_approved_stage_request(conn, adapter_key, action="promote", target_stage="production")
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def rollback_adapter(self, adapter_key: str, actor: str = "owner", reason: str = "") -> dict:
        if bool(getattr(settings, "TOOLING_REQUIRE_ROLLBACK_APPROVAL", True)):
            if not self._has_approved_stage_request(adapter_key, action="rollback", target_stage=""):
                return {"ok": False, "error": "rollback_approval_required"}
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
            return self._promote_adapter(
                adapter_key=adapter_key,
                to_stage=target_stage,
                actor=actor,
                reason=f"rollback:{reason}"[:500],
                require_policy=False,
            )
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

    def verify_release_bundle(self, row: dict) -> tuple[bool, str]:
        try:
            required = {"adapter_key", "adapter_version", "from_stage", "to_stage", "actor", "reason"}
            payload = {k: row.get(k, "") for k in required}
            bundle_hash = self._hash_release_bundle(payload)
            stored_hash = str(row.get("bundle_hash", "") or "")
            if not stored_hash or stored_hash != bundle_hash:
                return False, "bundle_hash_mismatch"
            ok_sig, sig_reason = self.verify_release_signature(
                bundle_hash=stored_hash,
                bundle_signature=str(row.get("bundle_signature", "") or ""),
                release_key_id=str(row.get("release_key_id", "") or ""),
            )
            if not ok_sig:
                return False, sig_reason
            stored_sig = str(row.get("bundle_signature", "") or "")
            if not stored_sig:
                return False, "bundle_signature_mismatch"
            return True, "bundle_ok"
        except Exception:
            return False, "bundle_verify_error"

    def request_stage_change(
        self,
        adapter_key: str,
        action: str,
        target_stage: str = "",
        requested_by: str = "system",
        reason: str = "",
    ) -> dict:
        act = str(action or "").strip().lower()
        if act not in {"promote", "rollback"}:
            return {"ok": False, "error": "action_invalid"}
        tgt = self._normalize_stage(target_stage) if target_stage else ""
        if act == "promote" and not tgt:
            return {"ok": False, "error": "target_stage_invalid"}
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO tooling_stage_approvals
                (adapter_key, action, target_stage, requested_by, reason, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (adapter_key[:120], act, tgt[:32], requested_by[:120], reason[:500]),
            )
            conn.commit()
            return {"ok": True, "approval_id": int(cur.lastrowid)}
        finally:
            conn.close()

    def list_stage_approvals(self, status: str = "pending", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_stage_approvals
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_stage_approvals
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def approve_stage_change(self, approval_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM tooling_stage_approvals WHERE id = ? AND status = 'pending'",
                (int(approval_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "approval_not_found"}
            action = str(row["action"] or "")
            adapter_key = str(row["adapter_key"] or "")
            target_stage = str(row["target_stage"] or "")
            if action == "promote":
                out = self._promote_adapter(
                    adapter_key=adapter_key,
                    to_stage=target_stage,
                    actor=approver,
                    reason=f"approved:{reason}"[:500],
                    require_policy=False,
                )
            else:
                out = self._promote_adapter(
                    adapter_key=adapter_key,
                    to_stage=self._rollback_target(adapter_key),
                    actor=approver,
                    reason=f"approved_rollback:{reason}"[:500],
                    require_policy=False,
                )
            if not out.get("ok"):
                return out
            conn.execute(
                """
                UPDATE tooling_stage_approvals
                SET status = 'approved', decision_reason = ?, decided_at = datetime('now')
                WHERE id = ?
                """,
                (f"approved_by:{approver}; {reason}"[:500], int(approval_id)),
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def reject_stage_change(self, approval_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE tooling_stage_approvals
                SET status = 'rejected', decision_reason = ?, decided_at = datetime('now')
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

    def _rollback_target(self, adapter_key: str) -> str:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT from_stage
                FROM tooling_release_history
                WHERE adapter_key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (adapter_key,),
            ).fetchone()
            return str((row["from_stage"] if row else "") or "")
        finally:
            conn.close()

    def _has_approved_stage_request(self, adapter_key: str, action: str, target_stage: str = "") -> bool:
        conn = self._get_conn()
        try:
            if target_stage:
                row = conn.execute(
                    """
                    SELECT 1 FROM tooling_stage_approvals
                    WHERE adapter_key = ? AND action = ? AND target_stage = ? AND status = 'approved'
                    LIMIT 1
                    """,
                    (adapter_key, action, target_stage),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 1 FROM tooling_stage_approvals
                    WHERE adapter_key = ? AND action = ? AND status = 'approved'
                    LIMIT 1
                    """,
                    (adapter_key, action),
                ).fetchone()
            return row is not None
        finally:
            conn.close()

    @staticmethod
    def _consume_approved_stage_request(conn: sqlite3.Connection, adapter_key: str, action: str, target_stage: str = "") -> None:
        if target_stage:
            conn.execute(
                """
                UPDATE tooling_stage_approvals
                SET status = 'applied', decided_at = CASE WHEN decided_at='' THEN datetime('now') ELSE decided_at END
                WHERE id = (
                  SELECT id FROM tooling_stage_approvals
                  WHERE adapter_key = ? AND action = ? AND target_stage = ? AND status = 'approved'
                  ORDER BY id DESC LIMIT 1
                )
                """,
                (adapter_key, action, target_stage),
            )
        else:
            conn.execute(
                """
                UPDATE tooling_stage_approvals
                SET status = 'applied', decided_at = CASE WHEN decided_at='' THEN datetime('now') ELSE decided_at END
                WHERE id = (
                  SELECT id FROM tooling_stage_approvals
                  WHERE adapter_key = ? AND action = ? AND status = 'approved'
                  ORDER BY id DESC LIMIT 1
                )
                """,
                (adapter_key, action),
            )

    @staticmethod
    def _build_release_bundle(snapshot: dict, from_stage: str, to_stage: str, actor: str, reason: str) -> dict:
        return {
            "adapter_key": snapshot.get("adapter_key", ""),
            "adapter_version": snapshot.get("adapter_version", "1.0.0"),
            "from_stage": from_stage,
            "to_stage": to_stage,
            "actor": actor,
            "reason": reason,
        }

    @staticmethod
    def _hash_release_bundle(bundle: dict) -> str:
        canonical = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _sign_release_bundle(self, bundle_hash: str, release_key_id: str = "") -> tuple[str, str]:
        key_id, secret = self._resolve_signing_secret(
            key_type="release",
            requested_key_id=release_key_id,
        )
        sig = hmac.new(secret.encode("utf-8"), (bundle_hash or "").encode("utf-8"), hashlib.sha256).hexdigest()
        return sig, key_id

    def verify_release_signature(self, bundle_hash: str, bundle_signature: str, release_key_id: str = "") -> tuple[bool, str]:
        if not bundle_signature:
            return False, "bundle_signature_missing"
        key_id, secret = self._resolve_signing_secret(
            key_type="release",
            requested_key_id=release_key_id,
        )
        expected = hmac.new(secret.encode("utf-8"), (bundle_hash or "").encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, bundle_signature):
            return True, f"bundle_signature_ok:{key_id}"
        return False, "bundle_signature_mismatch"

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
            ok_sig, reason = self.verify_contract_signature(
                contract_hash=stored_hash,
                contract_signature=str(adapter_row.get("contract_signature", "") or ""),
                contract_key_id=str(adapter_row.get("contract_key_id", "") or ""),
            )
            if not ok_sig:
                return False, reason
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

    def sign_contract_hash(self, contract_hash: str, contract_key_id: str = "") -> tuple[str, str]:
        key_id, secret = self._resolve_signing_secret(
            key_type="contract",
            requested_key_id=contract_key_id,
        )
        sig = hmac.new(secret.encode("utf-8"), (contract_hash or "").encode("utf-8"), hashlib.sha256).hexdigest()
        return sig, key_id

    def verify_contract_signature(self, contract_hash: str, contract_signature: str, contract_key_id: str = "") -> tuple[bool, str]:
        if not contract_signature:
            return False, "contract_signature_missing"
        key_id, secret = self._resolve_signing_secret(
            key_type="contract",
            requested_key_id=contract_key_id,
        )
        expected = hmac.new(secret.encode("utf-8"), (contract_hash or "").encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, contract_signature):
            return True, f"contract_signature_ok:{key_id}"
        return False, "contract_signature_mismatch"

    def get_signature_policy(self) -> dict:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT contract_active_key_id, release_active_key_id, updated_at FROM tooling_signature_policy WHERE id = 1"
            ).fetchone()
            if not row:
                return {"contract_active_key_id": "", "release_active_key_id": "", "updated_at": ""}
            return dict(row)
        finally:
            conn.close()

    def request_signature_key_rotation(
        self,
        key_type: str,
        requested_key_id: str,
        requested_by: str = "system",
        reason: str = "",
    ) -> dict:
        ktype = self._normalize_key_type(key_type)
        if not ktype:
            return {"ok": False, "error": "key_type_invalid"}
        key_id = str(requested_key_id or "").strip()
        if not key_id:
            return {"ok": False, "error": "key_id_required"}
        if key_id not in self._keyring(ktype):
            return {"ok": False, "error": "key_id_not_available"}
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO tooling_key_rotation_requests
                (key_type, requested_key_id, requested_by, reason, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (ktype, key_id[:120], requested_by[:120], reason[:500]),
            )
            conn.commit()
            return {"ok": True, "rotation_id": int(cur.lastrowid)}
        finally:
            conn.close()

    def list_signature_key_rotations(self, status: str = "pending", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_key_rotation_requests
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_key_rotation_requests
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def approve_signature_key_rotation(self, rotation_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM tooling_key_rotation_requests WHERE id = ? AND status = 'pending'",
                (int(rotation_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "rotation_not_found"}
            key_type = self._normalize_key_type(str(row["key_type"] or ""))
            key_id = str(row["requested_key_id"] or "")
            if not key_type:
                return {"ok": False, "error": "key_type_invalid"}
            if key_id not in self._keyring(key_type):
                return {"ok": False, "error": "key_id_not_available"}
            policy = self._ensure_signature_policy(conn)
            col = "contract_active_key_id" if key_type == "contract" else "release_active_key_id"
            if str(policy.get(col) or "") != key_id:
                conn.execute(
                    f"UPDATE tooling_signature_policy SET {col} = ?, updated_at = datetime('now') WHERE id = 1",
                    (key_id,),
                )
            conn.execute(
                """
                UPDATE tooling_key_rotation_requests
                SET status = 'approved', decision_reason = ?, decided_at = datetime('now')
                WHERE id = ?
                """,
                (f"approved_by:{approver}; {reason}"[:500], int(rotation_id)),
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def reject_signature_key_rotation(self, rotation_id: int, approver: str = "owner", reason: str = "") -> dict:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE tooling_key_rotation_requests
                SET status = 'rejected', decision_reason = ?, decided_at = datetime('now')
                WHERE id = ? AND status = 'pending'
                """,
                (f"rejected_by:{approver}; {reason}"[:500], int(rotation_id)),
            )
            conn.commit()
            if int(cur.rowcount or 0) <= 0:
                return {"ok": False, "error": "rotation_not_found"}
            return {"ok": True}
        finally:
            conn.close()

    def build_governance_report(self, days: int = 7) -> dict:
        window_days = max(1, int(days or 7))
        adapters = self.list_adapters(limit=500)
        approvals_pending = self.list_contract_approvals(status="pending", limit=500)
        stage_pending = self.list_stage_approvals(status="pending", limit=500)
        key_pending = self.list_signature_key_rotations(status="pending", limit=500)
        history = self.list_release_history(limit=500)
        policy = self.get_signature_policy()
        contract_ok = 0
        contract_bad = 0
        for row in adapters:
            ok, _ = self.verify_contract(row)
            if ok:
                contract_ok += 1
            else:
                contract_bad += 1
        release_ok = 0
        release_bad = 0
        for row in history:
            ok, _ = self.verify_release_bundle(row)
            if ok:
                release_ok += 1
            else:
                release_bad += 1
        stage_counts: dict[str, int] = {}
        for row in adapters:
            st = str(row.get("adapter_stage", "unknown") or "unknown")
            stage_counts[st] = int(stage_counts.get(st, 0) or 0) + 1
        conn = self._get_conn()
        try:
            recent_events = conn.execute(
                """
                SELECT COUNT(*) AS n FROM tooling_release_history
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{window_days} day",),
            ).fetchone()
            recent_rot = conn.execute(
                """
                SELECT COUNT(*) AS n FROM tooling_key_rotation_requests
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{window_days} day",),
            ).fetchone()
            recent_event_count = int((recent_events["n"] if recent_events else 0) or 0)
            recent_rotation_count = int((recent_rot["n"] if recent_rot else 0) or 0)
        finally:
            conn.close()
        keyring_contract = sorted(self._keyring("contract").keys())
        keyring_release = sorted(self._keyring("release").keys())
        remediations: list[str] = []
        if contract_bad > 0:
            remediations.append("Fix contract signature/hash mismatches before live runs.")
        if release_bad > 0:
            remediations.append("Investigate release bundle signature mismatches in history.")
        if approvals_pending:
            remediations.append("Review pending contract rotations to avoid stale tooling updates.")
        if stage_pending:
            remediations.append("Process pending stage approvals to unblock promotion flow.")
        if key_pending:
            remediations.append("Process pending key rotations and confirm active key IDs.")
        if policy.get("contract_active_key_id") not in keyring_contract:
            remediations.append("Set a valid active contract signing key ID.")
        if policy.get("release_active_key_id") not in keyring_release:
            remediations.append("Set a valid active release signing key ID.")
        return {
            "window_days": window_days,
            "adapters_total": len(adapters),
            "enabled_total": sum(1 for a in adapters if bool(a.get("enabled"))),
            "stage_counts": stage_counts,
            "pending_contract_rotations": len(approvals_pending),
            "pending_stage_changes": len(stage_pending),
            "pending_key_rotations": len(key_pending),
            "contract_integrity": {"ok": contract_ok, "failed": contract_bad},
            "release_integrity": {"ok": release_ok, "failed": release_bad},
            "recent_release_events": recent_event_count,
            "recent_key_rotations": recent_rotation_count,
            "active_keys": {
                "contract": str(policy.get("contract_active_key_id", "") or ""),
                "release": str(policy.get("release_active_key_id", "") or ""),
            },
            "available_keys": {
                "contract": keyring_contract,
                "release": keyring_release,
            },
            "remediations": remediations,
        }

    def _ensure_signature_policy(self, conn: sqlite3.Connection) -> dict:
        row = conn.execute(
            "SELECT contract_active_key_id, release_active_key_id, updated_at FROM tooling_signature_policy WHERE id = 1"
        ).fetchone()
        contract_default = self._default_key_id("contract")
        release_default = self._default_key_id("release")
        if row is None:
            conn.execute(
                """
                INSERT INTO tooling_signature_policy (id, contract_active_key_id, release_active_key_id, updated_at)
                VALUES (1, ?, ?, datetime('now'))
                """,
                (contract_default, release_default),
            )
            return {"contract_active_key_id": contract_default, "release_active_key_id": release_default, "updated_at": ""}
        contract_active = str(row["contract_active_key_id"] or "")
        release_active = str(row["release_active_key_id"] or "")
        changed = False
        if not contract_active:
            contract_active = contract_default
            changed = True
        if not release_active:
            release_active = release_default
            changed = True
        if changed:
            conn.execute(
                """
                UPDATE tooling_signature_policy
                SET contract_active_key_id = ?, release_active_key_id = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (contract_active, release_active),
            )
        return {
            "contract_active_key_id": contract_active,
            "release_active_key_id": release_active,
            "updated_at": str(row["updated_at"] or ""),
        }

    def _resolve_signing_secret(self, key_type: str, requested_key_id: str = "") -> tuple[str, str]:
        ktype = self._normalize_key_type(key_type)
        if not ktype:
            raise ValueError("key_type_invalid")
        keyring = self._keyring(ktype)
        key_id = (requested_key_id or "").strip()
        if not key_id:
            conn = self._get_conn()
            try:
                policy = self._ensure_signature_policy(conn)
                key_id = str(policy.get("contract_active_key_id" if ktype == "contract" else "release_active_key_id", "") or "")
            finally:
                conn.close()
        if key_id and key_id in keyring:
            return key_id, keyring[key_id]
        default_id = self._default_key_id(ktype)
        return default_id, keyring[default_id]

    def _default_key_id(self, key_type: str) -> str:
        keyring = self._keyring(key_type)
        configured = ""
        if key_type == "contract":
            configured = str(getattr(settings, "TOOLING_CONTRACT_ACTIVE_KEY_ID", "") or "").strip()
        if key_type == "release":
            configured = str(getattr(settings, "TOOLING_RELEASE_ACTIVE_KEY_ID", "") or "").strip()
        if configured and configured in keyring:
            return configured
        for key_id in keyring:
            return key_id
        return "legacy"

    def _keyring(self, key_type: str) -> dict[str, str]:
        ktype = self._normalize_key_type(key_type)
        if ktype == "contract":
            raw = str(getattr(settings, "TOOLING_CONTRACT_KEYS", "") or "")
            fallback = str(getattr(settings, "TOOLING_CONTRACT_SECRET", "tooling-contract-local") or "tooling-contract-local")
        else:
            raw = str(getattr(settings, "TOOLING_RELEASE_KEYS", "") or "")
            fallback = str(getattr(settings, "TOOLING_RELEASE_SECRET", "tooling-release-local") or "tooling-release-local")
        out: dict[str, str] = {}
        for chunk in raw.split(","):
            part = chunk.strip()
            if not part:
                continue
            if ":" in part:
                key_id, secret = part.split(":", 1)
                key_id = key_id.strip()
                secret = secret.strip()
                if key_id and secret:
                    out[key_id] = secret
        if not out:
            out["legacy"] = fallback
        elif "legacy" not in out:
            out["legacy"] = fallback
        return out

    @staticmethod
    def _normalize_key_type(key_type: str) -> str:
        ktype = str(key_type or "").strip().lower()
        if ktype not in {"contract", "release"}:
            return ""
        return ktype

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
