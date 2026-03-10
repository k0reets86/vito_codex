from modules.platform_circuit_breaker import PlatformCircuitBreaker


def test_platform_circuit_breaker_opens_after_threshold(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "SQLITE_PATH", str(tmp_path / "vito.db"))
    monkeypatch.setattr(settings, "PLATFORM_CIRCUIT_BREAKER_FAIL_THRESHOLD", 2)
    monkeypatch.setattr(settings, "PLATFORM_CIRCUIT_BREAKER_COOLDOWN_SEC", 120)
    monkeypatch.setattr(settings, "PLATFORM_CIRCUIT_BREAKER_LONG_COOLDOWN_SEC", 600)

    br = PlatformCircuitBreaker(sqlite_path=str(tmp_path / "vito.db"))
    ok, _ = br.allow("etsy")
    assert ok is True
    br.record_failure("etsy", "timeout")
    ok, _ = br.allow("etsy")
    assert ok is True
    st = br.record_failure("etsy", "timeout")
    assert st.is_open is True
    ok, reason = br.allow("etsy")
    assert ok is False
    assert "platform_circuit_open_until:" in reason


def test_platform_circuit_breaker_resets_on_success(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "SQLITE_PATH", str(tmp_path / "vito.db"))
    monkeypatch.setattr(settings, "PLATFORM_CIRCUIT_BREAKER_FAIL_THRESHOLD", 1)
    monkeypatch.setattr(settings, "PLATFORM_CIRCUIT_BREAKER_COOLDOWN_SEC", 120)
    br = PlatformCircuitBreaker(sqlite_path=str(tmp_path / "vito.db"))
    br.record_failure("gumroad", "daily_limit")
    assert br.state("gumroad").is_open is True
    br.record_success("gumroad")
    st = br.state("gumroad")
    assert st.is_open is False
    assert st.consecutive_failures == 0

