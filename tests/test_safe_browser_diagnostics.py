from scripts.safe_browser_diagnostics import run_diagnostics


def test_safe_browser_diagnostics_returns_service_profiles():
    result = run_diagnostics(["etsy", "gumroad"])
    assert result["ok"] is True
    assert "etsy" in result["services"]
    assert "gumroad" in result["services"]
    assert result["services"]["etsy"]["persistent_profile_dir"]
