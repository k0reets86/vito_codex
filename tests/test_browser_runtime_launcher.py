from modules.browser_runtime_launcher import chromium_launch_args, resolve_browser_engine


def test_chromium_launch_args_include_runtime_hardening():
    args = chromium_launch_args()
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--renderer-process-limit=1" in args


def test_resolve_browser_engine_returns_supported_engine():
    engine, factory = resolve_browser_engine()
    assert engine in {"playwright", "patchright"}
    assert callable(factory)
