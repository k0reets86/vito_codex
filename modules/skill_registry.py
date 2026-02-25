"""SkillRegistry — local registry for VITO skills."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from config.logger import get_logger
from config.settings import settings
from modules.skill_security import scan_text

logger = get_logger("skill_registry", agent="skill_registry")


class SkillRegistry:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_registry (
                    name TEXT PRIMARY KEY,
                    category TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    status TEXT DEFAULT 'learned',
                    security_status TEXT DEFAULT 'unknown',
                    notes TEXT DEFAULT '',
                    version INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_used TEXT DEFAULT ''
                )
                """
            )
            # Forward-compatible columns for quality/risk audits
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_registry)").fetchall()}
            if "compatibility" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN compatibility TEXT DEFAULT 'unknown'")
            if "tests_coverage" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN tests_coverage REAL DEFAULT 0")
            if "risk_score" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN risk_score REAL DEFAULT 0")
            if "last_audit" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN last_audit TEXT DEFAULT ''")
            if "acceptance_status" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN acceptance_status TEXT DEFAULT 'accepted'")
            if "acceptance_evidence" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN acceptance_evidence TEXT DEFAULT ''")
            if "accepted_at" not in cols:
                conn.execute("ALTER TABLE skill_registry ADD COLUMN accepted_at TEXT DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_acceptance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tests_passed INTEGER DEFAULT 0,
                    validator TEXT DEFAULT '',
                    evidence TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_remediation_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(skill_name, reason, action, status)
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SkillRegistry init failed: {e}", extra={"event": "db_init_error"})

    def register_skill(self, name: str, category: str = "", source: str = "", status: str = "learned",
                       security_status: str = "unknown", notes: str = "", acceptance_status: str = "accepted") -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            existing = conn.execute("SELECT version, notes FROM skill_registry WHERE name = ?", (name,)).fetchone()
            version = 1
            if existing:
                version = int(existing[0] or 1)
                if notes and notes != (existing[1] or ""):
                    version += 1
            conn.execute(
                """
                INSERT INTO skill_registry (name, category, source, status, security_status, notes, version, updated_at, last_used, acceptance_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    source=excluded.source,
                    status=excluded.status,
                    security_status=excluded.security_status,
                    notes=excluded.notes,
                    version=excluded.version,
                    updated_at=excluded.updated_at,
                    acceptance_status=excluded.acceptance_status
                """,
                (name, category, source, status, security_status, notes, version, now, now, acceptance_status),
            )
            conn.commit()
        finally:
            conn.close()

    def accept_skill(self, name: str, tests_passed: bool, evidence: str = "", validator: str = "system", notes: str = "") -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        status = "accepted" if tests_passed else "rejected"
        try:
            conn.execute(
                """
                UPDATE skill_registry
                SET acceptance_status = ?, acceptance_evidence = ?, accepted_at = ?, updated_at = ?, status = ?
                WHERE name = ?
                """,
                (status, evidence[:500], now, now, "learned" if tests_passed else "failed", name),
            )
            conn.execute(
                """
                INSERT INTO skill_acceptance_events (skill_name, status, tests_passed, validator, evidence, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, status, 1 if tests_passed else 0, validator[:120], evidence[:500], notes[:500]),
            )
            if tests_passed:
                conn.execute(
                    """
                    UPDATE skill_remediation_tasks
                    SET status = 'closed', updated_at = ?
                    WHERE skill_name = ? AND status = 'open'
                    """,
                    (now, name),
                )
            conn.commit()
        finally:
            conn.close()

    def update_status(self, name: str, status: str) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                "UPDATE skill_registry SET status = ?, updated_at = ? WHERE name = ?",
                (status, now, name),
            )
            conn.commit()
        finally:
            conn.close()

    def record_use(self, name: str) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute("UPDATE skill_registry SET last_used = ? WHERE name = ?", (now, name))
            conn.commit()
        finally:
            conn.close()

    def register_from_capability_packs(self, root: str = "capability_packs") -> int:
        """Register skills from capability pack specs."""
        base = Path(root)
        if not base.is_absolute():
            base = Path(__file__).resolve().parent.parent / base
        if not base.exists():
            return 0
        count = 0
        for spec_path in base.glob("*/spec.json"):
            try:
                data = json.loads(spec_path.read_text(encoding="utf-8"))
                name = str(data.get("name") or spec_path.parent.name).strip()
                if not name:
                    continue
                category = str(data.get("category") or "").strip()
                notes = str(data.get("description") or "")[:300]
                acceptance_status = str(data.get("acceptance_status") or "pending")
                self.register_skill(
                    name=name,
                    category=category,
                    source="capability_pack",
                    status="learned",
                    notes=notes,
                    acceptance_status=acceptance_status,
                )
                count += 1
            except Exception:
                continue
        return count

    def get_skill(self, name: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM skill_registry WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def pending_skills(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT name, category, source, status, acceptance_status, updated_at
                FROM skill_registry
                WHERE acceptance_status = 'pending'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def auto_accept_pending(self, tests_passed: bool, evidence: str = "", validator: str = "auto", notes: str = "") -> int:
        """Accept/reject all pending skills in batch after a validation run."""
        rows = self.pending_skills(limit=10000)
        count = 0
        for r in rows:
            self.accept_skill(
                name=r["name"],
                tests_passed=tests_passed,
                evidence=evidence,
                validator=validator,
                notes=notes,
            )
            count += 1
        return count

    def list_skills(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT name, category, source, status, security_status, version, compatibility, tests_coverage, risk_score, updated_at, acceptance_status "
                "FROM skill_registry ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "name": r[0],
                    "category": r[1],
                    "source": r[2],
                    "status": r[3],
                    "security": r[4],
                    "version": r[5],
                    "compatibility": r[6],
                    "tests_coverage": r[7],
                    "risk_score": r[8],
                    "updated_at": r[9],
                    "acceptance_status": r[10],
                })
            return result
        finally:
            conn.close()

    def audit_coverage(self, tests_root: str = "/home/vito/vito-agent/tests") -> int:
        """Populate compatibility/risk/tests_coverage from static + runtime signals."""
        conn = self._get_conn()
        audited = 0
        try:
            tests_dir = Path(tests_root)
            test_files = list(tests_dir.glob("test_*.py")) if tests_dir.exists() else []
            packs_dir = Path(__file__).resolve().parent.parent / "capability_packs"
            pack_tests = list(packs_dir.glob("*/tests/test_*.py")) if packs_dir.exists() else []
            test_names = [p.name.lower() for p in (test_files + pack_tests)]
            rows = conn.execute(
                "SELECT name, category, source, notes, acceptance_status FROM skill_registry"
            ).fetchall()
            try:
                pb_rows = conn.execute(
                    "SELECT agent, task_type, action, success_count, fail_count FROM agent_playbooks"
                ).fetchall()
            except sqlite3.OperationalError:
                pb_rows = []
            try:
                fm_rows = conn.execute(
                    """
                    SELECT agent, task_type, COUNT(*) AS cnt
                    FROM failure_memory
                    WHERE created_at >= datetime('now', '-30 day')
                    GROUP BY agent, task_type
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                fm_rows = []
            now = datetime.now(timezone.utc).isoformat()
            playbook_by_action: dict[str, tuple[int, int]] = {}
            playbook_by_agent_task: dict[str, tuple[int, int]] = {}
            for pr in pb_rows:
                agent = str(pr[0] or "").strip().lower()
                task_type = str(pr[1] or "").strip().lower()
                action = str(pr[2] or "").strip().lower()
                ok = int(pr[3] or 0)
                fail = int(pr[4] or 0)
                if action:
                    cur = playbook_by_action.get(action, (0, 0))
                    playbook_by_action[action] = (cur[0] + ok, cur[1] + fail)
                if agent and task_type:
                    key = f"{agent}:{task_type}"
                    cur = playbook_by_agent_task.get(key, (0, 0))
                    playbook_by_agent_task[key] = (cur[0] + ok, cur[1] + fail)

            fail_memory_by_agent_task = {
                f"{str(r[0] or '').strip().lower()}:{str(r[1] or '').strip().lower()}": int(r[2] or 0)
                for r in fm_rows
            }

            for r in rows:
                name = (r[0] or "").strip()
                category = (r[1] or "").strip().lower()
                source = (r[2] or "").strip().lower()
                notes = r[3] or ""
                acceptance = (r[4] or "accepted").strip().lower()
                low = name.lower()

                # Compatibility heuristic
                compatibility = "stable"
                if any(k in low for k in ("deprecated", "legacy", "broken")):
                    compatibility = "review"

                # Tests coverage heuristic by name/category matching test files
                hits = 0
                keys = [low, category]
                for tn in test_names:
                    if any(k and k in tn for k in keys):
                        hits += 1
                static_coverage = min(1.0, hits / 3.0)

                # Risk score from static scan in notes
                sec_status, sec_note = scan_text(notes)
                risk = 0.2
                if sec_status == "needs_review":
                    risk = 0.7
                if "password" in notes.lower() or "token" in notes.lower():
                    risk = max(risk, 0.8)

                # Runtime signals from playbooks and failure memory
                succ, fail = playbook_by_action.get(low, (0, 0))
                if not succ and not fail and source and category:
                    succ, fail = playbook_by_agent_task.get(f"{source}:{category}", (0, 0))
                total = succ + fail
                success_rate = (float(succ) / float(total)) if total > 0 else 0.0
                fail_mem = fail_memory_by_agent_task.get(f"{source}:{category}", 0) if source and category else 0

                coverage = static_coverage
                if acceptance == "accepted":
                    coverage = max(coverage, 0.66 if total == 0 else min(1.0, 0.5 + 0.5 * success_rate))
                elif acceptance == "pending":
                    coverage = min(max(coverage, 0.2), 0.6)
                elif acceptance == "rejected":
                    coverage = min(coverage, 0.1)

                fail_pressure = (float(fail) / float(total) * 0.5) if total > 0 else 0.0
                fail_pressure += min(0.3, float(fail_mem) * 0.05)
                risk += fail_pressure
                if acceptance == "accepted":
                    risk -= 0.1
                elif acceptance == "pending":
                    risk += 0.1
                elif acceptance == "rejected":
                    risk += 0.2
                risk = max(0.0, min(1.0, risk))

                if acceptance == "rejected" or risk >= 0.65:
                    compatibility = "review"
                elif acceptance == "pending" or total == 0:
                    compatibility = "unknown"
                elif total >= 3 and success_rate >= 0.8 and risk < 0.35:
                    compatibility = "stable"
                else:
                    compatibility = "partial"

                conn.execute(
                    """
                    UPDATE skill_registry
                    SET compatibility = ?, tests_coverage = ?, risk_score = ?, security_status = ?, last_audit = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (
                        compatibility,
                        round(float(coverage), 3),
                        round(float(risk), 3),
                        sec_status,
                        now,
                        now,
                        name,
                    ),
                )
                audited += 1
            conn.commit()
        finally:
            conn.close()
        return audited

    def audit_summary(self, limit: int = 10) -> dict:
        conn = self._get_conn()
        try:
            totals = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN acceptance_status='pending' THEN 1 ELSE 0 END) AS pending,
                  SUM(CASE WHEN acceptance_status='rejected' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN risk_score >= 0.65 THEN 1 ELSE 0 END) AS high_risk,
                  SUM(CASE WHEN compatibility='stable' THEN 1 ELSE 0 END) AS stable
                FROM skill_registry
                """
            ).fetchone()
            risky = conn.execute(
                """
                SELECT name, category, source, risk_score, compatibility, acceptance_status
                FROM skill_registry
                ORDER BY risk_score DESC, updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return {
                "total": int(totals["total"] or 0),
                "pending": int(totals["pending"] or 0),
                "rejected": int(totals["rejected"] or 0),
                "high_risk": int(totals["high_risk"] or 0),
                "stable": int(totals["stable"] or 0),
                "top_risky": [dict(r) for r in risky],
            }
        finally:
            conn.close()

    def remediate_high_risk(self, limit: int = 50) -> dict:
        """
        Create remediation tasks for high-risk/review skills.
        Idempotent for open tasks by UNIQUE key.
        """
        conn = self._get_conn()
        created = 0
        rows_out: list[dict] = []
        try:
            rows = conn.execute(
                """
                SELECT name, category, source, acceptance_status, compatibility, risk_score
                FROM skill_registry
                WHERE risk_score >= 0.65 OR compatibility IN ('review')
                ORDER BY risk_score DESC, updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            for r in rows:
                name = str(r["name"] or "")
                acceptance = str(r["acceptance_status"] or "unknown").lower()
                comp = str(r["compatibility"] or "unknown").lower()
                risk = float(r["risk_score"] or 0.0)

                # choose primary action
                if acceptance == "pending":
                    reason = "pending_acceptance"
                    action = "run_tests_and_accept_or_reject"
                elif acceptance == "rejected":
                    reason = "rejected_skill"
                    action = "disable_or_rewrite_skill"
                elif risk >= 0.8:
                    reason = "critical_risk"
                    action = "security_review_and_retest"
                elif comp == "review":
                    reason = "compatibility_review"
                    action = "revalidate_with_smoke_and_unit_tests"
                else:
                    reason = "elevated_risk"
                    action = "add_tests_and_reduce_risk"

                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO skill_remediation_tasks(skill_name, reason, action, status, updated_at)
                    VALUES (?, ?, ?, 'open', datetime('now'))
                    """,
                    (name, reason, action),
                )
                if int(getattr(cur, "rowcount", 0) or 0) > 0:
                    created += 1
                rows_out.append(
                    {
                        "skill_name": name,
                        "reason": reason,
                        "action": action,
                        "risk_score": round(risk, 3),
                        "acceptance_status": acceptance,
                        "compatibility": comp,
                    }
                )
            conn.commit()
            open_total = conn.execute(
                "SELECT COUNT(*) n FROM skill_remediation_tasks WHERE status='open'"
            ).fetchone()
            return {
                "created": created,
                "open_total": int((open_total["n"] if open_total else 0) or 0),
                "items": rows_out[:20],
            }
        finally:
            conn.close()

    def list_remediation_tasks(self, status: str = "open", limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT skill_name, reason, action, status, created_at, updated_at
                FROM skill_remediation_tasks
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (status, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
