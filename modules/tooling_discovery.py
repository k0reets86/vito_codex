"""Autonomous tooling discovery intake: candidate -> review -> promote."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config.settings import settings
from modules.tooling_registry import ToolingRegistry


class ToolingDiscovery:
    """Manages discovered tooling candidates before registry promotion."""

    def __init__(self, sqlite_path: Optional[str] = None, registry: ToolingRegistry | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.registry = registry or ToolingRegistry(sqlite_path=self.sqlite_path)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tooling_discovery_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT DEFAULT '',
                    adapter_key TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    auth_type TEXT DEFAULT 'none',
                    schema_json TEXT DEFAULT '{}',
                    validation_errors_json TEXT DEFAULT '[]',
                    risk_score REAL DEFAULT 0.0,
                    quality_score REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'discovered',
                    notes TEXT DEFAULT '',
                    discovered_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_tooling_discovery_status
                ON tooling_discovery_candidates (status, discovered_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tooling_discovery_adapter
                ON tooling_discovery_candidates (adapter_key, discovered_at DESC);
                CREATE TABLE IF NOT EXISTS tooling_discovery_rollout_state (
                    scope TEXT PRIMARY KEY,
                    cursor INTEGER DEFAULT 0,
                    last_stage TEXT DEFAULT 'canary',
                    last_pool_size INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def discover_candidate(
        self,
        source: str,
        adapter_key: str,
        protocol: str,
        endpoint: str,
        auth_type: str = "none",
        schema: dict | None = None,
        notes: str = "",
    ) -> dict:
        schema = schema or {}
        existing = self._find_recent_candidate(
            adapter_key=adapter_key,
            protocol=protocol,
            endpoint=endpoint,
            dedup_hours=max(1, int(getattr(settings, "TOOLING_DISCOVERY_DEDUP_HOURS", 72) or 72)),
        )
        if existing:
            return {
                "ok": True,
                "candidate_id": int(existing.get("id") or 0),
                "status": str(existing.get("status") or "discovered"),
                "risk_score": round(float(existing.get("risk_score", 0.0) or 0.0), 4),
                "quality_score": round(float(existing.get("quality_score", 0.0) or 0.0), 4),
                "validation_errors": existing.get("validation_errors", []),
                "duplicate": True,
            }
        errs = self.registry.validate(protocol=protocol, endpoint=endpoint, schema=schema)
        errs.extend(self._discovery_policy_errors(protocol=protocol, endpoint=endpoint))
        quality = self._quality_score(protocol=protocol, endpoint=endpoint, schema=schema, validation_errors=errs)
        risk = self._risk_score(auth_type=auth_type, endpoint=endpoint, schema=schema)
        status = "approved" if (not errs and risk < 0.65 and quality >= 0.6) else "review_required"

        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO tooling_discovery_candidates
                (source, adapter_key, protocol, endpoint, auth_type, schema_json, validation_errors_json, risk_score, quality_score, status, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    str(source or "")[:120],
                    str(adapter_key or "")[:120],
                    str(protocol or "")[:20].lower(),
                    str(endpoint or "")[:500],
                    str(auth_type or "none")[:30].lower(),
                    json.dumps(schema, ensure_ascii=False)[:10000],
                    json.dumps(errs, ensure_ascii=False)[:3000],
                    float(risk),
                    float(quality),
                    status,
                    str(notes or "")[:1000],
                ),
            )
            conn.commit()
            cid = int(cur.lastrowid)
        finally:
            conn.close()

        return {
            "ok": True,
            "candidate_id": cid,
            "status": status,
            "risk_score": round(risk, 4),
            "quality_score": round(quality, 4),
            "validation_errors": errs,
        }

    @staticmethod
    def _discovery_policy_errors(protocol: str, endpoint: str) -> list[str]:
        errs: list[str] = []
        pr = str(protocol or "").strip().lower()
        ep = str(endpoint or "").strip()
        if pr != "openapi" or not ep:
            return errs

        low = ep.lower()
        if low.startswith("http://"):
            parsed = urlparse(ep)
            host = str(parsed.hostname or "").strip().lower()
            local_hosts = {"localhost", "127.0.0.1", "::1"}
            if bool(getattr(settings, "TOOLING_DISCOVERY_REQUIRE_HTTPS", True)) and host not in local_hosts:
                errs.append("endpoint_https_required")

        allowed_raw = str(getattr(settings, "TOOLING_DISCOVERY_ALLOWED_DOMAINS", "") or "").strip()
        if not allowed_raw:
            return errs
        parsed = urlparse(ep)
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            errs.append("endpoint_domain_missing")
            return errs
        allowed_domains = [x.strip().lower() for x in allowed_raw.split(",") if x.strip()]
        if not allowed_domains:
            return errs
        if not any(host == d or host.endswith(f".{d}") for d in allowed_domains):
            errs.append("endpoint_domain_not_allowed")
        return errs

    def list_candidates(self, status: str = "", limit: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_discovery_candidates
                    WHERE status = ?
                    ORDER BY discovered_at DESC
                    LIMIT ?
                    """,
                    (status[:40], int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tooling_discovery_candidates
                    ORDER BY discovered_at DESC
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
                try:
                    d["validation_errors"] = json.loads(d.get("validation_errors_json") or "[]")
                except Exception:
                    d["validation_errors"] = []
                out.append(d)
            return out
        finally:
            conn.close()

    def set_status(self, candidate_id: int, status: str, notes: str = "") -> bool:
        status = str(status or "").strip().lower()
        if status not in {"discovered", "review_required", "approved", "rejected", "promoted"}:
            return False
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                UPDATE tooling_discovery_candidates
                SET status = ?, notes = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (status, str(notes or "")[:1000], int(candidate_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
        finally:
            conn.close()

    def approve_candidate(
        self,
        candidate_id: int,
        actor: str = "owner",
        promote_to_registry: bool = False,
    ) -> dict:
        row = self._get_candidate(candidate_id)
        if not row:
            return {"ok": False, "error": "candidate_not_found"}

        if str(row.get("status") or "").lower() == "rejected":
            return {"ok": False, "error": "candidate_rejected"}

        self.set_status(candidate_id, "approved", notes=f"approved_by:{actor}"[:1000])
        if not promote_to_registry:
            return {"ok": True, "status": "approved"}

        schema = row.get("schema") or {}
        up = self.registry.upsert_adapter(
            adapter_key=str(row.get("adapter_key") or ""),
            protocol=str(row.get("protocol") or ""),
            endpoint=str(row.get("endpoint") or ""),
            auth_type=str(row.get("auth_type") or "none"),
            enabled=False,
            schema=schema,
            adapter_stage="staging",
            notes=f"discovered_from:{row.get('source')}; candidate_id:{candidate_id}; actor:{actor}"[:1000],
        )
        if not up.get("ok"):
            return {"ok": False, "error": "registry_upsert_failed", "details": up}

        self.set_status(candidate_id, "promoted", notes=f"promoted_by:{actor}"[:1000])
        return {"ok": True, "status": "promoted", "registry": up}

    def build_summary(self) -> dict:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n, AVG(risk_score) AS avg_risk, AVG(quality_score) AS avg_quality
                FROM tooling_discovery_candidates
                GROUP BY status
                """
            ).fetchall()
        finally:
            conn.close()
        by_status = {}
        total = 0
        for r in rows:
            status = str(r["status"] or "")
            n = int(r["n"] or 0)
            total += n
            by_status[status] = {
                "count": n,
                "avg_risk": round(float(r["avg_risk"] or 0.0), 4),
                "avg_quality": round(float(r["avg_quality"] or 0.0), 4),
            }
        return {"total": total, "by_status": by_status}

    def get_rollout_state(self, scope: str = "default") -> dict:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT scope, cursor, last_stage, last_pool_size, updated_at
                FROM tooling_discovery_rollout_state
                WHERE scope = ?
                LIMIT 1
                """,
                (str(scope or "default")[:80],),
            ).fetchone()
            if not row:
                return {
                    "scope": str(scope or "default"),
                    "cursor": 0,
                    "last_stage": "canary",
                    "last_pool_size": 0,
                    "updated_at": "",
                }
            return dict(row)
        finally:
            conn.close()

    def discover_from_sources(
        self,
        sources: list[dict],
        *,
        max_items: int = 5,
        auto_promote: bool = False,
        rollout_stage: str = "canary",
        canary_percent: int = 34,
        scope: str = "default",
    ) -> dict:
        selected, state = self._next_rollout_batch(
            sources=sources,
            max_items=max_items,
            rollout_stage=rollout_stage,
            canary_percent=canary_percent,
            scope=scope,
        )
        processed = 0
        duplicates = 0
        promoted = 0
        review_required = 0
        policy_blocked = 0
        policy_block_reasons: dict[str, int] = {}
        approved = 0
        failed = 0
        for item in selected:
            out = self.discover_candidate(
                source=str(item.get("source", "scheduled_scan")),
                adapter_key=str(item.get("adapter_key", "")),
                protocol=str(item.get("protocol", "")),
                endpoint=str(item.get("endpoint", "")),
                auth_type=str(item.get("auth_type", "none")),
                schema=item.get("schema", {}) if isinstance(item.get("schema", {}), dict) else {},
                notes=str(item.get("notes", "")),
            )
            processed += 1
            if not out.get("ok"):
                failed += 1
                continue
            if out.get("duplicate"):
                duplicates += 1
                continue
            status = str(out.get("status", "")).strip().lower()
            val_errs = out.get("validation_errors", []) if isinstance(out, dict) else []
            policy_errs = [
                str(e).strip().lower()
                for e in (val_errs or [])
                if str(e).strip().lower().startswith("endpoint_")
            ]
            has_policy_block = bool(policy_errs)
            if has_policy_block:
                policy_blocked += 1
                for err in policy_errs:
                    policy_block_reasons[err] = int(policy_block_reasons.get(err, 0) or 0) + 1
            if status == "review_required":
                review_required += 1
            elif status == "approved":
                approved += 1
            if auto_promote and status == "approved":
                prm = self.approve_candidate(
                    candidate_id=int(out.get("candidate_id", 0) or 0),
                    actor="discovery_rollout",
                    promote_to_registry=True,
                )
                if prm.get("ok") and prm.get("status") == "promoted":
                    promoted += 1
        return {
            "ok": True,
            "processed": processed,
            "duplicates": duplicates,
            "approved": approved,
            "review_required": review_required,
            "policy_blocked": policy_blocked,
            "policy_block_reasons": dict(sorted(policy_block_reasons.items())),
            "promoted": promoted,
            "failed": failed,
            "selected": [str(x.get("adapter_key", "")) for x in selected],
            "rollout_state": state,
        }

    def _find_recent_candidate(
        self,
        adapter_key: str,
        protocol: str,
        endpoint: str,
        dedup_hours: int = 72,
    ) -> dict | None:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM tooling_discovery_candidates
                WHERE adapter_key = ? AND protocol = ? AND endpoint = ?
                ORDER BY updated_at DESC
                LIMIT 3
                """,
                (
                    str(adapter_key or "")[:120],
                    str(protocol or "").strip().lower()[:20],
                    str(endpoint or "")[:500],
                ),
            ).fetchall()
            if not rows:
                return None
            now = datetime.now(timezone.utc)
            horizon = now - timedelta(hours=max(1, int(dedup_hours or 72)))
            for row in rows:
                d = dict(row)
                ts = self._parse_sqlite_dt(str(d.get("updated_at") or ""))
                if ts and ts >= horizon and str(d.get("status") or "").lower() != "rejected":
                    try:
                        d["validation_errors"] = json.loads(d.get("validation_errors_json") or "[]")
                    except Exception:
                        d["validation_errors"] = []
                    return d
            return None
        finally:
            conn.close()

    def _next_rollout_batch(
        self,
        *,
        sources: list[dict],
        max_items: int,
        rollout_stage: str,
        canary_percent: int,
        scope: str,
    ) -> tuple[list[dict], dict]:
        clean_sources = [s for s in (sources or []) if isinstance(s, dict)]
        if not clean_sources:
            return [], self.get_rollout_state(scope)

        stage = str(rollout_stage or "canary").strip().lower()
        if stage not in {"canary", "full"}:
            stage = "canary"
        percent = max(1, min(100, int(canary_percent or 34)))
        if stage == "full":
            pool = clean_sources
        else:
            canary_n = max(1, (len(clean_sources) * percent + 99) // 100)
            pool = clean_sources[:canary_n]

        sc = str(scope or "default")[:80]
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT cursor FROM tooling_discovery_rollout_state WHERE scope = ? LIMIT 1",
                (sc,),
            ).fetchone()
            cursor = int((row["cursor"] if row else 0) or 0)
            selected: list[dict] = []
            size = len(pool)
            if size > 0:
                for idx in range(min(max(1, int(max_items or 1)), size)):
                    selected.append(pool[(cursor + idx) % size])
                new_cursor = (cursor + len(selected)) % size
            else:
                new_cursor = 0
            conn.execute(
                """
                INSERT INTO tooling_discovery_rollout_state (scope, cursor, last_stage, last_pool_size, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(scope) DO UPDATE SET
                  cursor = excluded.cursor,
                  last_stage = excluded.last_stage,
                  last_pool_size = excluded.last_pool_size,
                  updated_at = excluded.updated_at
                """,
                (sc, int(new_cursor), stage, int(size)),
            )
            conn.commit()
            state = {
                "scope": sc,
                "cursor_before": int(cursor),
                "cursor_after": int(new_cursor),
                "rollout_stage": stage,
                "pool_size": int(size),
                "canary_percent": int(percent),
            }
            return selected, state
        finally:
            conn.close()

    def _get_candidate(self, candidate_id: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM tooling_discovery_candidates WHERE id = ?",
                (int(candidate_id),),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["schema"] = json.loads(d.get("schema_json") or "{}")
            except Exception:
                d["schema"] = {}
            return d
        finally:
            conn.close()

    @staticmethod
    def _quality_score(protocol: str, endpoint: str, schema: dict, validation_errors: list[str]) -> float:
        score = 0.0
        pr = str(protocol or "").lower()
        if pr in {"mcp", "openapi"}:
            score += 0.25
        ep = str(endpoint or "")
        if ep.startswith("https://"):
            score += 0.2
        elif ep.startswith("http://") or ep.startswith("stdio://"):
            score += 0.1
        if isinstance(schema, dict) and schema:
            score += 0.25
            if pr == "openapi" and ("openapi" in schema or "paths" in schema):
                score += 0.15
            if pr == "mcp" and ("tools" in schema or "capabilities" in schema):
                score += 0.15
        if validation_errors:
            score -= min(0.5, 0.1 * len(validation_errors))
        return max(0.0, min(1.0, score))

    @staticmethod
    def _risk_score(auth_type: str, endpoint: str, schema: dict) -> float:
        risk = 0.1
        auth = str(auth_type or "none").lower()
        if auth in {"bearer", "oauth2", "api_key"}:
            risk += 0.2
        ep = str(endpoint or "").lower()
        if ep.startswith("http://"):
            risk += 0.15
        if "localhost" in ep or ep.startswith("stdio://"):
            risk -= 0.05
        if isinstance(schema, dict) and schema:
            # Heuristic: mutating operations are riskier than read-only.
            paths = schema.get("paths") if isinstance(schema.get("paths"), dict) else {}
            mutating = 0
            for _, spec in paths.items():
                if not isinstance(spec, dict):
                    continue
                for method in spec.keys():
                    if str(method).lower() in {"post", "put", "patch", "delete"}:
                        mutating += 1
            if mutating > 0:
                risk += min(0.3, 0.05 * mutating)
        return max(0.0, min(1.0, risk))

    def discover_from_config_sources(
        self,
        *,
        max_items: int = 5,
        auto_promote: bool = False,
        rollout_stage: str = "canary",
        canary_percent: int = 34,
        scope: str = "default",
    ) -> dict:
        sources = parse_tooling_discovery_sources(
            str(getattr(settings, "TOOLING_DISCOVERY_SOURCES", "") or "")
        )
        if not sources:
            return {
                "ok": True,
                "processed": 0,
                "duplicates": 0,
                "promoted": 0,
                "approved": 0,
                "review_required": 0,
                "failed": 0,
                "policy_blocked": 0,
                "policy_block_reasons": {},
                "selected": [],
                "rollout_state": self.get_rollout_state(scope),
            }
        return self.discover_from_sources(
            sources=sources,
            max_items=max_items,
            auto_promote=auto_promote,
            rollout_stage=rollout_stage,
            canary_percent=canary_percent,
            scope=scope,
        )

    @staticmethod
    def _parse_sqlite_dt(value: str) -> datetime | None:
        ts = (value or "").strip()
        if not ts:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts[:19], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None


def parse_tooling_discovery_sources(raw: object) -> list[dict]:
    """Normalize discovery source definitions from JSON string/list/dict."""
    payload = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("@"):
            try:
                file_text = Path(text[1:].strip()).expanduser().read_text(encoding="utf-8")
            except Exception:
                return []
            text = file_text.strip()
            if not text:
                return []
        try:
            payload = json.loads(text)
        except Exception:
            # Fallback line format:
            # source|adapter_key|protocol|endpoint|auth_type|notes
            rows: list[dict] = []
            for ln in text.splitlines():
                line = ln.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    continue
                source = parts[0] or "manual"
                adapter_key = parts[1]
                protocol = parts[2].lower()
                endpoint = parts[3]
                auth_type = (parts[4] if len(parts) >= 5 else "none") or "none"
                notes = parts[5] if len(parts) >= 6 else ""
                rows.append(
                    {
                        "source": source,
                        "adapter_key": adapter_key,
                        "protocol": protocol,
                        "endpoint": endpoint,
                        "auth_type": auth_type,
                        "notes": notes,
                    }
                )
            payload = rows
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    out: list[dict] = []
    dedup: set[tuple[str, str, str]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        adapter_key = str(item.get("adapter_key", "")).strip()
        protocol = str(item.get("protocol", "")).strip().lower()
        endpoint = str(item.get("endpoint", "")).strip()
        if not adapter_key or protocol not in {"mcp", "openapi"} or not endpoint:
            continue
        key = (adapter_key.lower(), protocol, endpoint.lower())
        if key in dedup:
            continue
        dedup.add(key)
        out.append(
            {
                "source": str(item.get("source", "manual")).strip()[:120] or "manual",
                "adapter_key": adapter_key[:120],
                "protocol": protocol[:20],
                "endpoint": endpoint[:500],
                "auth_type": str(item.get("auth_type", "none")).strip()[:30] or "none",
                "schema": item.get("schema", {}) if isinstance(item.get("schema", {}), dict) else {},
                "notes": str(item.get("notes", "")).strip()[:1000],
            }
        )
    return out
