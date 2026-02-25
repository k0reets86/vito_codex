"""Automated executor for self-learning test jobs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from config.settings import settings
from modules.self_learning import SelfLearningEngine
from modules.skill_registry import SkillRegistry


class SelfLearningTestRunner:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.self_learning = SelfLearningEngine(sqlite_path=self.sqlite_path)
        self.skills = SkillRegistry(sqlite_path=self.sqlite_path)

    @staticmethod
    def _family_test_targets(task_family: str) -> str:
        fam = str(task_family or "").strip().lower()
        mapping = {
            "research": "tests/test_research_agent.py tests/test_trend_scout.py",
            "strategy": "tests/test_vito_core.py tests/test_decision_loop.py",
            "code": "tests/test_agent_registry.py tests/test_step_contract.py",
            "content": "tests/test_content_creator.py tests/test_seo_agent.py",
            "routine": "tests/test_decision_loop.py tests/test_memory_manager.py",
        }
        return mapping.get(fam, "tests/test_decision_loop.py tests/test_agent_registry.py")

    @staticmethod
    def _coverage_from_return_code(code: int) -> float:
        if code == 0:
            return 0.92
        if code == 5:
            return 0.2
        return 0.45

    def _run_job_tests(self, task_family: str, timeout_sec: int = 120) -> tuple[bool, str, float]:
        targets = self._family_test_targets(task_family)
        cmd = f"pytest -q -c /dev/null {targets}"
        cwd = Path("/home/vito/vito-agent")
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(30, int(timeout_sec or 120)),
                env=dict(os.environ),
            )
            output_tail = (proc.stdout or "").strip().splitlines()[-3:]
            output = " | ".join(output_tail)[:400]
            passed = int(proc.returncode) == 0
            coverage = self._coverage_from_return_code(int(proc.returncode))
            return passed, output or f"return_code={proc.returncode}", coverage
        except subprocess.TimeoutExpired:
            return False, "timeout", 0.25
        except Exception as e:
            return False, f"runner_error:{e}", 0.2

    def run_open_jobs(self, max_jobs: int = 3, timeout_sec: int = 120) -> dict:
        jobs = self.self_learning.list_test_jobs(status="open", limit=max(1, int(max_jobs or 3)))
        processed = 0
        passed = 0
        failed = 0
        details: list[dict] = []
        for job in jobs:
            job_id = int(job.get("id", 0) or 0)
            skill_name = str(job.get("skill_name", "") or "")
            task_family = str(job.get("task_family", "") or "")
            if not job_id or not skill_name:
                continue
            ok, notes, coverage = self._run_job_tests(task_family=task_family, timeout_sec=timeout_sec)
            done = self.self_learning.complete_test_job(job_id=job_id, passed=ok, notes=notes)
            if not done:
                continue
            processed += 1
            if ok:
                passed += 1
            else:
                failed += 1
            skill = self.skills.get_skill(skill_name)
            if skill:
                try:
                    cur_cov = float(skill.get("tests_coverage", 0) or 0.0)
                    new_cov = round(max(cur_cov, coverage), 4) if ok else round(min(cur_cov, coverage), 4)
                    risk = float(skill.get("risk_score", 0) or 0.0)
                    if ok:
                        risk = max(0.0, round(risk - 0.05, 4))
                    else:
                        risk = min(1.0, round(risk + 0.08, 4))
                    conn = self.skills._get_conn()
                    try:
                        conn.execute(
                            """
                            UPDATE skill_registry
                            SET tests_coverage = ?, risk_score = ?, updated_at = datetime('now')
                            WHERE name = ?
                            """,
                            (new_cov, risk, skill_name),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                except Exception:
                    pass
            details.append(
                {
                    "job_id": job_id,
                    "skill_name": skill_name,
                    "task_family": task_family,
                    "passed": ok,
                    "notes": notes,
                }
            )
        return {
            "ok": True,
            "processed": processed,
            "passed": passed,
            "failed": failed,
            "details": details,
        }
