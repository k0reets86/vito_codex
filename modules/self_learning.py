"""Reflection-based self-learning store for VITO."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from typing import Optional

from config.settings import settings
from modules.failure_memory import FailureMemory
from modules.playbook_registry import PlaybookRegistry


class SelfLearningEngine:
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
                CREATE TABLE IF NOT EXISTS self_learning_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT DEFAULT '',
                    step_text TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    score REAL DEFAULT 0,
                    lesson TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    candidate_skill TEXT DEFAULT '',
                    task_family TEXT DEFAULT '',
                    source_agent TEXT DEFAULT '',
                    evidence_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE NOT NULL,
                    category TEXT DEFAULT 'self_learning',
                    confidence REAL DEFAULT 0,
                    source TEXT DEFAULT 'reflection',
                    task_family TEXT DEFAULT '',
                    source_agent TEXT DEFAULT '',
                    domain_role TEXT DEFAULT '',
                    evidence_json TEXT DEFAULT '{}',
                    notes TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    optimized_confidence REAL DEFAULT 0,
                    lessons_count INTEGER DEFAULT 0,
                    pass_rate REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_optimizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    confidence_before REAL DEFAULT 0,
                    confidence_after REAL DEFAULT 0,
                    lessons_count INTEGER DEFAULT 0,
                    pass_rate REAL DEFAULT 0,
                    recommendation TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_promotion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    decision TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_test_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    task_family TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'open',
                    attempts INTEGER DEFAULT 0,
                    flaky INTEGER DEFAULT 0,
                    result_notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(skill_name, reason, status)
                );
                """
            )
            lesson_cols = {r["name"] for r in conn.execute("PRAGMA table_info(self_learning_lessons)").fetchall()}
            if "candidate_skill" not in lesson_cols:
                conn.execute("ALTER TABLE self_learning_lessons ADD COLUMN candidate_skill TEXT DEFAULT ''")
            if "task_family" not in lesson_cols:
                conn.execute("ALTER TABLE self_learning_lessons ADD COLUMN task_family TEXT DEFAULT ''")
            if "source_agent" not in lesson_cols:
                conn.execute("ALTER TABLE self_learning_lessons ADD COLUMN source_agent TEXT DEFAULT ''")
            if "evidence_json" not in lesson_cols:
                conn.execute("ALTER TABLE self_learning_lessons ADD COLUMN evidence_json TEXT DEFAULT '{}'")
            cand_cols = {r["name"] for r in conn.execute("PRAGMA table_info(self_learning_candidates)").fetchall()}
            if "optimized_confidence" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN optimized_confidence REAL DEFAULT 0")
            if "lessons_count" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN lessons_count INTEGER DEFAULT 0")
            if "pass_rate" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN pass_rate REAL DEFAULT 0")
            if "task_family" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN task_family TEXT DEFAULT ''")
            if "source_agent" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN source_agent TEXT DEFAULT ''")
            if "domain_role" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN domain_role TEXT DEFAULT ''")
            if "evidence_json" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN evidence_json TEXT DEFAULT '{}'")
            job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(self_learning_test_jobs)").fetchall()}
            if "attempts" not in job_cols:
                conn.execute("ALTER TABLE self_learning_test_jobs ADD COLUMN attempts INTEGER DEFAULT 0")
            if "flaky" not in job_cols:
                conn.execute("ALTER TABLE self_learning_test_jobs ADD COLUMN flaky INTEGER DEFAULT 0")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_learning_thresholds (
                    task_family TEXT PRIMARY KEY,
                    confidence_min REAL DEFAULT 0.78,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_lesson(
        self,
        goal_id: str,
        step_text: str,
        status: str,
        score: float,
        lesson: str,
        notes: str = "",
        candidate_skill: str = "",
        task_family: str = "",
        source_agent: str = "",
        evidence: dict | None = None,
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_lessons (goal_id, step_text, status, score, lesson, notes, candidate_skill, task_family, source_agent, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal_id[:120],
                    step_text[:500],
                    status[:40],
                    float(score or 0),
                    lesson[:1500],
                    notes[:1000],
                    candidate_skill[:140],
                    task_family[:60],
                    source_agent[:80],
                    json.dumps(evidence or {}, ensure_ascii=False)[:2000],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def register_candidate(
        self,
        skill_name: str,
        confidence: float,
        notes: str,
        category: str = "self_learning",
        task_family: str = "",
        source_agent: str = "",
        domain_role: str = "",
        evidence: dict | None = None,
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_candidates (skill_name, category, confidence, task_family, source_agent, domain_role, evidence_json, notes, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(skill_name) DO UPDATE SET
                  confidence = excluded.confidence,
                  task_family = CASE WHEN excluded.task_family != '' THEN excluded.task_family ELSE task_family END,
                  source_agent = CASE WHEN excluded.source_agent != '' THEN excluded.source_agent ELSE source_agent END,
                  domain_role = CASE WHEN excluded.domain_role != '' THEN excluded.domain_role ELSE domain_role END,
                  evidence_json = CASE WHEN excluded.evidence_json != '{}' THEN excluded.evidence_json ELSE evidence_json END,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (
                    skill_name[:120],
                    category[:80],
                    float(confidence or 0),
                    task_family[:60],
                    source_agent[:80],
                    domain_role[:80],
                    json.dumps(evidence or {}, ensure_ascii=False)[:2000],
                    notes[:1000],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_lessons(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT goal_id, step_text, status, score, lesson, notes, candidate_skill, task_family, source_agent, evidence_json, created_at
                FROM self_learning_lessons
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_candidates(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT skill_name, category, confidence, optimized_confidence, lessons_count, pass_rate, source, task_family, source_agent, domain_role, evidence_json, notes, status, created_at, updated_at
                FROM self_learning_candidates
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def set_candidate_status(self, skill_name: str, status: str, notes: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                UPDATE self_learning_candidates
                SET status = ?, notes = CASE WHEN ? != '' THEN ? ELSE notes END, updated_at = datetime('now')
                WHERE skill_name = ?
                """,
                (status[:40], notes[:1000], notes[:1000], skill_name[:140]),
            )
            conn.commit()
        finally:
            conn.close()

    def optimization_runs(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT skill_name, confidence_before, confidence_after, lessons_count, pass_rate, recommendation, notes, created_at
                FROM self_learning_optimizations
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_test_jobs(self, status: str = "", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT id, skill_name, task_family, reason, status, attempts, flaky, result_notes, created_at, updated_at
                    FROM self_learning_test_jobs
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, skill_name, task_family, reason, status, attempts, flaky, result_notes, created_at, updated_at
                    FROM self_learning_test_jobs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def complete_test_job(self, job_id: int, passed: bool, notes: str = "", attempts: int = 1, flaky: bool = False) -> bool:
        conn = self._get_conn()
        try:
            status = "passed" if passed else "failed"
            cur = conn.execute(
                """
                UPDATE self_learning_test_jobs
                SET status = ?, result_notes = ?, attempts = ?, flaky = ?, updated_at = datetime('now')
                WHERE id = ? AND status = 'open'
                """,
                (status, notes[:500], max(1, int(attempts or 1)), 1 if flaky else 0, int(job_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
        finally:
            conn.close()

    def generate_test_jobs(self, limit: int = 20) -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        created = 0
        try:
            from modules.skill_registry import SkillRegistry
            reg = SkillRegistry(sqlite_path=self.sqlite_path)
            rows = conn.execute(
                """
                SELECT skill_name, task_family, status, optimized_confidence, lessons_count
                FROM self_learning_candidates
                WHERE status IN ('ready', 'hold')
                ORDER BY updated_at DESC
                LIMIT 200
                """
            ).fetchall()
            for r in rows:
                if created >= int(limit):
                    break
                skill_name = str(r["skill_name"] or "")
                skill = reg.get_skill(skill_name)
                tests_cov = float((skill or {}).get("tests_coverage", 0) or 0.0)
                conf = float(r["optimized_confidence"] or 0.0)
                reason = ""
                if tests_cov < 0.75:
                    reason = "tests_coverage_low"
                elif str(r["status"] or "") == "hold" and conf >= float(settings.SELF_LEARNING_SKILL_SCORE_MIN or 0.78):
                    reason = "confidence_ready_but_hold"
                if not reason:
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO self_learning_test_jobs
                    (skill_name, task_family, reason, status, updated_at)
                    VALUES (?, ?, ?, 'open', datetime('now'))
                    """,
                    (skill_name[:140], str(r["task_family"] or "")[:60], reason[:120]),
                )
                if int(cur.rowcount or 0) > 0:
                    created += 1
            conn.commit()
            return {"ok": True, "created": created}
        finally:
            conn.close()

    def promotion_events(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT skill_name, decision, reason, created_at
                FROM self_learning_promotion_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def optimize_candidates(
        self,
        days: int = 30,
        min_lessons: int = 3,
        promote_confidence_min: float = 0.82,
        auto_promote: bool = False,
    ) -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        updated = 0
        promoted = 0
        decisions: list[dict] = []
        try:
            candidates = conn.execute(
                """
                SELECT skill_name, confidence, notes, status, task_family, source_agent, domain_role
                FROM self_learning_candidates
                WHERE status IN ('pending', 'optimized', 'ready')
                ORDER BY updated_at DESC
                LIMIT 200
                """
            ).fetchall()
            for row in candidates:
                skill = str(row["skill_name"] or "")
                base_conf = float(row["confidence"] or 0.0)
                task_family = str(row["task_family"] or "")
                source_agent = str(row["source_agent"] or "")
                domain_role = str(row["domain_role"] or "")
                stem = skill.split(":")[-1].replace("selflearn_", "").replace("selflearn", "").strip("_")
                pattern = f"%{stem}%"
                lessons = conn.execute(
                    """
                    SELECT status, score, task_family
                    FROM self_learning_lessons
                    WHERE created_at >= datetime('now', ?)
                      AND (candidate_skill = ? OR lower(step_text) LIKE lower(?) OR lower(lesson) LIKE lower(?))
                    ORDER BY id DESC
                    LIMIT 200
                    """,
                    (f"-{max(1, int(days or 30))} day", skill, pattern, pattern),
                ).fetchall()
                if not lessons:
                    lessons = conn.execute(
                        """
                        SELECT status, score, task_family
                        FROM self_learning_lessons
                        WHERE created_at >= datetime('now', ?)
                        ORDER BY id DESC
                        LIMIT 100
                        """,
                        (f"-{max(1, int(days or 30))} day",),
                    ).fetchall()
                lessons_count = len(lessons)
                if lessons_count <= 0:
                    pass_rate = 0.0
                    avg_score = 0.0
                else:
                    pass_count = sum(1 for r in lessons if str(r["status"] or "") == "completed")
                    pass_rate = pass_count / max(1, lessons_count)
                    avg_score = sum(float(r["score"] or 0.0) for r in lessons) / max(1, lessons_count)
                family_rows = [r for r in lessons if task_family and str(r["task_family"] or "") == task_family]
                if family_rows:
                    family_pass = sum(1 for r in family_rows if str(r["status"] or "") == "completed")
                    family_pass_rate = family_pass / max(1, len(family_rows))
                else:
                    family_pass_rate = pass_rate
                family_bias = 0.03 if family_pass_rate >= 0.75 else (-0.03 if family_pass_rate <= 0.4 else 0.0)
                playbook_signal = self._agent_playbook_signal(source_agent, task_family)
                failure_signal = self._agent_failure_signal(source_agent, task_family)
                optimized = (
                    (0.38 * base_conf)
                    + (0.30 * avg_score)
                    + (0.18 * pass_rate)
                    + (0.05 * family_pass_rate)
                    + (0.06 * playbook_signal)
                    - (0.05 * failure_signal)
                    + family_bias
                )
                optimized = max(0.0, min(1.0, optimized))
                threshold = self.get_threshold_for_family(task_family, float(promote_confidence_min))
                recommendation = "hold"
                if lessons_count >= int(min_lessons) and pass_rate >= 0.65 and optimized >= threshold:
                    recommendation = "ready"
                next_status = "optimized" if recommendation == "hold" else "ready"
                conn.execute(
                    """
                    UPDATE self_learning_candidates
                    SET optimized_confidence = ?, lessons_count = ?, pass_rate = ?, status = ?, updated_at = datetime('now')
                    WHERE skill_name = ?
                    """,
                    (optimized, lessons_count, pass_rate, next_status, skill),
                )
                conn.execute(
                    """
                    INSERT INTO self_learning_optimizations
                    (skill_name, confidence_before, confidence_after, lessons_count, pass_rate, recommendation, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill[:140],
                        base_conf,
                        optimized,
                        lessons_count,
                        pass_rate,
                        recommendation,
                        f"task_family={task_family}; family_pass_rate={family_pass_rate:.3f}; min_lessons={int(min_lessons)}; threshold={float(promote_confidence_min)}"[:300],
                    ),
                )
                updated += 1
                decisions.append(
                    {
                        "skill_name": skill,
                        "confidence_before": round(base_conf, 4),
                        "confidence_after": round(optimized, 4),
                        "lessons_count": lessons_count,
                        "pass_rate": round(pass_rate, 4),
                        "task_family": task_family,
                        "source_agent": source_agent,
                        "domain_role": domain_role,
                        "family_pass_rate": round(family_pass_rate, 4),
                        "playbook_signal": round(playbook_signal, 4),
                        "failure_signal": round(failure_signal, 4),
                        "recommendation": recommendation,
                        "threshold": round(threshold,4),
                    }
                )
                self.adjust_threshold_for_family(task_family, pass_rate, avg_score, conn=conn)
            conn.commit()
        finally:
            conn.close()

        if auto_promote:
            promoted = self.auto_promote_ready_candidates()
        test_jobs = self.generate_test_jobs(limit=20)
        return {
            "ok": True,
            "updated": updated,
            "promoted": promoted,
            "test_jobs_created": int(test_jobs.get("created", 0) or 0),
            "decisions": decisions[:40],
        }

    def auto_promote_ready_candidates(self) -> int:
        """Safe promotion: only when skill-registry quality gates pass."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        changed = 0
        try:
            candidates = conn.execute(
                """
                SELECT skill_name, optimized_confidence, lessons_count, pass_rate, task_family, source_agent, domain_role
                FROM self_learning_candidates
                WHERE status = 'ready'
                ORDER BY updated_at ASC
                LIMIT 100
                """
            ).fetchall()
            from modules.skill_registry import SkillRegistry
            reg = SkillRegistry(sqlite_path=self.sqlite_path)
            for row in candidates:
                skill_name = str(row["skill_name"] or "")
                skill = reg.get_skill(skill_name)
                if not skill:
                    conn.execute(
                        "UPDATE self_learning_candidates SET status='needs_registry', updated_at=datetime('now') WHERE skill_name=?",
                        (skill_name,),
                    )
                    conn.execute(
                        "INSERT INTO self_learning_promotion_events (skill_name, decision, reason) VALUES (?, 'hold', ?)",
                        (skill_name, "skill_registry_missing"),
                    )
                    continue
                tests_cov = float(skill.get("tests_coverage", 0) or 0.0)
                risk = float(skill.get("risk_score", 0) or 0.0)
                security = str(skill.get("security_status", "unknown") or "unknown").lower()
                conf = float(row["optimized_confidence"] or 0.0)
                lessons_count = int(row["lessons_count"] or 0)
                pass_rate = float(row["pass_rate"] or 0.0)
                source_agent = str(row["source_agent"] or "")
                domain_role = str(row["domain_role"] or "")
                gate_reason = f"cov={tests_cov:.2f},risk={risk:.2f},sec={security},conf={conf:.2f}"
                gate_ok = (
                    tests_cov >= 0.75
                    and risk <= 0.35
                    and security not in {"blocked", "critical"}
                    and conf >= float(settings.SELF_LEARNING_SKILL_SCORE_MIN or 0.78)
                    and lessons_count >= int(getattr(settings, "SELF_LEARNING_MIN_LESSONS", 3) or 3)
                    and pass_rate >= 0.65
                )
                if gate_ok:
                    flaky_row = conn.execute(
                        """
                        SELECT 1
                        FROM self_learning_test_jobs
                        WHERE skill_name = ?
                          AND status = 'passed'
                          AND flaky = 1
                          AND updated_at >= datetime('now', ?)
                        LIMIT 1
                        """,
                        (skill_name, f"-{max(1, int(getattr(settings, 'SELF_LEARNING_FLAKY_COOLDOWN_HOURS', 72) or 72))} hour"),
                    ).fetchone()
                    if flaky_row:
                        gate_ok = False
                        gate_reason += ",flaky_cooldown=1"
                if gate_ok:
                    win_days = max(1, int(getattr(settings, "SELF_LEARNING_FLAKY_WINDOW_DAYS", 30) or 30))
                    flaky_lim = float(getattr(settings, "SELF_LEARNING_FLAKY_RATE_MAX", 0.3) or 0.3)
                    decay_days = float(getattr(settings, "SELF_LEARNING_FLAKY_DECAY_DAYS", 14) or 14)
                    min_weight = float(getattr(settings, "SELF_LEARNING_FLAKY_MIN_WEIGHT", 0.12) or 0.12)
                    flaky_rate, weighted_runs = self._decayed_flaky_rate(
                        conn=conn,
                        skill_name=skill_name,
                        window_days=win_days,
                        decay_days=decay_days,
                        min_weight=min_weight,
                    )
                    if weighted_runs >= 2.5 and flaky_rate > flaky_lim:
                        gate_ok = False
                        gate_reason += f",flaky_rate={flaky_rate:.2f}>{flaky_lim:.2f},weighted_runs={weighted_runs:.2f}"
                if not gate_ok:
                    conn.execute(
                        "UPDATE self_learning_candidates SET status='hold', updated_at=datetime('now') WHERE skill_name=?",
                        (skill_name,),
                    )
                    if tests_cov < 0.75:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO self_learning_test_jobs
                            (skill_name, task_family, reason, status, updated_at)
                            VALUES (?, ?, 'tests_coverage_low', 'open', datetime('now'))
                            """,
                            (skill_name[:140], str(row["task_family"] or "")[:60]),
                        )
                    conn.execute(
                        "INSERT INTO self_learning_promotion_events (skill_name, decision, reason) VALUES (?, 'hold', ?)",
                        (skill_name, f"gate_failed:{gate_reason}"),
                    )
                    continue
                reg.accept_skill(
                    name=skill_name,
                    tests_passed=True,
                    evidence=f"self_learning_auto_promote agent={source_agent} role={domain_role} conf={conf:.3f} lessons={lessons_count} pass_rate={pass_rate:.3f}",
                    validator="self_learning_optimizer",
                    notes="auto-promoted by safe gates",
                )
                conn.execute(
                    "UPDATE self_learning_candidates SET status='promoted', updated_at=datetime('now') WHERE skill_name=?",
                    (skill_name,),
                )
                conn.execute(
                    "INSERT INTO self_learning_promotion_events (skill_name, decision, reason) VALUES (?, 'promoted', ?)",
                    (skill_name, "accepted_in_skill_registry"),
                )
                changed += 1
            conn.commit()
            return changed
        finally:
            conn.close()

    def get_threshold_for_family(self, task_family: str, default: float = 0.78) -> float:
        if not task_family:
            return default
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT confidence_min
                FROM self_learning_thresholds
                WHERE task_family = ?
                """,
                (task_family[:60],),
            ).fetchone()
            if row and row["confidence_min"] not in (None, ""):
                return float(row["confidence_min"])
        finally:
            conn.close()
        return default

    def adjust_threshold_for_family(self, task_family: str, pass_rate: float, avg_score: float, conn=None) -> None:
        if not task_family:
            return
        own_conn = conn is None
        db = conn or self._get_conn()
        try:
            row = db.execute(
                """
                SELECT confidence_min
                FROM self_learning_thresholds
                WHERE task_family = ?
                """,
                (task_family[:60],),
            ).fetchone()
            current = float(row["confidence_min"]) if row and row["confidence_min"] not in (None, "") else 0.78
        except Exception:
            if own_conn:
                try:
                    db.close()
                except Exception:
                    pass
            current = self.get_threshold_for_family(task_family)
            own_conn = False
            db = None
        delta = 0.0
        if pass_rate >= 0.85 and avg_score >= 0.7:
            delta = -0.03
        elif pass_rate <= 0.5:
            delta = 0.04
        outcome_rate, outcome_weight = self._family_outcome_signal(task_family)
        if outcome_rate is not None and outcome_weight >= 0.6:
            max_shift = float(getattr(settings, "SELF_LEARNING_THRESHOLD_OUTCOME_WEIGHT", 0.02) or 0.02)
            if outcome_rate >= 0.7:
                delta -= max_shift * min(1.0, (outcome_rate - 0.7) / 0.3)
            elif outcome_rate <= 0.45:
                delta += max_shift * min(1.0, (0.45 - outcome_rate) / 0.45)
        new_value = self._clamp_threshold(current + delta)
        if abs(new_value - current) < 0.005:
            if own_conn and db is not None:
                db.close()
            return
        if db is not None:
            try:
                db.execute(
                    """
                    INSERT INTO self_learning_thresholds (task_family, confidence_min, updated_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(task_family) DO UPDATE SET
                      confidence_min = excluded.confidence_min,
                      updated_at = excluded.updated_at
                    """,
                    (task_family[:60], new_value),
                )
                if own_conn:
                    db.commit()
            finally:
                if own_conn:
                    db.close()
            return
        self.set_threshold_for_family(task_family, new_value)

    def set_threshold_for_family(self, task_family: str, value: float) -> None:
        if not task_family:
            return
        value = self._clamp_threshold(value)
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_thresholds (task_family, confidence_min, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(task_family) DO UPDATE SET
                  confidence_min = excluded.confidence_min,
                  updated_at = excluded.updated_at
                """,
                (task_family[:60], value),
            )
            conn.commit()
        finally:
            conn.close()

    def list_thresholds(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT task_family, confidence_min, updated_at
                FROM self_learning_thresholds
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            out: list[dict] = []
            for row in rows:
                family = str(row["task_family"] or "")
                outcome_rate, outcome_weight = self._family_outcome_signal(family)
                out.append(
                    {
                        "task_family": family,
                        "confidence_min": round(float(row["confidence_min"] or 0.0), 4),
                        "updated_at": row["updated_at"] or "",
                        "outcome_rate": round(float(outcome_rate), 4) if outcome_rate is not None else None,
                        "outcome_weight": round(float(outcome_weight or 0.0), 4),
                    }
                )
            return out
        finally:
            conn.close()

    def recalibrate_thresholds(self, days: int = 45, min_lessons: int = 4) -> dict:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        updated = 0
        families: list[dict] = []
        try:
            rows = conn.execute(
                """
                SELECT task_family,
                       COUNT(*) AS n,
                       AVG(CASE WHEN status='completed' THEN 1.0 ELSE 0.0 END) AS pass_rate,
                       AVG(score) AS avg_score
                FROM self_learning_lessons
                WHERE task_family != ''
                  AND created_at >= datetime('now', ?)
                GROUP BY task_family
                HAVING COUNT(*) >= ?
                ORDER BY n DESC
                LIMIT 200
                """,
                (f"-{max(1, int(days or 45))} day", max(1, int(min_lessons or 4))),
            ).fetchall()
            for row in rows:
                family = str(row["task_family"] or "")
                before = self.get_threshold_for_family(family)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO self_learning_thresholds (task_family, confidence_min, updated_at)
                    VALUES (?, ?, datetime('now'))
                    """,
                    (family[:60], self._clamp_threshold(before)),
                )
                pass_rate = float(row["pass_rate"] or 0.0)
                avg_score = float(row["avg_score"] or 0.0)
                self.adjust_threshold_for_family(family, pass_rate=pass_rate, avg_score=avg_score, conn=conn)
                after_row = conn.execute(
                    "SELECT confidence_min FROM self_learning_thresholds WHERE task_family = ?",
                    (family,),
                ).fetchone()
                after = float(after_row["confidence_min"] or before) if after_row else before
                if abs(after - before) >= 0.005:
                    updated += 1
                families.append(
                    {
                        "task_family": family,
                        "lessons": int(row["n"] or 0),
                        "pass_rate": round(pass_rate, 4),
                        "avg_score": round(avg_score, 4),
                        "threshold_before": round(before, 4),
                        "threshold_after": round(after, 4),
                    }
                )
            conn.commit()
            return {"ok": True, "updated": updated, "families": families[:30]}
        finally:
            conn.close()

    def sync_promotion_outcomes_from_tests(
        self,
        days: int = 45,
        min_runs: int = 2,
        fail_rate_max: float = 0.35,
        flaky_rate_max: Optional[float] = None,
    ) -> dict:
        """Attach long-horizon postcheck outcomes for promoted skills based on recent test jobs."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        inserted = 0
        passed = 0
        failed = 0
        skipped = 0
        families_touched: set[str] = set()
        try:
            flaky_limit = float(
                flaky_rate_max
                if flaky_rate_max is not None
                else (getattr(settings, "SELF_LEARNING_FLAKY_RATE_MAX", 0.3) or 0.3)
            )
            rows = conn.execute(
                """
                SELECT c.skill_name,
                       c.task_family,
                       COUNT(*) AS total_n,
                       SUM(CASE WHEN j.status = 'failed' THEN 1 ELSE 0 END) AS fail_n,
                       SUM(CASE WHEN j.flaky = 1 THEN 1 ELSE 0 END) AS flaky_n,
                       MAX(j.updated_at) AS latest_job_at
                FROM self_learning_candidates c
                JOIN self_learning_test_jobs j
                  ON j.skill_name = c.skill_name
                WHERE c.status = 'promoted'
                  AND j.status IN ('passed', 'failed')
                  AND j.updated_at >= datetime('now', ?)
                GROUP BY c.skill_name, c.task_family
                ORDER BY latest_job_at DESC
                LIMIT 300
                """,
                (f"-{max(1, int(days or 45))} day",),
            ).fetchall()
            for row in rows:
                total_n = int(row["total_n"] or 0)
                if total_n < max(1, int(min_runs or 2)):
                    skipped += 1
                    continue
                skill_name = str(row["skill_name"] or "")
                task_family = str(row["task_family"] or "")
                fail_n = int(row["fail_n"] or 0)
                flaky_n = int(row["flaky_n"] or 0)
                fail_rate = float(fail_n) / max(1.0, float(total_n))
                flaky_rate = float(flaky_n) / max(1.0, float(total_n))
                decision = "postcheck_pass"
                if fail_rate > float(fail_rate_max or 0.35) or flaky_rate > flaky_limit:
                    decision = "postcheck_fail"
                signature = (
                    f"postcheck:{decision};window_days={max(1, int(days or 45))};"
                    f"runs={total_n};fails={fail_n};flaky={flaky_n};"
                    f"fail_rate={fail_rate:.3f};flaky_rate={flaky_rate:.3f}"
                )[:300]
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM self_learning_promotion_events
                    WHERE skill_name = ?
                      AND decision = ?
                      AND reason = ?
                    LIMIT 1
                    """,
                    (skill_name, decision, signature),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO self_learning_promotion_events (skill_name, decision, reason)
                    VALUES (?, ?, ?)
                    """,
                    (skill_name[:140], decision, signature),
                )
                inserted += 1
                if decision == "postcheck_pass":
                    passed += 1
                else:
                    failed += 1
                if task_family:
                    families_touched.add(task_family[:60])
            conn.commit()
            return {
                "ok": True,
                "inserted": inserted,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "families_touched": sorted(families_touched),
            }
        finally:
            conn.close()

    def remediate_degraded_promoted_skills(self, days: int = 45, max_actions: int = 3) -> dict:
        """Move degraded promoted skills back to hold and queue remediation test jobs."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        remediated = 0
        queued_jobs = 0
        touched: list[str] = []
        try:
            rows = conn.execute(
                """
                SELECT c.skill_name, c.task_family, e.reason AS fail_reason
                FROM self_learning_candidates c
                JOIN self_learning_promotion_events e
                  ON e.skill_name = c.skill_name
                WHERE c.status = 'promoted'
                  AND e.decision = 'postcheck_fail'
                  AND e.created_at >= datetime('now', ?)
                  AND e.id = (
                    SELECT MAX(e2.id)
                    FROM self_learning_promotion_events e2
                    WHERE e2.skill_name = c.skill_name
                      AND e2.decision = 'postcheck_fail'
                  )
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (f"-{max(1, int(days or 45))} day", max(1, int(max_actions or 3))),
            ).fetchall()
            for row in rows:
                skill_name = str(row["skill_name"] or "")
                task_family = str(row["task_family"] or "")
                fail_reason = str(row["fail_reason"] or "")[:260]
                conn.execute(
                    """
                    UPDATE self_learning_candidates
                    SET status = 'hold',
                        notes = CASE
                          WHEN notes = '' THEN ?
                          ELSE substr(notes || '; ' || ?, 1, 1000)
                        END,
                        updated_at = datetime('now')
                    WHERE skill_name = ?
                    """,
                    (f"remediation_needed:{fail_reason}", f"remediation_needed:{fail_reason}", skill_name[:140]),
                )
                remediation_reasons = self._remediation_reasons_for_failure(task_family, fail_reason)
                for remediation_reason in remediation_reasons:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO self_learning_test_jobs
                        (skill_name, task_family, reason, status, updated_at)
                        VALUES (?, ?, ?, 'open', datetime('now'))
                        """,
                        (skill_name[:140], task_family[:60], remediation_reason[:120]),
                    )
                    if int(cur.rowcount or 0) > 0:
                        queued_jobs += 1
                conn.execute(
                    """
                    INSERT INTO self_learning_promotion_events (skill_name, decision, reason)
                    VALUES (?, 'remediation_started', ?)
                    """,
                    (skill_name[:140], f"auto_hold_after_postcheck_fail:{fail_reason}"[:300]),
                )
                remediated += 1
                touched.append(skill_name)
            conn.commit()
            return {
                "ok": True,
                "remediated": remediated,
                "queued_jobs": queued_jobs,
                "skills": touched[:40],
            }
        finally:
            conn.close()

    @staticmethod
    def _remediation_reason_for_family(task_family: str) -> str:
        fam = str(task_family or "").strip().lower()
        if not fam:
            return "postcheck_remediation_generic"
        safe = re.sub(r"[^a-z0-9_]+", "_", fam).strip("_")[:40]
        if not safe:
            return "postcheck_remediation_generic"
        return f"postcheck_remediation_{safe}"

    @staticmethod
    def _remediation_reasons_for_failure(task_family: str, fail_reason: str = "") -> list[str]:
        """Build deterministic remediation playbooks from postcheck failure diagnostics."""
        base = SelfLearningEngine._remediation_reason_for_family(task_family)
        reasons: list[str] = [base]
        text = str(fail_reason or "").lower()
        fail_match = re.search(r"fail_rate=([0-9]*\.?[0-9]+)", text)
        flaky_match = re.search(r"flaky_rate=([0-9]*\.?[0-9]+)", text)
        fail_rate = float(fail_match.group(1)) if fail_match else 0.0
        flaky_rate = float(flaky_match.group(1)) if flaky_match else 0.0
        if fail_rate >= 0.45:
            reasons.append(f"{base}_regression")
        if flaky_rate >= 0.20:
            reasons.append(f"{base}_stability")
        out: list[str] = []
        seen: set[str] = set()
        for item in reasons:
            key = str(item or "").strip().lower()[:120]
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    def cleanup_old_test_jobs(self, max_age_days: int = 90) -> dict:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                DELETE FROM self_learning_test_jobs
                WHERE status IN ('passed', 'failed')
                  AND updated_at < datetime('now', ?)
                """,
                (f"-{max(1, int(max_age_days or 90))} day",),
            )
            conn.commit()
            return {"ok": True, "deleted": int(cur.rowcount or 0)}
        finally:
            conn.close()

    def _agent_playbook_signal(self, source_agent: str, task_family: str) -> float:
        agent = str(source_agent or "").strip().lower()
        family = str(task_family or "").strip().lower()
        if not agent:
            return 0.5
        try:
            rows = PlaybookRegistry(sqlite_path=self.sqlite_path).find(agent=agent, task_type=family, limit=8)
        except Exception:
            return 0.5
        if not rows:
            return 0.5
        weighted = 0.0
        total = 0.0
        for idx, row in enumerate(rows, start=1):
            succ = float(row.get("success_count") or 0.0)
            fail = float(row.get("fail_count") or 0.0)
            runs = succ + fail
            score = (succ / runs) if runs > 0 else 0.5
            weight = 1.0 / idx
            weighted += score * weight
            total += weight
        return max(0.0, min(1.0, (weighted / total) if total > 0 else 0.5))

    def _agent_failure_signal(self, source_agent: str, task_family: str) -> float:
        agent = str(source_agent or "").strip().lower()
        family = str(task_family or "").strip().lower()
        if not agent:
            return 0.0
        try:
            rows = FailureMemory(sqlite_path=self.sqlite_path).recent(limit=60)
        except Exception:
            return 0.0
        matched = [
            row for row in rows
            if str(row.get("agent", "")).strip().lower() == agent
            and (not family or family in str(row.get("task_type", "")).strip().lower())
        ]
        if not matched:
            return 0.0
        return max(0.0, min(1.0, len(matched) / 8.0))

    @staticmethod
    def _clamp_threshold(value: float) -> float:
        return max(0.65, min(0.95, float(value or 0.0)))

    def _family_outcome_signal(self, task_family: str) -> tuple[Optional[float], float]:
        if not task_family:
            return None, 0.0
        conn = self._get_conn()
        try:
            window_days = max(7, int(getattr(settings, "SELF_LEARNING_OUTCOME_WINDOW_DAYS", 60) or 60))
            decay_days = max(1.0, float(getattr(settings, "SELF_LEARNING_OUTCOME_DECAY_DAYS", 21) or 21))
            rows = conn.execute(
                """
                SELECT e.decision, (julianday('now') - julianday(e.created_at)) AS age_days
                FROM self_learning_promotion_events e
                JOIN self_learning_candidates c
                  ON c.skill_name = e.skill_name
                WHERE c.task_family = ?
                  AND e.created_at >= datetime('now', ?)
                ORDER BY e.id DESC
                LIMIT 200
                """,
                (task_family[:60], f"-{window_days} day"),
            ).fetchall()
            if not rows:
                return None, 0.0
            success_w = 0.0
            total_w = 0.0
            for row in rows:
                age_days = max(0.0, float(row["age_days"] or 0.0))
                weight = math.exp(-(age_days / decay_days))
                decision = str(row["decision"] or "").strip().lower()
                if decision in {"promoted", "postcheck_pass"}:
                    value = 1.0
                elif decision in {"hold", "rejected", "postcheck_fail"}:
                    value = 0.0
                else:
                    value = 0.5
                success_w += weight * value
                total_w += weight
            if total_w <= 0.0:
                return None, 0.0
            return (success_w / total_w), total_w
        finally:
            conn.close()

    def _decayed_flaky_rate(
        self,
        conn,
        skill_name: str,
        window_days: int,
        decay_days: float,
        min_weight: float = 0.12,
    ) -> tuple[float, float]:
        rows = conn.execute(
            """
            SELECT flaky, (julianday('now') - julianday(updated_at)) AS age_days
            FROM self_learning_test_jobs
            WHERE skill_name = ?
              AND status IN ('passed', 'failed')
              AND updated_at >= datetime('now', ?)
            ORDER BY id DESC
            LIMIT 300
            """,
            (skill_name, f"-{max(1, int(window_days or 30))} day"),
        ).fetchall()
        if not rows:
            return 0.0, 0.0
        decay = max(1.0, float(decay_days or 14.0))
        floor = max(0.01, min(1.0, float(min_weight or 0.12)))
        flaky_w = 0.0
        total_w = 0.0
        for row in rows:
            age_days = max(0.0, float(row["age_days"] or 0.0))
            weight = max(floor, math.exp(-(age_days / decay)))
            total_w += weight
            if int(row["flaky"] or 0) == 1:
                flaky_w += weight
        if total_w <= 0.0:
            return 0.0, 0.0
        return flaky_w / total_w, total_w

    def summary(self, days: int = 30) -> dict:
        conn = self._get_conn()
        try:
            window = f"-{max(1, int(days or 30))} day"
            lessons = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) AS n FROM self_learning_lessons WHERE created_at >= datetime('now', ?)",
                        (window,),
                    ).fetchone()
                    or {"n": 0}
                )["n"]
                or 0
            )
            avg_score = float(
                (
                    conn.execute(
                        "SELECT AVG(score) AS v FROM self_learning_lessons WHERE created_at >= datetime('now', ?)",
                        (window,),
                    ).fetchone()
                    or {"v": 0.0}
                )["v"]
                or 0.0
            )
            pending = int((conn.execute("SELECT COUNT(*) AS n FROM self_learning_candidates WHERE status='pending'").fetchone() or {"n": 0})["n"] or 0)
            ready = int((conn.execute("SELECT COUNT(*) AS n FROM self_learning_candidates WHERE status='ready'").fetchone() or {"n": 0})["n"] or 0)
            promoted = int((conn.execute("SELECT COUNT(*) AS n FROM self_learning_candidates WHERE status='promoted'").fetchone() or {"n": 0})["n"] or 0)
            open_jobs = int((conn.execute("SELECT COUNT(*) AS n FROM self_learning_test_jobs WHERE status='open'").fetchone() or {"n": 0})["n"] or 0)
            calib_rows = conn.execute(
                """
                SELECT task_family,
                       COUNT(*) AS n,
                       AVG(CASE WHEN status='completed' THEN 1.0 ELSE 0.0 END) AS pass_rate,
                       AVG(score) AS avg_score
                FROM self_learning_lessons
                WHERE created_at >= datetime('now', ?)
                GROUP BY task_family
                ORDER BY n DESC
                LIMIT 10
                """,
                (window,),
            ).fetchall()
            flaky_rows = conn.execute(
                """
                SELECT skill_name,
                       SUM(CASE WHEN flaky = 1 THEN 1 ELSE 0 END) AS flaky_n,
                       COUNT(*) AS total_n
                FROM self_learning_test_jobs
                WHERE status IN ('passed', 'failed')
                  AND updated_at >= datetime('now', ?)
                GROUP BY skill_name
                HAVING COUNT(*) >= 2
                ORDER BY (CAST(SUM(CASE WHEN flaky = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) DESC
                LIMIT 8
                """,
                (window,),
            ).fetchall()
            threshold_rows = conn.execute(
                """
                SELECT task_family, confidence_min, updated_at
                FROM self_learning_thresholds
                ORDER BY updated_at DESC
                LIMIT 12
                """
            ).fetchall()
            agent_rows = conn.execute(
                """
                SELECT source_agent,
                       COUNT(*) AS n,
                       AVG(CASE WHEN status = 'promoted' THEN 1.0 ELSE 0.0 END) AS promoted_rate,
                       AVG(optimized_confidence) AS avg_conf
                FROM self_learning_candidates
                WHERE source_agent != ''
                GROUP BY source_agent
                ORDER BY n DESC, avg_conf DESC
                LIMIT 12
                """
            ).fetchall()
            return {
                "window_days": int(days or 30),
                "lessons": lessons,
                "avg_score": round(avg_score, 4),
                "pending_candidates": pending,
                "ready_candidates": ready,
                "promoted_candidates": promoted,
                "open_test_jobs": open_jobs,
                "family_calibration": [
                    {
                        "task_family": str(r["task_family"] or ""),
                        "lessons": int(r["n"] or 0),
                        "pass_rate": round(float(r["pass_rate"] or 0.0), 4),
                        "avg_score": round(float(r["avg_score"] or 0.0), 4),
                    }
                    for r in calib_rows
                ],
                "flaky_by_skill": [
                    {
                        "skill_name": str(r["skill_name"] or ""),
                        "flaky_rate": round((float(r["flaky_n"] or 0.0) / max(1.0, float(r["total_n"] or 1.0))), 4),
                        "flaky_runs": int(r["flaky_n"] or 0),
                        "total_runs": int(r["total_n"] or 0),
                    }
                    for r in flaky_rows
                ],
                "thresholds": [
                    {
                        "task_family": str(r["task_family"] or ""),
                        "confidence_min": round(float(r["confidence_min"] or 0.0), 4),
                        "updated_at": str(r["updated_at"] or ""),
                    }
                    for r in threshold_rows
                ],
                "source_agents": [
                    {
                        "source_agent": str(r["source_agent"] or ""),
                        "candidates": int(r["n"] or 0),
                        "promoted_rate": round(float(r["promoted_rate"] or 0.0), 4),
                        "avg_optimized_confidence": round(float(r["avg_conf"] or 0.0), 4),
                    }
                    for r in agent_rows
                ],
            }
        finally:
            conn.close()

    async def reflect_step(
        self,
        llm_router,
        task_type,
        goal_id: str,
        step_text: str,
        step_result: dict,
        min_skill_score: float = 0.78,
        responsible_agent: str = "",
        execution_context: dict | None = None,
    ) -> dict:
        task_family = _task_family(task_type)
        status = str(step_result.get("status", "unknown"))
        output = step_result.get("output", "")
        error = step_result.get("error", "")
        ctx = execution_context or {}
        contract = ctx.get("contract") if isinstance(ctx, dict) else {}
        memory_context = ctx.get("memory_context") if isinstance(ctx, dict) else {}
        source_agent = str(
            responsible_agent
            or step_result.get("responsible_agent")
            or (contract.get("agent") if isinstance(contract, dict) else "")
            or ""
        ).strip().lower()
        evidence = {
            "status": status,
            "responsible_agent": source_agent,
            "task_family": task_family,
            "owned_outcomes": list((contract or {}).get("owned_outcomes", [])[:3]) if isinstance(contract, dict) else [],
            "recent_fact_actions": [
                str(x.get("action", "") or "")
                for x in list((memory_context or {}).get("recent_facts", [])[:3])
                if isinstance(x, dict)
            ],
            "recent_failures": len(list((memory_context or {}).get("recent_failures", []) or [])),
            "playbooks": len(list((memory_context or {}).get("playbooks", []) or [])),
        }
        prompt = (
            "You are a strict evaluator of agent execution steps.\n"
            "Return JSON only with keys: score, lesson, reusable_skill, skill_name, notes.\n"
            "Rules:\n"
            "- score is float 0..1.\n"
            "- reusable_skill true only if lesson is stable and repeatable.\n"
            "- skill_name must be snake_case short id (if reusable_skill=true).\n"
            f"Step: {step_text[:400]}\n"
            f"Status: {status}\n"
            f"Output: {str(output)[:600]}\n"
            f"Error: {str(error)[:300]}\n"
            f"Responsible agent: {source_agent[:80]}\n"
            f"Agent role: {str((contract or {}).get('role', ''))[:80]}\n"
            f"Owned outcomes: {', '.join(list((contract or {}).get('owned_outcomes', [])[:3]) if isinstance(contract, dict) else [])}\n"
            f"Related playbooks: {len(list((memory_context or {}).get('playbooks', []) or []))}\n"
            f"Recent failures: {len(list((memory_context or {}).get('recent_failures', []) or []))}"
        )
        parsed = None
        try:
            raw = await llm_router.call_llm(task_type=task_type, prompt=prompt, estimated_tokens=400)
            parsed = _parse_reflection(raw or "")
        except Exception:
            parsed = None
        if not parsed:
            parsed = {
                "score": 0.8 if status == "completed" else 0.2,
                "lesson": "step_completed" if status == "completed" else "step_failed",
                "reusable_skill": False,
                "skill_name": "",
                "notes": "fallback_reflection",
            }

        score = float(parsed.get("score", 0.0) or 0.0)
        lesson = str(parsed.get("lesson", "") or "").strip() or "no_lesson"
        notes = str(parsed.get("notes", "") or "").strip()
        candidate_skill_key = ""
        if bool(parsed.get("reusable_skill", False)) and score >= float(min_skill_score):
            raw_name = str(parsed.get("skill_name", "") or "").strip().lower().replace(" ", "_")
            if raw_name:
                candidate_skill_key = f"selflearn:{raw_name}"
        self.record_lesson(
            goal_id=goal_id,
            step_text=step_text,
            status=status,
            score=score,
            lesson=lesson,
            notes=notes,
            candidate_skill=candidate_skill_key,
            task_family=task_family,
            source_agent=source_agent,
            evidence=evidence,
        )
        candidate_name = ""
        if bool(parsed.get("reusable_skill", False)) and score >= float(min_skill_score):
            candidate_name = str(parsed.get("skill_name", "") or "").strip().lower().replace(" ", "_")
            if candidate_name:
                self.register_candidate(
                    skill_name=f"selflearn:{candidate_name}",
                    confidence=score,
                    notes=f"{lesson}; {notes}"[:1000],
                    task_family=task_family,
                    source_agent=source_agent,
                    domain_role=str((contract or {}).get("role", "") or "")[:80],
                    evidence=evidence,
                )
        return {"score": score, "lesson": lesson, "candidate_name": candidate_name}


def _parse_reflection(raw: str) -> Optional[dict]:
    if not raw:
        return None
    txt = raw.strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    s = txt.find("{")
    e = txt.rfind("}")
    if s >= 0 and e > s:
        fragment = txt[s : e + 1]
        try:
            return json.loads(fragment)
        except Exception:
            return None
    return None


def _task_family(task_type) -> str:
    try:
        if hasattr(task_type, "value"):
            return str(task_type.value or "").strip().lower()[:60]
        return str(task_type or "").strip().lower()[:60]
    except Exception:
        return "unknown"
