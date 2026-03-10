from pathlib import Path

import pytest

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


def test_has_persistent_profile_data_false_for_empty_dir(tmp_path):
    d = tmp_path / "profiles" / "etsy"
    d.mkdir(parents=True)
    browser = HumanBrowser()
    assert browser.has_persistent_profile_data({"service": "etsy", "persistent_profile_dir": str(d)}) is False


def test_has_persistent_profile_data_true_for_non_empty_dir(tmp_path):
    d = tmp_path / "profiles" / "etsy"
    d.mkdir(parents=True)
    (d / "Cookies").write_text("x", encoding="utf-8")
    browser = HumanBrowser()
    assert browser.has_persistent_profile_data({"service": "etsy", "persistent_profile_dir": str(d)}) is True


class _FakeContext:
    pass


class _FakeBrowser:
    def __init__(self):
        self.new_context_calls = []

    async def new_context(self, **kwargs):
        self.new_context_calls.append(kwargs)
        return _FakeContext()


class _FakeBrowserType:
    def __init__(self):
        self.launch_calls = []
        self.persistent_calls = []
        self.browser = _FakeBrowser()
        self.persistent_context = _FakeContext()

    async def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser

    async def launch_persistent_context(self, **kwargs):
        self.persistent_calls.append(kwargs)
        return self.persistent_context


@pytest.mark.asyncio
async def test_launch_managed_context_prefers_storage_state(tmp_path):
    storage = tmp_path / "etsy.json"
    storage.write_text("{}", encoding="utf-8")
    profile_dir = tmp_path / "profiles" / "etsy"
    browser = HumanBrowser()
    browser_type = _FakeBrowserType()

    launched_browser, context, mode = await browser.launch_managed_context(
        browser_type,
        profile={
            "service": "etsy",
            "storage_state_path": str(storage),
            "persistent_profile_dir": str(profile_dir),
        },
        headless=True,
        launch_args=["--no-sandbox"],
        user_agent="ua",
        locale="en-US",
        timezone_id="UTC",
    )

    assert mode == "storage_state"
    assert launched_browser is browser_type.browser
    assert isinstance(context, _FakeContext)
    assert len(browser_type.launch_calls) == 1
    assert browser_type.browser.new_context_calls[0]["storage_state"] == str(storage)
    assert browser_type.persistent_calls == []


@pytest.mark.asyncio
async def test_launch_managed_context_uses_persistent_profile_when_available(tmp_path):
    profile_dir = tmp_path / "profiles" / "etsy"
    profile_dir.mkdir(parents=True)
    (profile_dir / "Cookies").write_text("x", encoding="utf-8")
    browser = HumanBrowser()
    browser_type = _FakeBrowserType()

    launched_browser, context, mode = await browser.launch_managed_context(
        browser_type,
        profile={
            "service": "etsy",
            "storage_state_path": str(tmp_path / "missing.json"),
            "persistent_profile_dir": str(profile_dir),
        },
        headless=False,
        launch_args=["--flag"],
        user_agent="ua",
        locale="en-US",
        timezone_id="UTC",
    )

    assert mode == "persistent_profile"
    assert launched_browser is None
    assert context is browser_type.persistent_context
    assert len(browser_type.persistent_calls) == 1
    assert browser_type.persistent_calls[0]["user_data_dir"] == str(profile_dir)
    assert browser_type.launch_calls == []


@pytest.mark.asyncio
async def test_launch_managed_context_falls_back_to_fresh_context(tmp_path):
    profile_dir = tmp_path / "profiles" / "etsy"
    browser = HumanBrowser()
    browser_type = _FakeBrowserType()

    launched_browser, context, mode = await browser.launch_managed_context(
        browser_type,
        profile={
            "service": "etsy",
            "storage_state_path": str(tmp_path / "missing.json"),
            "persistent_profile_dir": str(profile_dir),
        },
        headless=True,
        launch_args=[],
        user_agent="ua",
        locale="en-US",
        timezone_id="UTC",
    )

    assert mode == "fresh"
    assert launched_browser is browser_type.browser
    assert isinstance(context, _FakeContext)
    assert len(browser_type.launch_calls) == 1
    assert browser_type.browser.new_context_calls[0]["user_agent"] == "ua"
    assert browser_type.persistent_calls == []
