from modules.human_browser import HumanBrowser, profile_dir_for_service


def test_profile_dir_for_service_is_stable():
    path = profile_dir_for_service("etsy")
    assert path.endswith("runtime/browser_profiles/etsy")


def test_build_context_spec_contains_runtime_flags():
    browser = HumanBrowser()
    spec = browser.build_context_spec(
        {
            "service": "etsy",
            "storage_state_path": "/tmp/etsy.json",
            "persistent_profile_dir": "/tmp/profiles/etsy",
            "screenshot_first_default": True,
            "anti_bot_humanize": True,
            "headless_preferred": True,
            "llm_navigation_allowed": True,
        }
    )
    assert spec.service == "etsy"
    assert spec.storage_state_path == "/tmp/etsy.json"
    assert spec.persistent_profile_dir == "/tmp/profiles/etsy"
    assert spec.screenshot_first_default is True
    assert spec.llm_navigation_allowed is True
