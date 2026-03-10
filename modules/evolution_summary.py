from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.evolution_archive import EvolutionArchive
from modules.evolution_audit import EvolutionAuditTrail
from modules.evolution_events import EvolutionEventStore


class EvolutionSummaryBuilder:
    def __init__(self, *, sqlite_path: str | None = None):
        self.events = EvolutionEventStore(sqlite_path=sqlite_path)
        self.audit = EvolutionAuditTrail(sqlite_path=sqlite_path)
        self.archive = EvolutionArchive(sqlite_path=sqlite_path)

    def build_owner_summary(self, days: int = 7) -> dict[str, Any]:
        event_summary = self.events.summary(days=days)
        latest_events = self.events.list_events(limit=10)
        latest_audit = self.audit.list_entries(limit=10)
        latest_archive = self.archive.recent(limit=10)
        return {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'days': days,
            'events': event_summary,
            'latest_events': latest_events,
            'latest_audit': latest_audit,
            'latest_archive': latest_archive,
        }

    def render_markdown(self, payload: dict[str, Any]) -> str:
        lines = [
            '# VITO Evolution Owner Summary',
            '',
            f"- generated_at: {payload.get('generated_at', '')}",
            f"- days: {payload.get('days', 0)}",
            f"- events_total: {payload.get('events', {}).get('total', 0)}",
            '',
            '## Event Statuses',
        ]
        statuses = dict(payload.get('events', {}).get('statuses', {}) or {})
        if statuses:
            for key, value in sorted(statuses.items()):
                lines.append(f"- {key}: {value}")
        else:
            lines.append('- none')
        lines.append('')
        lines.append('## Latest Evolution Events')
        latest_events = list(payload.get('latest_events') or [])
        if latest_events:
            for item in latest_events[:10]:
                lines.append(f"- [{item.get('status','')}] {item.get('event_type','')}: {item.get('title','')}")
        else:
            lines.append('- none')
        lines.append('')
        lines.append('## Latest Apply Audit')
        latest_audit = list(payload.get('latest_audit') or [])
        if latest_audit:
            for item in latest_audit[:10]:
                lines.append(f"- [{ 'ok' if item.get('signature_ok') else 'bad' }] {item.get('event_type','')}: success={bool(item.get('success'))}")
        else:
            lines.append('- none')
        lines.append('')
        lines.append('## Latest Evolution Archive')
        latest_archive = list(payload.get('latest_archive') or [])
        if latest_archive:
            for item in latest_archive[:10]:
                lines.append(f"- [{ 'ok' if item.get('success') else 'fail' }] {item.get('archive_type','')}: {item.get('title','')}")
        else:
            lines.append('- none')
        lines.append('')
        return '\n'.join(lines)

    def persist_markdown(self, path: str | Path, payload: dict[str, Any]) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render_markdown(payload), encoding='utf-8')
        return out
