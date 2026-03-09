from modules.browser_runtime_policy import (
    build_auth_interrupt_output,
    browser_capability_map,
    get_browser_runtime_profile,
    get_profile_completion_runbook,
    storage_state_path_for_service,
)


def test_browser_capability_map_contains_core_services():
    data = browser_capability_map()
    assert "etsy" in data
    assert "amazon_kdp" in data
    assert data["etsy"]["screenshot_first"] is True


def test_storage_state_path_for_service_resolves_runtime_path():
    path = storage_state_path_for_service("etsy")
    assert path is not None
    assert str(path).endswith("runtime/etsy_storage_state.json")


def test_get_browser_runtime_profile_contains_auth_prompt():
    profile = get_browser_runtime_profile("amazon_kdp")
    assert profile["otp_supported"] is True
    assert "6 цифр" in profile["otp_prompt"]


def test_build_auth_interrupt_output_for_kdp_otp():
    out = build_auth_interrupt_output(
        "amazon_kdp",
        url="https://www.amazon.com/ap/mfa",
        body_text="Two-Step Verification",
        screenshot_path="/tmp/test.png",
    )
    assert out is not None
    assert out["auth_interrupt"]["type"] == "otp_required"
    assert out["needs_manual_auth"] is True
    assert out["screenshot"] == "/tmp/test.png"


def test_profile_completion_runbook_contains_route():
    runbook = get_profile_completion_runbook("pinterest")
    assert runbook["requires_profile_completion"] is True
    assert "settings/profile" in runbook["route"]
