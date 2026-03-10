from scripts.browser_owner_grade_summary import run_summary


def test_browser_owner_grade_summary_pass():
    result = run_summary()
    assert result["summary"]["failed"] == 0
    assert result["summary"]["owner_grade_ok"] == 3
