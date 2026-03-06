"""Unified publisher queue with retries and evidence-first execution."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from config.settings import settings
from modules.execution_facts import ExecutionFacts
from modules.platform_result_contract import normalize_platform_result, validate_platform_result_contract
from modules.publish_contract import build_publish_signature


@dataclass
class PublishJob:
    id: int
    platform: str
    payload_json: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str
    evidence: str
    trace_id: str
    created_at: str
    updated_at: str


class PublisherQueue:
    """Durable queue for multi-platform publish jobs."""

    def __init__(self, platforms: dict[str, Any], sqlite_path: Optional[str] = None):
        self.platforms = platforms or {}
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.facts = ExecutionFacts(sqlite_path=self.sqlite_path)
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.sqlite_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publish_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                last_error TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                trace_id TEXT DEFAULT '',
                signature TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_jobs_status ON publish_jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_jobs_platform ON publish_jobs(platform)")
        conn.commit()
        conn.close()

    def enqueue(self, platform: str, payload: dict, max_attempts: int = 3, trace_id: str = "") -> int:
        sig = build_publish_signature(platform, payload)
        conn = self._conn()
        # Avoid enqueue duplicates still in active states.
        row = conn.execute(
            """
            SELECT id FROM publish_jobs
            WHERE platform=? AND signature=? AND status IN ('queued','running')
            ORDER BY id DESC LIMIT 1
            """,
            (platform, sig),
        ).fetchone()
        if row:
            job_id = int(row["id"])
            conn.close()
            return job_id
        cur = conn.execute(
            """
            INSERT INTO publish_jobs(platform, payload_json, status, attempts, max_attempts, trace_id, signature, updated_at)
            VALUES (?, ?, 'queued', 0, ?, ?, ?, datetime('now'))
            """,
            (platform, json.dumps(payload, ensure_ascii=False), int(max_attempts), trace_id[:120], sig),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
        conn.close()
        return job_id

    def list_jobs(self, limit: int = 100, status: str = "") -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                """
                SELECT * FROM publish_jobs
                WHERE status=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (status, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM publish_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT status, COUNT(*) n
            FROM publish_jobs
            GROUP BY status
            """
        ).fetchall()
        conn.close()
        out = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        for r in rows:
            out[str(r["status"])] = int(r["n"] or 0)
        out["total"] = sum(out.values())
        return out

    def _next_queued(self) -> Optional[sqlite3.Row]:
        conn = self._conn()
        row = conn.execute(
            """
            SELECT * FROM publish_jobs
            WHERE status='queued'
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        return row

    def _set_status(self, job_id: int, status: str, attempts: int, error: str = "", evidence: str = "") -> None:
        conn = self._conn()
        conn.execute(
            """
            UPDATE publish_jobs
            SET status=?, attempts=?, last_error=?, evidence=?, updated_at=datetime('now')
            WHERE id=?
            """,
            (status, int(attempts), error[:500], evidence[:1000], int(job_id)),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _extract_evidence(result: dict | None) -> str:
        if isinstance(result, dict) and isinstance(result.get("evidence"), dict):
            ev = result.get("evidence") or {}
        else:
            normalized = normalize_platform_result(result or {}, platform=str((result or {}).get("platform", "")))
            ev = normalized.get("evidence") if isinstance(normalized, dict) else {}
        if not isinstance(ev, dict):
            return ""
        for key in ("url", "id", "path", "screenshot"):
            val = str(ev.get(key) or "").strip()
            if val:
                return val
        return ""

    async def process_once(self) -> dict | None:
        row = self._next_queued()
        if not row:
            return None
        job = dict(row)
        job_id = int(job["id"])
        platform = str(job["platform"])
        attempts = int(job.get("attempts") or 0) + 1
        max_attempts = int(job.get("max_attempts") or 3)
        trace_id = str(job.get("trace_id") or "")
        payload = {}
        try:
            payload = json.loads(job.get("payload_json") or "{}")
        except Exception:
            payload = {}

        self._set_status(job_id, "running", attempts, error="", evidence=job.get("evidence", ""))

        pl = self.platforms.get(platform)
        if not pl:
            err = f"platform_not_registered:{platform}"
            final = "failed" if attempts >= max_attempts else "queued"
            self._set_status(job_id, final, attempts, error=err)
            self.facts.record(
                action="platform:publish_job",
                status="failed",
                detail=f"{platform} job_id={job_id} err={err}",
                source="publisher_queue",
                evidence_dict={"platform": platform, "job_id": job_id, "trace_id": trace_id},
            )
            return {"job_id": job_id, "platform": platform, "status": final, "error": err}

        try:
            result = await pl.publish(payload)
            normalized = normalize_platform_result(result or {}, platform=platform, action="publish")
            contract = validate_platform_result_contract(normalized, require_evidence_for_success=True)
            if not contract.ok:
                err = f"platform_contract_invalid:{','.join(contract.errors)}"
                final = "failed" if attempts >= max_attempts else "queued"
                self._set_status(job_id, final, attempts, error=err)
                self.facts.record(
                    action="platform:publish_job",
                    status="failed",
                    detail=f"{platform} job_id={job_id} err={err}",
                    source="publisher_queue",
                    evidence_dict={"platform": platform, "job_id": job_id, "trace_id": trace_id, "result": normalized},
                )
                return {"job_id": job_id, "platform": platform, "status": final, "error": err}

            st = str(normalized.get("status", "")).lower()
            evidence = self._extract_evidence(normalized)
            ok_status = st in {"published", "created", "draft", "prepared", "completed", "success", "draft_saved"}
            evidence_optional = st in {"draft", "prepared", "draft_saved"}
            if ok_status and (evidence or evidence_optional):
                self._set_status(job_id, "done", attempts, evidence=evidence)
                self.facts.record(
                    action="platform:publish_job",
                    status="success",
                    detail=f"{platform} job_id={job_id} st={st}",
                    evidence=evidence,
                    source="publisher_queue",
                    evidence_dict={"platform": platform, "job_id": job_id, "trace_id": trace_id, "result": normalized},
                )
                return {"job_id": job_id, "platform": platform, "status": "done", "result": normalized}
            if ok_status and not evidence and not evidence_optional:
                err = "missing_evidence"
            else:
                err = str(normalized.get("error", f"publish_status:{st}"))
        except Exception as e:
            err = str(e)

        final = "failed" if attempts >= max_attempts else "queued"
        self._set_status(job_id, final, attempts, error=err)
        self.facts.record(
            action="platform:publish_job",
            status="failed",
            detail=f"{platform} job_id={job_id} err={err[:220]}",
            source="publisher_queue",
            evidence_dict={"platform": platform, "job_id": job_id, "trace_id": trace_id},
        )
        return {"job_id": job_id, "platform": platform, "status": final, "error": err}

    async def process_all(self, limit: int = 20) -> list[dict]:
        out: list[dict] = []
        for _ in range(int(limit)):
            item = await self.process_once()
            if not item:
                break
            out.append(item)
        return out
