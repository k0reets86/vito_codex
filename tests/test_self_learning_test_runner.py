from types import SimpleNamespace

from config.self_learning_test_map import TEST_MAP_VERSION
from modules.self_learning import SelfLearningEngine
from modules.self_learning_test_runner import SelfLearningTestRunner
from modules.skill_registry import SkillRegistry


def test_self_learning_test_runner_run_open_jobs(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="research")
    sl.set_candidate_status(skill_name, "ready")
    sl.generate_test_jobs(limit=10)

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="2 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=2, timeout_sec=30)
    assert out["ok"] is True
    assert out["processed"] >= 1
    jobs = sl.list_test_jobs(status="passed", limit=10)
    assert jobs


def test_self_learning_test_runner_failure_updates_job(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_fail_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="code")
    sl.set_candidate_status(skill_name, "ready")
    sl.generate_test_jobs(limit=10)

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="1 failed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=2, timeout_sec=30)
    assert out["ok"] is True
    assert out["failed"] >= 1
    jobs = sl.list_test_jobs(status="failed", limit=10)
    assert jobs


def test_self_learning_test_runner_flaky_retry(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_flaky_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="research")
    sl.set_candidate_status(skill_name, "ready")
    sl.generate_test_jobs(limit=10)

    calls = {"n": 0}

    def _fake_run(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(returncode=1, stdout="1 failed\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="2 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert out["passed"] >= 1
    jobs = sl.list_test_jobs(status="passed", limit=10)
    assert jobs
    assert int(jobs[0]["flaky"] or 0) == 1
    assert int(jobs[0]["attempts"] or 0) == 2


def test_self_learning_test_runner_uses_override_map(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_map_skill"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="research")
    sl.set_candidate_status(skill_name, "ready")
    sl.generate_test_jobs(limit=10)

    called = {"cmd": ""}

    def _fake_run(*args, **kwargs):
        called["cmd"] = str(args[0] if args else kwargs.get("args", ""))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    monkeypatch.setattr("modules.self_learning_test_runner.settings.SELF_LEARNING_TEST_TARGET_MAP", "research=tests/test_self_learning.py")
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert "tests/test_self_learning.py" in called["cmd"]
    assert out["details"][0]["map_version"] == TEST_MAP_VERSION


def test_self_learning_test_runner_resolves_family_from_reason(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_reason_family"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="")
    sl.set_candidate_status(skill_name, "hold")
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, updated_at)
            VALUES (?, '', 'postcheck_remediation_research', 'open', datetime('now'))
            """,
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()

    called = {"cmd": ""}

    def _fake_run(*args, **kwargs):
        called["cmd"] = str(args[0] if args else kwargs.get("args", ""))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    monkeypatch.setattr("modules.self_learning_test_runner.settings.SELF_LEARNING_TEST_TARGET_MAP", "research=tests/test_self_learning.py")
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert "tests/test_self_learning.py" in called["cmd"]
    assert out["details"][0]["task_family"] == "research"


def test_self_learning_test_runner_maps_alias_family_to_default_suite(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_alias_family"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="")
    sl.set_candidate_status(skill_name, "hold")
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, updated_at)
            VALUES (?, '', 'postcheck_remediation_security_ops', 'open', datetime('now'))
            """,
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()

    called = {"cmd": ""}

    def _fake_run(*args, **kwargs):
        called["cmd"] = str(args[0] if args else kwargs.get("args", ""))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    monkeypatch.setattr("modules.self_learning_test_runner.settings.SELF_LEARNING_TEST_TARGET_MAP", "")
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert "tests/test_operator_policy.py" in called["cmd"]
    assert out["details"][0]["task_family"] == "security_ops"


def test_self_learning_test_runner_resolves_playbook_suffix_to_base_family(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_playbook_family"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="")
    sl.set_candidate_status(skill_name, "hold")
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, updated_at)
            VALUES (?, '', 'postcheck_remediation_security_ops_stability', 'open', datetime('now'))
            """,
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()

    called = {"cmd": ""}

    def _fake_run(*args, **kwargs):
        called["cmd"] = str(args[0] if args else kwargs.get("args", ""))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    monkeypatch.setattr("modules.self_learning_test_runner.settings.SELF_LEARNING_TEST_TARGET_MAP", "")
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert "tests/test_operator_policy.py" in called["cmd"]
    assert out["details"][0]["task_family"] == "security_ops"


def test_self_learning_test_runner_maps_incident_response_alias_to_recovery_suite(tmp_path, monkeypatch):
    db = str(tmp_path / "sl.db")
    sl = SelfLearningEngine(sqlite_path=db)
    reg = SkillRegistry(sqlite_path=db)
    skill_name = "selflearn:runner_incident_alias"
    reg.register_skill(skill_name, category="self_learning", source="self_learning", acceptance_status="pending")
    sl.register_candidate(skill_name, confidence=0.9, notes="n", task_family="")
    sl.set_candidate_status(skill_name, "hold")
    conn = sl._get_conn()
    try:
        conn.execute(
            """
            INSERT INTO self_learning_test_jobs (skill_name, task_family, reason, status, updated_at)
            VALUES (?, '', 'postcheck_remediation_incident_response_regression', 'open', datetime('now'))
            """,
            (skill_name,),
        )
        conn.commit()
    finally:
        conn.close()

    called = {"cmd": ""}

    def _fake_run(*args, **kwargs):
        called["cmd"] = str(args[0] if args else kwargs.get("args", ""))
        return SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr("modules.self_learning_test_runner.subprocess.run", _fake_run)
    monkeypatch.setattr("modules.self_learning_test_runner.settings.SELF_LEARNING_TEST_TARGET_MAP", "")
    runner = SelfLearningTestRunner(sqlite_path=db)
    out = runner.run_open_jobs(max_jobs=1, timeout_sec=30)
    assert out["ok"] is True
    assert "tests/test_self_learning_test_runner.py" in called["cmd"]
    assert out["details"][0]["task_family"] == "incident_response"
