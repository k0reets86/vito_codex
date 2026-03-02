"""Weekly governance aggregation across LLM risk, tooling, provider health, and memory retention."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings
from memory.memory_manager import MemoryManager
from modules.llm_evals import LLMEvals
from modules.provider_health import ProviderHealth
from modules.skill_registry import SkillRegistry
from modules.tooling_registry import ToolingRegistry


class GovernanceReporter:
    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        sqlite_path: str | None = None,
    ):
        self.memory = memory_manager or MemoryManager()
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH

    def weekly_report(self, days: int = 7) -> dict[str, Any]:
        llm = LLMEvals(sqlite_path=self.sqlite_path).compute()
        tooling = ToolingRegistry(sqlite_path=self.sqlite_path).build_governance_report(days=days)
        skill_registry = SkillRegistry(sqlite_path=self.sqlite_path)
        skill_audit = skill_registry.audit_summary(limit=10)
        skill_remediation = {"created": 0, "open_total": 0, "items": []}
        if bool(getattr(settings, "WEEKLY_GOVERNANCE_SKILL_REMEDIATE_ENABLED", True)):
            skill_remediation = skill_registry.remediate_high_risk(
                limit=max(1, int(getattr(settings, "WEEKLY_GOVERNANCE_SKILL_REMEDIATE_LIMIT", 20) or 20))
            )
        providers = ProviderHealth().summary(rotation_days_max=int(getattr(settings, "TOOLING_KEY_ROTATION_MAX_DAYS", 90) or 90))
        memory_summary = self.memory.get_memory_policy_summary(days=days)
        memory_drift = self.memory.retention_drift_alerts(days=days)
        remediations: list[str] = []
        remediations.extend(tooling.get("remediations", []) or [])
        remediations.extend(providers.get("remediations", []) or [])
        if float(llm.get("fail_rate", 0.0) or 0.0) >= 0.25:
            remediations.append("Review failing prompts/tools and route unstable tasks to safer model profile.")
        if bool(llm.get("cost_anomaly")):
            remediations.append("Enable economy model profile and audit expensive LLM/tool chains.")
        if (memory_drift or {}).get("alerts"):
            remediations.append("Review memory retention drift alerts and run expired cleanup.")
        if int(skill_audit.get("pending", 0) or 0) > 0:
            remediations.append("Process pending skill acceptance queue and validate required tests.")
        if int(skill_audit.get("high_risk", 0) or 0) > 0 or int(skill_remediation.get("open_total", 0) or 0) > 0:
            remediations.append("Work through open skill remediation tasks (risk/compatibility) with deterministic test gates.")
        dedup: list[str] = []
        seen: set[str] = set()
        for item in remediations:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(text)
        suggestions = self._safe_action_suggestions(
            llm=llm,
            tooling=tooling,
            providers=providers,
            memory_drift=memory_drift,
            skill_audit=skill_audit,
            skill_remediation=skill_remediation,
        )

        status = "ok"
        if providers.get("overall_status") in {"degraded", "warning"}:
            status = "warning"
        if int(skill_audit.get("pending", 0) or 0) > 0 or int(skill_audit.get("high_risk", 0) or 0) > 0:
            status = "warning"
        if dedup:
            status = "warning"
        if float(llm.get("fail_rate", 0.0) or 0.0) >= 0.35 or bool(llm.get("cost_anomaly")):
            status = "critical"

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": int(days),
            "status": status,
            "llm": llm,
            "tooling": tooling,
            "skill_audit": skill_audit,
            "skill_remediation": skill_remediation,
            "providers": providers,
            "memory_summary": memory_summary,
            "memory_drift": memory_drift,
            "remediations": dedup,
            "safe_action_suggestions": suggestions,
        }

    @staticmethod
    def _safe_action_suggestions(
        llm: dict[str, Any],
        tooling: dict[str, Any],
        providers: dict[str, Any],
        memory_drift: dict[str, Any],
        skill_audit: dict[str, Any] | None = None,
        skill_remediation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        fail_rate = float(llm.get("fail_rate", 0.0) or 0.0)
        key_alerts = ((tooling.get("key_rotation_health", {}) or {}).get("alerts", []) or [])
        skill_queue = int((skill_remediation or {}).get("open_total", 0) or 0) + int((skill_audit or {}).get("pending", 0) or 0)
        if bool(llm.get("cost_anomaly")) or fail_rate >= 0.30:
            sev = 5 + (2 if bool(llm.get("cost_anomaly")) else 0) + int(min(3.0, fail_rate * 5.0))
            suggestions.append({
                "action": "apply_profile_economy",
                "priority": 1,
                "score": sev,
                "reason": "LLM cost anomaly/high fail-rate",
            })
        if fail_rate >= 0.25:
            sev = 4 + int(min(4.0, fail_rate * 6.0))
            suggestions.append({
                "action": "enable_guardrails_block",
                "priority": 2,
                "score": sev,
                "reason": "High fail-rate indicates potential unsafe prompts",
            })
        if key_alerts:
            sev = 4 + min(4, len(key_alerts))
            suggestions.append({
                "action": "disable_tooling_live",
                "priority": 2,
                "score": sev,
                "reason": "Tooling key/integrity alerts detected",
            })
            if len(key_alerts) >= 3:
                suggestions.append({
                    "action": "disable_discovery_intake",
                    "priority": 2,
                    "score": max(4, min(8, len(key_alerts) + 2)),
                    "reason": "Frequent tooling integrity alerts suggest intake should be paused",
                })
        if providers.get("overall_status") in {"degraded", "warning"} or bool((memory_drift or {}).get("alerts")):
            suggestions.append({
                "action": "set_notify_minimal",
                "priority": 3,
                "score": 2,
                "reason": "Reduce noise while remediation is in progress",
            })
        if bool(llm.get("cost_anomaly")) and fail_rate >= 0.35:
            suggestions.append({
                "action": "enable_revenue_dry_run",
                "priority": 2,
                "score": 6,
                "reason": "Cost anomaly with high fail-rate: keep revenue loops in dry-run until stabilized",
            })
        if bool(llm.get("cost_anomaly")) and fail_rate >= 0.45 and key_alerts:
            suggestions.append({
                "action": "disable_revenue_engine",
                "priority": 1,
                "score": 10,
                "reason": "Critical combined risk (cost anomaly + very high fail-rate + tooling alerts)",
            })
        if fail_rate >= 0.40:
            suggestions.append({
                "action": "tighten_self_healer_budget",
                "priority": 2,
                "score": 6 + int(min(3.0, fail_rate * 4.0)),
                "reason": "High fail-rate: tighten autonomous self-heal change budget until stability recovers",
            })
        if skill_queue > 0:
            suggestions.append({
                "action": "set_notify_minimal",
                "priority": 3,
                "score": min(5, 1 + skill_queue),
                "reason": "Skill acceptance/remediation queue is active",
            })
        if skill_queue >= 3:
            suggestions.append({
                "action": "pause_self_learning_autopromote",
                "priority": 2,
                "score": min(8, 4 + skill_queue),
                "reason": "Large skill remediation queue: pause auto-promote to reduce unstable skill drift",
            })
        # De-duplicate by action and keep highest severity.
        by_action: dict[str, dict[str, Any]] = {}
        for item in suggestions:
            act = str(item.get("action") or "")
            if not act:
                continue
            prev = by_action.get(act)
            if prev is None:
                by_action[act] = item
                continue
            prev_score = float(prev.get("score", 0) or 0)
            cur_score = float(item.get("score", 0) or 0)
            if cur_score > prev_score:
                by_action[act] = item
                continue
            if cur_score == prev_score and int(item.get("priority", 9)) < int(prev.get("priority", 9)):
                by_action[act] = item
        return sorted(
            by_action.values(),
            key=lambda x: (-float(x.get("score", 0) or 0), int(x.get("priority", 9)), str(x.get("action", ""))),
        )

    @staticmethod
    def to_markdown(report: dict[str, Any]) -> str:
        llm = report.get("llm", {}) if isinstance(report, dict) else {}
        tooling = report.get("tooling", {}) if isinstance(report, dict) else {}
        skill_audit = report.get("skill_audit", {}) if isinstance(report, dict) else {}
        skill_remediation = report.get("skill_remediation", {}) if isinstance(report, dict) else {}
        providers = report.get("providers", {}) if isinstance(report, dict) else {}
        mem = report.get("memory_summary", {}) if isinstance(report, dict) else {}
        drift = report.get("memory_drift", {}) if isinstance(report, dict) else {}
        rem = report.get("remediations", []) if isinstance(report, dict) else []
        suggestions = report.get("safe_action_suggestions", []) if isinstance(report, dict) else []
        lines = [
            f"## Weekly Governance Report ({report.get('generated_at', '')})",
            "",
            f"- Status: {report.get('status', 'unknown')}",
            f"- Window: {report.get('window_days', 7)} days",
            f"- LLM score: {llm.get('score', 'n/a')} | fail_rate: {llm.get('fail_rate', 'n/a')} | anomaly: {int(bool(llm.get('cost_anomaly')))}",
            f"- Tooling pending rotations: {tooling.get('pending_contract_rotations', 0)} | stage changes: {tooling.get('pending_stage_changes', 0)} | key rotations: {tooling.get('pending_key_rotations', 0)}",
            f"- Skills: total={skill_audit.get('total', 0)} | pending={skill_audit.get('pending', 0)} | high_risk={skill_audit.get('high_risk', 0)} | remediation_open={skill_remediation.get('open_total', 0)}",
            f"- Provider status: {providers.get('overall_status', 'unknown')} (missing={providers.get('missing_provider_count', 0)}, stale={providers.get('stale_provider_count', 0)})",
            f"- Memory quality: {mem.get('quality_score', 0.0)} | save_ratio: {mem.get('save_ratio', 0.0)} | drift_alerts: {len((drift or {}).get('alerts', []) or [])}",
            "",
            "### Remediations",
        ]
        if rem:
            lines.extend([f"- {x}" for x in rem[:12]])
        else:
            lines.append("- No critical remediation required.")
        lines.append("")
        lines.append("### Safe Actions")
        if suggestions:
            for s in suggestions[:8]:
                lines.append(f"- {s.get('action')} (p{s.get('priority')}): {s.get('reason')}")
        else:
            lines.append("- No automatic safe action suggested.")
        return "\n".join(lines)

    def persist_markdown(self, path: Path, report: dict[str, Any]) -> Path:
        content = "\n" + self.to_markdown(report) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(content)
        return path
