from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AutonomyOverseer:
    def __init__(self, *, stuck_tick_threshold: int = 288):
        self.stuck_tick_threshold = max(12, int(stuck_tick_threshold or 288))

    def inspect(
        self,
        *,
        tick_count: int,
        proposal_store,
        workflow_sessions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        sessions = list(workflow_sessions or [])
        for item in sessions:
            state = str(item.get('state') or '').lower()
            last_tick = int(item.get('last_tick') or item.get('last_activity_tick') or 0)
            if state in {'running', 'waiting_approval'} and last_tick and tick_count - last_tick >= self.stuck_tick_threshold:
                findings.append({
                    'type': 'workflow_stuck',
                    'goal_id': str(item.get('goal_id') or ''),
                    'state': state,
                    'last_tick': last_tick,
                    'age_ticks': tick_count - last_tick,
                })
        try:
            proposals = proposal_store.list_proposals(status='pending', limit=200)
        except Exception:
            proposals = []
        now = datetime.now(timezone.utc)
        for row in proposals:
            created_at = str(row.get('created_at') or '')
            try:
                dt = datetime.fromisoformat(created_at.replace(' ', 'T')) if 'T' in created_at else datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except Exception:
                continue
            age_h = (now - dt).total_seconds() / 3600.0
            if age_h >= 24:
                findings.append({'type': 'stale_proposal', 'proposal_id': str(row.get('proposal_id') or row.get('id') or ''), 'age_hours': round(age_h, 2)})
        return {
            'ok': not findings,
            'finding_count': len(findings),
            'findings': findings,
        }
