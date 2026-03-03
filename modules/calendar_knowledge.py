"""CalendarKnowledge — local calendar lookup without LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from config.paths import PROJECT_ROOT


CALENDAR_PATH = PROJECT_ROOT / "docs" / "commerce_calendar.md"

MONTHS_RU = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
MONTHS_EN = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class CalendarEntry:
    date: str          # YYYY-MM-DD or MM-DD
    region: str
    name: str
    notes: str


def _load_entries() -> list[CalendarEntry]:
    if not CALENDAR_PATH.exists():
        return []
    entries: list[CalendarEntry] = []
    for line in CALENDAR_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        date, region, name = parts[0], parts[1], parts[2]
        notes = parts[3] if len(parts) > 3 else ""
        if re.match(r"^\\d{4}-\\d{2}-\\d{2}$", date) or re.match(r"^\\d{2}-\\d{2}$", date):
            entries.append(CalendarEntry(date=date, region=region, name=name, notes=notes))
    return entries


def _parse_date_from_text(text: str) -> Optional[str]:
    text = text.lower()
    # YYYY-MM-DD
    m = re.search(r"(\\d{4})-(\\d{2})-(\\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # DD.MM.YYYY
    m = re.search(r"(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})", text)
    if m:
        d = int(m.group(1))
        mo = int(m.group(2))
        y = int(m.group(3))
        return f\"{y:04d}-{mo:02d}-{d:02d}\"
    # "14 февраля" / "14 february"
    m = re.search(r\"(\\d{1,2})\\s+([a-zа-я]+)\", text)
    if m:
        d = int(m.group(1))
        mon_raw = m.group(2)
        month = None
        for k, v in MONTHS_RU.items():
            if mon_raw.startswith(k):
                month = v
                break
        if month is None:
            for k, v in MONTHS_EN.items():
                if mon_raw.startswith(k):
                    month = v
                    break
        if month:
            return f\"{month:02d}-{d:02d}\"
    return None


def search_calendar(query: str, limit: int = 8) -> list[CalendarEntry]:
    entries = _load_entries()
    if not entries:
        return []

    date = _parse_date_from_text(query)
    q = query.lower()
    results: list[CalendarEntry] = []

    if date:
        # Match exact date first
        for e in entries:
            if e.date == date:
                results.append(e)
        # Also match MM-DD if date is full
        if re.match(r\"^\\d{4}-\\d{2}-\\d{2}$\", date):
            mmdd = date[5:]
            for e in entries:
                if e.date == mmdd:
                    results.append(e)
        return results[:limit]

    # Keyword search by name or region
    for e in entries:
        if e.name.lower() in q or q in e.name.lower():
            results.append(e)
        elif e.region.lower() in q:
            results.append(e)
        else:
            # fallback token overlap
            for token in re.split(r\"\\W+\", q):
                if token and token in e.name.lower():
                    results.append(e)
                    break

    return results[:limit]


def format_calendar_results(results: list[CalendarEntry]) -> str:
    if not results:
        return \"В календаре не нашёл совпадений. Уточни дату или название праздника.\"
    lines = [\"Календарь: найденные даты\"]
    for e in results:
        note = f\" — {e.notes}\" if e.notes else \"\"
        lines.append(f\"  {e.date} | {e.region} | {e.name}{note}\")
    return \"\\n\".join(lines)
