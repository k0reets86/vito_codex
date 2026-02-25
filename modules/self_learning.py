"""Reflection-based self-learning store for VITO."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from config.settings import settings


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
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE NOT NULL,
                    category TEXT DEFAULT 'self_learning',
                    confidence REAL DEFAULT 0,
                    source TEXT DEFAULT 'reflection',
                    task_family TEXT DEFAULT '',
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
            cand_cols = {r["name"] for r in conn.execute("PRAGMA table_info(self_learning_candidates)").fetchall()}
            if "optimized_confidence" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN optimized_confidence REAL DEFAULT 0")
            if "lessons_count" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN lessons_count INTEGER DEFAULT 0")
            if "pass_rate" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN pass_rate REAL DEFAULT 0")
            if "task_family" not in cand_cols:
                conn.execute("ALTER TABLE self_learning_candidates ADD COLUMN task_family TEXT DEFAULT ''")
            job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(self_learning_test_jobs)").fetchall()}
            if "attempts" not in job_cols:
                conn.execute("ALTER TABLE self_learning_test_jobs ADD COLUMN attempts INTEGER DEFAULT 0")
            if "flaky" not in job_cols:
                conn.execute("ALTER TABLE self_learning_test_jobs ADD COLUMN flaky INTEGER DEFAULT 0")
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
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_lessons (goal_id, step_text, status, score, lesson, notes, candidate_skill, task_family)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_candidates (skill_name, category, confidence, task_family, notes, status, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(skill_name) DO UPDATE SET
                  confidence = excluded.confidence,
                  task_family = CASE WHEN excluded.task_family != '' THEN excluded.task_family ELSE task_family END,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (skill_name[:120], category[:80], float(confidence or 0), task_family[:60], notes[:1000]),
            )
            conn.commit()
        finally:
            conn.close()

    def list_lessons(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT goal_id, step_text, status, score, lesson, notes, candidate_skill, task_family, created_at
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
                SELECT skill_name, category, confidence, optimized_confidence, lessons_count, pass_rate, source, task_family, notes, status, created_at, updated_at
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
                SELECT skill_name, confidence, notes, status, task_family
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
                optimized = (0.42 * base_conf) + (0.33 * avg_score) + (0.20 * pass_rate) + (0.05 * family_pass_rate) + family_bias
                optimized = max(0.0, min(1.0, optimized))
                recommendation = "hold"
                if lessons_count >= int(min_lessons) and pass_rate >= 0.65 and optimized >= float(promote_confidence_min):
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
                        "family_pass_rate": round(family_pass_rate, 4),
                        "recommendation": recommendation,
                    }
                )
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
                SELECT skill_name, optimized_confidence, lessons_count, pass_rate, task_family
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
                    fr = conn.execute(
                        """
                        SELECT
                          SUM(CASE WHEN flaky = 1 THEN 1 ELSE 0 END) AS flaky_n,
                          COUNT(*) AS total_n
                        FROM self_learning_test_jobs
                        WHERE skill_name = ?
                          AND status IN ('passed', 'failed')
                          AND updated_at >= datetime('now', ?)
                        """,
                        (skill_name, f"-{win_days} day"),
                    ).fetchone()
                    flaky_n = int((fr["flaky_n"] if fr else 0) or 0)
                    total_n = int((fr["total_n"] if fr else 0) or 0)
                    flaky_rate = (flaky_n / max(1, total_n)) if total_n > 0 else 0.0
                    if total_n >= 3 and flaky_rate > flaky_lim:
                        gate_ok = False
                        gate_reason += f",flaky_rate={flaky_rate:.2f}>{flaky_lim:.2f}"
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
                    evidence=f"self_learning_auto_promote conf={conf:.3f} lessons={lessons_count} pass_rate={pass_rate:.3f}",
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
    ) -> dict:
        task_family = _task_family(task_type)
        status = str(step_result.get("status", "unknown"))
        output = step_result.get("output", "")
        error = step_result.get("error", "")
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
            f"Error: {str(error)[:300]}"
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
