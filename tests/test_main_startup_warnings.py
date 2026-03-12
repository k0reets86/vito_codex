from modules.startup_warnings import emit_startup_warnings


def test_emit_startup_warnings(monkeypatch):
    events = []

    class _Logger:
        def warning(self, message, extra=None):
            events.append((message, dict(extra or {})))

    monkeypatch.setattr("modules.startup_warnings.settings.DATABASE_URL", "", raising=False)
    monkeypatch.setattr("modules.startup_warnings.settings.MEM0_ENABLED", False, raising=False)
    monkeypatch.setattr("modules.startup_warnings.settings.MEM0_API_KEY", "secret", raising=False)

    emit_startup_warnings(_Logger())

    names = {item[1].get("event") for item in events}
    assert "startup_pgvector_disabled" in names
    assert "startup_mem0_disabled_with_key" in names
