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
        raw_map = str(getattr(settings, "SELF_LEARNING_TEST_TARGET_MAP", "") or "").strip()
        if raw_map:
            # Format: "research=tests/a.py tests/b.py;code=tests/c.py"
            for chunk in raw_map.split(";"):
                part = chunk.strip()
                if not part or "=" not in part:
                    continue
                key, val = part.split("=", 1)
                if key.strip().lower() == fam and val.strip():
                    return val.strip()
        mapping = {
            "research": "tests/test_research_agent.py tests/test_trend_scout.py",
            "strategy": "tests/test_vito_core.py tests/test_decision_loop.py",
            "code": "tests/test_agent_registry.py tests/test_step_contract.py",
            "content": "tests/test_content_creator.py tests/test_seo_agent.py",
            "routine": "tests/test_decision_loop.py tests/test_memory_manager.py",
            "self_learning": "tests/test_self_learning.py tests/test_skill_registry.py",
            "orchestrate": "tests/test_decision_loop.py tests/test_workflow_state_machine.py tests/test_workflow_threads.py",
            "tooling": "tests/test_tooling_runner.py tests/test_tooling_registry.py",
            "security": "tests/test_operator_policy.py tests/test_llm_guardrails.py",
            "publish": "tests/test_platform_scorecard.py tests/test_publisher_queue.py",
        }
        return mapping.get(fam, "tests/test_decision_loop.py tests/test_agent_registry.py")

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
