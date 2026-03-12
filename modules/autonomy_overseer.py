from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json

from llm_router import TaskType


class AutonomyOverseer:
    def __init__(self, *, stuck_tick_threshold: int = 288, llm_router: Any | None = None):
        self.stuck_tick_threshold = max(1, int(stuck_tick_threshold or 288))
        self.llm_router = llm_router

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
            'diagnostics': self._heuristic_diagnostics(findings),
        }

    async def inspect_async(
        self,
        *,
        tick_count: int,
        proposal_store,
        workflow_sessions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        report = self.inspect(
            tick_count=tick_count,
            proposal_store=proposal_store,
            workflow_sessions=workflow_sessions,
        )
        if not self.llm_router or report.get("ok"):
            return report
        diagnostics = await self._llm_diagnostics(report.get("findings") or [])
        if diagnostics:
            report = dict(report)
            report["diagnostics"] = diagnostics
        return report

    async def execute_actions(self, findings, goal_engine, comms, proposal_store=None) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for f in list(findings or []):
            ftype = str(f.get("type") or "").strip()
            if ftype == "workflow_stuck":
                goal_id = str(f.get("goal_id") or "").strip()
                try:
                    if goal_id and hasattr(goal_engine, "reset_goal"):
                        goal_engine.reset_goal(goal_id)
                        actions.append({"type": "goal_reset", "goal_id": goal_id})
                    elif goal_id and hasattr(goal_engine, "fail_goal"):
                        goal_engine.fail_goal(goal_id, "overseer_timeout")
                        actions.append({"type": "goal_failed", "goal_id": goal_id})
                    elif comms:
                        await comms.send_message(f"OVERSEER: stuck goal {goal_id} needs manual attention", level="warning")
                except Exception as e:
                    if comms:
                        await comms.send_message(f"OVERSEER: stuck goal {goal_id} reset failed: {e}", level="warning")
            elif ftype == "stale_proposal":
                proposal_id = str(f.get("proposal_id") or "").strip()
                if not proposal_id or proposal_store is None:
                    continue
                try:
                    if hasattr(proposal_store, "update_status"):
                        proposal_store.update_status(proposal_id, "archived")
                        actions.append({"type": "proposal_archived", "proposal_id": proposal_id})
                except Exception:
                    continue
        return {"actions_taken": actions, "count": len(actions)}

    def _heuristic_diagnostics(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        if not findings:
            return {"summary": "no_findings", "recommended_actions": [], "risk_level": "low"}
        types = [str(f.get("type") or "issue") for f in findings]
        risk_level = "medium" if len(types) < 3 else "high"
        return {
            "summary": ", ".join(types[:4]),
            "recommended_actions": [self._action_hint(t) for t in types[:3]],
            "risk_level": risk_level,
        }

    async def _llm_diagnostics(self, findings: list[dict[str, Any]]) -> dict[str, Any] | None:
        prompt = (
            "Проанализируй stuck-cases автономного контура и верни JSON: "
            '{"summary": "...", "recommended_actions": ["..."], "risk_level": "low|medium|high"}.\n'
            f"Findings: {json.dumps(findings, ensure_ascii=False)}"
        )
        try:
            raw = await self.llm_router.call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=700)
        except Exception:
            return None
        try:
            cleaned = str(raw or "").strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
            if isinstance(data, dict):
                data.setdefault("recommended_actions", [])
                data.setdefault("summary", "diagnostics_unavailable")
                data.setdefault("risk_level", "medium")
                return data
        except Exception:
            return None
        return None

    def _action_hint(self, finding_type: str) -> str:
        if finding_type == "workflow_stuck":
            return "reset_or_fail_stuck_goal"
        if finding_type == "stale_proposal":
            return "archive_or_reprioritize_stale_proposal"
        return "manual_review"
