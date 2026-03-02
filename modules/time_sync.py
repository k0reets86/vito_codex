"""TimeSync — periodic time verification against external service."""

import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from modules.network_utils import network_available, network_status

from config.logger import get_logger
from config.settings import settings

logger = get_logger("time_sync", agent="time_sync")


class TimeSync:
    def __init__(self, comms=None):
        self.comms = comms
        self.last_check_ts: float = 0.0
        self.last_offset_sec: Optional[float] = None
        self.last_source: Optional[str] = None

    def _fetch_utc(self) -> Optional[datetime]:
        net = network_status(["worldtimeapi.org", "timeapi.io"])
        if not net["ok"]:
            return None
        urls = []
        if getattr(settings, "TIME_SYNC_URLS", ""):
            urls.extend([u.strip() for u in settings.TIME_SYNC_URLS.split(",") if u.strip()])
        if settings.TIME_SYNC_URL:
            urls.append(settings.TIME_SYNC_URL)
        # Fallbacks (public time endpoints)
        urls.extend([
            "https://worldtimeapi.org/api/ip",
            "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
            "https://timeapi.io/api/Time/current/zone?timeZone=Etc/UTC",
        ])
        seen = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    # worldtimeapi: utc_datetime or unixtime
                    if "utc_datetime" in data:
                        self.last_source = url
                        return datetime.fromisoformat(data["utc_datetime"].replace("Z", "+00:00"))
                    if "unixtime" in data:
                        self.last_source = url
                        return datetime.fromtimestamp(int(data["unixtime"]), tz=timezone.utc)
                    # timeapi.io: dateTime or time
                    if "dateTime" in data:
                        self.last_source = url
                        return datetime.fromisoformat(data["dateTime"].replace("Z", "+00:00"))
            except Exception:
                continue
        return None

    async def check(self, reason: str = "scheduled") -> dict:
        """Check time skew vs external service."""
        now = datetime.now(timezone.utc)
        external = self._fetch_utc()
        if not external:
            logger.warning("Time sync failed: no external time", extra={"event": "time_sync_failed"})
            return {"ok": False, "reason": "external_unavailable"}

        offset = (now - external).total_seconds()
        self.last_offset_sec = offset
        self.last_check_ts = time.time()

        max_skew = settings.TIME_SYNC_MAX_SKEW_SEC
        if abs(offset) > max_skew:
            msg = (
                f"Time skew detected ({offset:.2f}s). "
                f"Local: {now.isoformat()} vs External: {external.isoformat()}."
            )
            logger.warning(msg, extra={"event": "time_skew", "context": {"offset_sec": offset, "reason": reason}})
            if self.comms:
                scheduled_reason = str(reason or "").lower() in {"scheduled", "daily", "weekly"}
                if (not scheduled_reason) or settings.TELEGRAM_CRON_ENABLED:
                    await self.comms.send_message(f"⚠️ {msg}", level="critical")
            return {"ok": False, "offset_sec": offset}

        logger.info("Time sync OK", extra={"event": "time_sync_ok", "context": {"offset_sec": offset, "reason": reason}})
        return {"ok": True, "offset_sec": offset}
