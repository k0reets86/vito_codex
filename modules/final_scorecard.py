"""Final scorecard calculator for VITO 10/10 tracking."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import settings
from modules.platform_scorecard import PlatformScorecard


CHECKLIST_PATH = Path("/home/vito/vito-agent/docs/20_CHECKLIST_VITO_10x10_2026-02-25.md")


@dataclass
class ScoreBlock:
    name: str
    score: float
    note: str


class FinalScorecard:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _count(self, table: str) -> int:
        conn = self._conn()
        try:
            row = conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()
            return int(row["n"] or 0)
        except Exception:
            return 0
        finally:
            conn.close()

    def _avg_skill_coverage(self) -> float:
        conn = self._conn()
        try:
            row = conn.execute("SELECT AVG(tests_coverage) c FROM skill_registry").fetchone()
            return float(row["c"] or 0.0)
        except Exception:
            return 0.0
        finally:
            conn.close()

    def _checklist_done_ratio(self) -> float:
        if not CHECKLIST_PATH.exists():
            return 0.0
        text = CHECKLIST_PATH.read_text(encoding="utf-8", errors="ignore")
        all_items = re.findall(r"^- \[(DONE|TODO|IN_PROGRESS|BLOCKED)\] .+$", text, flags=re.M)
        done = re.findall(r"^- \[DONE\] .+$", text, flags=re.M)
        if not all_items:
            return 0.0
        return len(done) / len(all_items)

    def _recent_telegram_conflict(self) -> bool:
        # Cheap local signal from log file (if present)
        log_path = Path("/home/vito/vito-agent/logs/vito.log")
        if not log_path.exists():
            return False
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-300:])
            return "telegram.error.Conflict" in tail or "getUpdates request" in tail
        except Exception:
            return False

    def calculate(self) -> dict:
        skills = self._count("skills")
        playbooks = self._count("agent_playbooks")
        facts = self._count("execution_facts")
        failures = self._count("failure_memory")
        feedback = self._count("agent_feedback")
        coverage = self._avg_skill_coverage()
        ratio = self._checklist_done_ratio()
        pscore_rows = PlatformScorecard(self.sqlite_path).score(
            ["gumroad", "etsy", "wordpress", "twitter", "kofi", "printful"], days=30
        )
        p_avg = sum(r["readiness_score"] for r in pscore_rows) / max(len(pscore_rows), 1)
        conflict = self._recent_telegram_conflict()

        # 1) Orchestration
        orchestration = min(10.0, 7.0 + (1.0 if feedback >= 100 else 0.5) + (1.0 if facts >= 100 else 0.0) + (1.0 if ratio >= 0.9 else 0.5))
        # 2) Memory/skills
        mem = min(10.0, 6.0 + (2.0 if skills >= 120 else 1.0) + (1.0 if playbooks >= 20 else 0.5) + min(1.0, coverage * 2.0))
        # 3) Dialog
        dialog = 8.0 - (2.0 if conflict else 0.0) + (1.0 if facts >= 120 else 0.0)
        dialog = max(1.0, min(10.0, dialog))
        # 4) Self-learning
        self_learning = min(10.0, 6.0 + (2.0 if playbooks >= 20 else 1.0) + (1.0 if failures >= 50 else 0.5) + (1.0 if ratio >= 0.9 else 0.5))
        # 5) Publish/commerce
        publish = max(1.0, min(10.0, 4.0 + (p_avg / 20.0)))  # 0..100 -> +0..5
        # 6) Security/budget
        sec = min(10.0, 7.0 + (1.0 if facts >= 120 else 0.5) + (1.0 if ratio >= 0.9 else 0.5))
        # 7) ТЗ compliance
        tz = max(1.0, min(10.0, round(ratio * 10, 2)))

        blocks = [
            ScoreBlock("Оркестрация агентов", round(orchestration, 2), "feedback/facts/checklist"),
            ScoreBlock("Память и навыки", round(mem, 2), "skills/playbooks/tests_coverage"),
            ScoreBlock("Диалог с владельцем", round(dialog, 2), "telegram stability + facts"),
            ScoreBlock("Самообучение", round(self_learning, 2), "playbooks/failure loop"),
            ScoreBlock("Публикации/коммерция", round(publish, 2), "platform readiness score"),
            ScoreBlock("Безопасность/контроль расходов", round(sec, 2), "guards/policy/facts"),
            ScoreBlock("Соответствие ТЗ", round(tz, 2), "checklist done ratio"),
        ]
        avg = round(sum(b.score for b in blocks) / len(blocks), 2)
        return {
            "avg": avg,
            "blocks": [b.__dict__ for b in blocks],
            "metrics": {
                "skills": skills,
                "playbooks": playbooks,
                "execution_facts": facts,
                "failure_memory": failures,
                "agent_feedback": feedback,
                "avg_skill_coverage": round(coverage, 3),
                "checklist_done_ratio": round(ratio, 3),
                "platform_readiness_avg": round(p_avg, 2),
                "telegram_conflict_signal": conflict,
            },
            "platform_scorecard": pscore_rows,
        }
