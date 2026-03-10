from pathlib import Path

from config.paths import PROJECT_ROOT
from modules.platform_readiness import assess_platform_readiness
from modules.comms_views import render_platform_readiness_summary
from modules.service_session_registry import save_service_sessions


def test_assess_platform_readiness_marks_missing_session(tmp_path, monkeypatch):
    runtime = PROJECT_ROOT / "runtime"
    reports = PROJECT_ROOT / "reports"
    runtime.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    save_service_sessions({})
    results = assess_platform_readiness(["etsy"])
    assert results[0]["service"] == "etsy"
    assert results[0]["blocker"] == "missing_session"


def test_assess_platform_readiness_can_validate_when_session_and_probe_exist(tmp_path):
    runtime = PROJECT_ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    probe = runtime / "etsy_owner_grade_probe.json"
    probe.write_text("{}", encoding="utf-8")
    save_service_sessions(
        {
            "etsy": {
                "storage_exists": True,
                "verified_at": "2026-03-10T00:00:00+00:00",
                "storage_state_path": str(runtime / "etsy_storage_state.json"),
            }
        }
    )
    results = assess_platform_readiness(["etsy"])
    assert results[0]["session_present"] is True
    assert results[0]["probe_present"] is True
    assert results[0]["can_validate_now"] is True


def test_render_platform_readiness_summary_includes_counts():
    text = render_platform_readiness_summary([
        {"service": "etsy", "owner_grade_state": "owner_grade", "can_validate_now": True, "blocker": ""},
        {"service": "printful", "owner_grade_state": "partial", "can_validate_now": False, "blocker": "missing_session"},
    ])
    assert "owner-grade=1" in text
    assert "можно валидировать сейчас=1" in text
    assert "printful: partial | blocker=missing_session" in text
