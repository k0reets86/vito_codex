from pathlib import Path

from config.paths import PROJECT_ROOT
from modules.platform_readiness import assess_platform_readiness
from modules.comms_views import render_platform_readiness_summary
from modules.status_snapshot import build_status_snapshot, render_status_snapshot
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
    assert results[0]["recommended_action"] == "reauth:etsy"


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
    assert results[0]["recommended_action"] == "owner_grade_validate:etsy"


def test_render_platform_readiness_summary_includes_counts():
    text = render_platform_readiness_summary([
        {"service": "etsy", "owner_grade_state": "owner_grade", "can_validate_now": True, "blocker": "", "recommended_action": ""},
        {"service": "printful", "owner_grade_state": "partial", "can_validate_now": False, "blocker": "missing_session", "recommended_action": "reauth:printful"},
    ])
    assert "owner-grade=1" in text
    assert "можно валидировать сейчас=1" in text
    assert "printful: partial | blocker=missing_session | next=reauth:printful" in text


def test_status_snapshot_renders_platform_readiness():
    class DummyLoop:
        def get_status(self):
            return {
                "running": True,
                "tick_count": 7,
                "daily_spend": 1.5,
                "platform_readiness": {
                    "total": 3,
                    "owner_grade": 1,
                    "can_validate_now": 1,
                    "blocked": 2,
                    "next_steps": ["reauth:etsy", "run_probe:printful"],
                },
            }

    snap = build_status_snapshot(decision_loop=DummyLoop())
    text = render_status_snapshot(snap)
    assert "Платформы: 3 всего; owner-grade 1; готовы к валидации 1; блокеры 2" in text
    assert "reauth:etsy" in text
