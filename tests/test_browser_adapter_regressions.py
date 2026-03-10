from scripts.browser_adapter_regressions import run


def test_browser_adapter_regressions_pass():
    result = run()
    assert result["summary"]["failed"] == 0
    assert result["summary"]["passed"] == 3
