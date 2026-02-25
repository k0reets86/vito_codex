"""Automated executor for self-learning test jobs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from config.settings import settings
from config.self_learning_test_map import TEST_MAP_VERSION, resolve_family_targets
from modules.self_learning import SelfLearningEngine
from modules.skill_registry import SkillRegistry


class SelfLearningTestRunner:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.self_learning = SelfLearningEngine(sqlite_path=self.sqlite_path)
        self.skills = SkillRegistry(sqlite_path=self.sqlite_path)

    @staticmethod
    def _family_test_targets(task_family: str) -> str:
        return resolve_family_targets(
            task_family=task_family,
            override=str(getattr(settings, "SELF_LEARNING_TEST_TARGET_MAP", "") or ""),
        )

    @staticmethod
    def _coverage_from_return_code(code: int) -> float:
        if code == 0:
            return 0.92
        if code == 5:
            return 0.2
        return 0.45

    def _run_job_tests(self, task_family: str, timeout_sec: int = 120) -> tuple[bool, str, float, int, bool]:
        targets = self._family_test_targets(task_family)
        cmd = f"pytest -q -c /dev/null {targets}"
        cwd = Path("/home/vito/vito-agent")
        max_attempts = max(1, int(getattr(settings, "SELF_LEARNING_TEST_MAX_ATTEMPTS", 2) or 2))
        retry_on_fail = bool(getattr(settings, "SELF_LEARNING_TEST_RETRY_ON_FAIL", True))
        last_note = ""
        for attempt in range(1, max_attempts + 1):
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
                if passed:
                    flaky = attempt > 1
                    note = output or f"return_code={proc.returncode}"
                    if flaky:
                        note = f"flaky_pass_after_retry(attempt={attempt}): {note}"[:500]
                        coverage = min(coverage, 0.75)
                    return True, note, coverage, attempt, flaky
                last_note = output or f"return_code={proc.returncode}"
                if not retry_on_fail:
                    return False, last_note, coverage, attempt, False
            except subprocess.TimeoutExpired:
                last_note = "timeout"
                if not retry_on_fail:
                    return False, "timeout", 0.25, attempt, False
            except Exception as e:
                return False, f"runner_error:{e}", 0.2, attempt, False
        return False, last_note or "failed", 0.45, max_attempts, False

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
            ok, notes, coverage, attempts, flaky = self._run_job_tests(task_family=task_family, timeout_sec=timeout_sec)
            done = self.self_learning.complete_test_job(job_id=job_id, passed=ok, notes=notes, attempts=attempts, flaky=flaky)
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
                    if ok and not flaky:
                        risk = max(0.0, round(risk - 0.05, 4))
                    elif ok and flaky:
                        risk = max(0.0, round(risk - 0.01, 4))
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
                    "flaky": flaky,
                    "attempts": attempts,
                    "map_version": TEST_MAP_VERSION,
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
