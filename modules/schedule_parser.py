"""ScheduleParser — parse natural language schedule requests (RU/EN).

Supports:
  - weekly: "каждую субботу в 10 утра", "every Monday 9:00"
  - daily: "каждый день в 10", "daily at 09:30"
  - once: "2026-03-05 10:00", "05.03.2026 10:00"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


WEEKDAYS = {
    # RU
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
    # EN
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass
class ScheduleParseResult:
    ok: bool
    schedule_type: Optional[str] = None  # once|daily|weekly
    time_of_day: Optional[str] = None    # "HH:MM"
    weekday: Optional[int] = None        # 0=Mon
    run_at: Optional[str] = None         # ISO datetime
    action: Optional[str] = None         # e.g., "sales_report"
    title: Optional[str] = None
    needs_clarification: bool = False
    clarification: Optional[str] = None


def _parse_time(text: str) -> Optional[str]:
    """Parse time from text into HH:MM."""
    m = re.search(r"(\\d{1,2})(?::(\\d{2}))?\\s*(утра|вечера|дня|ночи|am|pm)?", text, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or "00")
    suffix = (m.group(3) or "").lower()

    if suffix in ("pm", "вечера") and hour < 12:
        hour += 12
    if suffix in ("am", "утра") and hour == 12:
        hour = 0
    if suffix == "ночи" and hour == 12:
        hour = 0
    if suffix == "дня" and 1 <= hour <= 7:
        hour += 12

    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_weekday(text: str) -> Optional[int]:
    lower = text.lower()
    for name, idx in WEEKDAYS.items():
        if name in lower:
            return idx
    return None


def _extract_once_datetime(text: str, now: datetime) -> Optional[str]:
    # ISO or YYYY-MM-DD HH:MM
    m = re.search(r"(\\d{4})-(\\d{2})-(\\d{2})(?:\\s+(\\d{1,2})(?::(\\d{2}))?)?", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or "09")
        mm = int(m.group(5) or "00")
        dt = datetime(y, mo, d, hh, mm, tzinfo=timezone.utc)
        return dt.isoformat()

    # DD.MM.YYYY
    m = re.search(r"(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})(?:\\s+(\\d{1,2})(?::(\\d{2}))?)?", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or "09")
        mm = int(m.group(5) or "00")
        dt = datetime(y, mo, d, hh, mm, tzinfo=timezone.utc)
        return dt.isoformat()
    return None


def parse_schedule(text: str, now: Optional[datetime] = None) -> ScheduleParseResult:
    now = now or datetime.now(timezone.utc)
    lower = text.lower()

    # Action detection
    action = "reminder"
    if any(w in lower for w in ("отчет по продаж", "отчеты по продаж", "sales report", "отчет продаж", "финансовый отчет", "p&l", "pnl", "финансы")):
        action = "sales_report"
    elif any(w in lower for w in ("отчет по платформ", "platform report", "отчет по площадк", "отчет по каналам")):
        action = "platform_report"
    elif any(w in lower for w in ("контент отчет", "отчет по контент", "content report")):
        action = "content_report"
    elif any(w in lower for w in ("маркетинг отчет", "отчет по маркетинг", "ads report", "отчет по рекламе")):
        action = "ads_report"
    elif any(w in lower for w in ("отчет", "report")):
        action = "report"

    # Once schedule by explicit date
    once_dt = _extract_once_datetime(text, now)
    if once_dt:
        return ScheduleParseResult(
            ok=True,
            schedule_type="once",
            run_at=once_dt,
            action=action,
            title=text.strip()[:200],
        )

    # Daily
    if any(w in lower for w in ("каждый день", "ежедневно", "daily")):
        t = _parse_time(text)
        if not t:
            return ScheduleParseResult(
                ok=False,
                needs_clarification=True,
                clarification="Укажи время. Например: «каждый день в 10:00».",
            )
        return ScheduleParseResult(
            ok=True,
            schedule_type="daily",
            time_of_day=t,
            action=action,
            title=text.strip()[:200],
        )

    # Weekly
    wd = _extract_weekday(text)
    if wd is not None:
        t = _parse_time(text)
        if not t:
            return ScheduleParseResult(
                ok=False,
                needs_clarification=True,
                clarification="Укажи время. Например: «каждую субботу в 10:00».",
            )
        # If "кажд" or "every" assume weekly, else still treat as weekly
        return ScheduleParseResult(
            ok=True,
            schedule_type="weekly",
            weekday=wd,
            time_of_day=t,
            action=action,
            title=text.strip()[:200],
        )

    return ScheduleParseResult(ok=False)
