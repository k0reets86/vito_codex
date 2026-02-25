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
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS self_learning_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE NOT NULL,
                    category TEXT DEFAULT 'self_learning',
                    confidence REAL DEFAULT 0,
                    source TEXT DEFAULT 'reflection',
                    notes TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_lesson(self, goal_id: str, step_text: str, status: str, score: float, lesson: str, notes: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_lessons (goal_id, step_text, status, score, lesson, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (goal_id[:120], step_text[:500], status[:40], float(score or 0), lesson[:1500], notes[:1000]),
            )
            conn.commit()
        finally:
            conn.close()

    def register_candidate(self, skill_name: str, confidence: float, notes: str, category: str = "self_learning") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO self_learning_candidates (skill_name, category, confidence, notes, status, updated_at)
                VALUES (?, ?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(skill_name) DO UPDATE SET
                  confidence = excluded.confidence,
                  notes = excluded.notes,
                  updated_at = datetime('now')
                """,
                (skill_name[:120], category[:80], float(confidence or 0), notes[:1000]),
            )
            conn.commit()
        finally:
            conn.close()

    def list_lessons(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT goal_id, step_text, status, score, lesson, notes, created_at
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
                SELECT skill_name, category, confidence, source, notes, status, created_at, updated_at
                FROM self_learning_candidates
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
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
        self.record_lesson(
            goal_id=goal_id,
            step_text=step_text,
            status=status,
            score=score,
            lesson=lesson,
            notes=notes,
        )
        candidate_name = ""
        if bool(parsed.get("reusable_skill", False)) and score >= float(min_skill_score):
            candidate_name = str(parsed.get("skill_name", "") or "").strip().lower().replace(" ", "_")
            if candidate_name:
                self.register_candidate(
                    skill_name=f"selflearn:{candidate_name}",
                    confidence=score,
                    notes=f"{lesson}; {notes}"[:1000],
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
