from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import settings
from modules.time_sync import TimeSync

@pytest.mark.asyncio
async def test_time_sync_suppresses_scheduled_alert_when_cron_disabled(monkeypatch):
    comms = MagicMock()
    comms.send_message = AsyncMock(return_value=True)
    ts = TimeSync(comms=comms)
    monkeypatch.setattr(ts, "_fetch_utc", lambda: datetime.now(timezone.utc) - timedelta(seconds=120))
    monkeypatch.setattr(settings, "TIME_SYNC_MAX_SKEW_SEC", 5)
    monkeypatch.setattr(settings, "TELEGRAM_CRON_ENABLED", False)

    out = await ts.check(reason="daily")
    assert out["ok"] is False
    comms.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_time_sync_sends_alert_for_manual_reason_even_when_cron_disabled(monkeypatch):
    comms = MagicMock()
    comms.send_message = AsyncMock(return_value=True)
    ts = TimeSync(comms=comms)
    monkeypatch.setattr(ts, "_fetch_utc", lambda: datetime.now(timezone.utc) - timedelta(seconds=120))
    monkeypatch.setattr(settings, "TIME_SYNC_MAX_SKEW_SEC", 5)
    monkeypatch.setattr(settings, "TELEGRAM_CRON_ENABLED", False)

    out = await ts.check(reason="manual")
    assert out["ok"] is False
    comms.send_message.assert_called_once()
