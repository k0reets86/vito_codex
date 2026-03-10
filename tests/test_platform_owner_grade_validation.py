from pathlib import Path

from scripts.platform_owner_grade_validation import run_validation


def test_platform_owner_grade_validation_has_summary():
    report = run_validation()
    assert report["summary"]["total"] >= 1
    check = report["checks"][0]
    assert check["platform"] == "kofi"
    assert "repeatability_profile" in check["result"]
    assert Path(check["source"]).name == "result.json"
