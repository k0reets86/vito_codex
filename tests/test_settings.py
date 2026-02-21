"""Тесты config/settings.py."""

import os
from unittest.mock import patch


def test_settings_loads_defaults():
    from config.settings import Settings
    s = Settings()
    assert isinstance(s.DAILY_LIMIT_USD, float)
    assert isinstance(s.OPERATION_NOTIFY_USD, float)
    assert isinstance(s.OPERATION_APPROVE_USD, float)


def test_settings_financial_limits():
    from config.settings import settings
    assert settings.DAILY_LIMIT_USD > 0
    assert settings.OPERATION_NOTIFY_USD > settings.DAILY_LIMIT_USD
    assert settings.OPERATION_APPROVE_USD > settings.OPERATION_NOTIFY_USD


def test_settings_paths():
    from config.settings import settings
    assert "chroma_db" in settings.CHROMA_PATH
    assert settings.SQLITE_PATH.endswith(".db")
