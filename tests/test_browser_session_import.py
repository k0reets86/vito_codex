from scripts.browser_session_import import _default_storage_path, SERVICE_VERIFY_URLS


def test_browser_session_import_supports_extended_services():
    for svc in ("threads", "instagram", "facebook", "pinterest", "youtube", "linkedin", "tiktok"):
        assert svc in SERVICE_VERIFY_URLS
        p = _default_storage_path(svc)
        assert "runtime/" in p

