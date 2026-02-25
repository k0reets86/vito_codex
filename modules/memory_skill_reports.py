from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from memory.memory_manager import MemoryManager
from modules.skill_registry import SkillRegistry


class MemorySkillReporter:
    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.memory = memory_manager or MemoryManager()
        self.registry = skill_registry or SkillRegistry()

    def weekly_retention_report(self, days: int = 7) -> dict[str, Any]:
        summary = self.memory.get_memory_policy_summary(days=days)
        drift = self.memory.retention_drift_alerts(days=days)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": days,
            "summary": summary,
            "alerts": drift.get("alerts", []),
        }

    def per_skill_quality(self, limit: int = 12) -> list[dict[str, Any]]:
        blocks = self.memory.memory_blocks.blocks_by_type("skill", limit=limit * 3)
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for block in blocks:
            metadata = self._parse_metadata(block.get("metadata_json", "{}"))
            skill_name = metadata.get("skill_name") or str(block.get("doc_id", "")).replace("skill_block_", "")
            if not skill_name:
                continue
            if skill_name in seen:
                continue
            seen.add(skill_name)
            success_rate = float(metadata.get("success_rate", block.get("importance", 0.0) or 0.0))
            registry_entry = self.registry.get_skill(skill_name) or {}
            results.append({
                "skill_name": skill_name,
                "success_rate": round(success_rate, 3),
                "importance": float(block.get("importance") or 0.0),
                "priority": float(block.get("priority") or 0.0),
                "stage": block.get("stage", "short"),
                "updated_at": block.get("updated_at") or "",
                "tests_coverage": registry_entry.get("tests_coverage"),
                "risk_score": registry_entry.get("risk_score"),
                "acceptance": registry_entry.get("acceptance_status") or registry_entry.get("status"),
            })
            if len(results) >= limit:
                break
        return results

    def generate_markdown_report(self, days: int = 7, per_skill_limit: int = 8) -> str:
        report = self.weekly_retention_report(days=days)
        skills = self.per_skill_quality(limit=per_skill_limit)
        summary = report["summary"]
        lines: list[str] = [
            f"## Weekly Memory Report ({report['generated_at']})",
            "",
            f"- Window: {report['window_days']} days",
            f"- Total memory events: {summary.get('total_events', 0)}",
            f"- Saved: {summary.get('saved', 0)}",
            f"- Forgotten: {summary.get('forgotten', 0)}",
            f"- Quality score: {summary.get('quality_score', 0.0):.3f}",
            f"- Save ratio: {summary.get('save_ratio', 0.0):.3f}",
            "",
            "### Retention breakdown",
        ]
        for row in summary.get("saved_by_retention", []) or []:
            if not isinstance(row, dict) or not row:
                continue
            key, value = next(iter(row.items()))
            lines.append(f"- {key}: {value} captures")
        lines.append("")
        alerts = report.get("alerts", [])
        if alerts:
            lines.append("### Alerts")
            for alert in alerts:
                lines.append(f"- **{alert.get('code', 'alert')}**: {alert.get('message', '')} ({alert.get('severity', 'info')})")
            lines.append("")
        if per_skill_limit:
            lines.append("### Skill Memory Quality")
            headers = "| Skill | Success Rate | Tests Coverage | Risk Score | Stage | Updated | Acceptance |"
            dividers = "| --- | --- | --- | --- | --- | --- | --- |"
            lines.extend([headers, dividers])
            for skill in skills:
                lines.append(
                    f"| {skill['skill_name']} | {skill['success_rate']:.3f} | "
                    f"{skill.get('tests_coverage', 'n/a')} | {skill.get('risk_score', 'n/a')} | "
                    f"{skill['stage']} | {skill['updated_at']} | {skill.get('acceptance', 'unknown')} |"
                )
        return "\n".join(lines)

    def persist_markdown(self, path: Path, days: int = 7, per_skill_limit: int = 8) -> Path:
        report = self.generate_markdown_report(days=days, per_skill_limit=per_skill_limit)
        content = f"\n{report}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(content)
        return path

    @staticmethod
    def _parse_metadata(payload: str) -> dict[str, Any]:
        try:
            return json.loads(payload or "{}")
        except Exception:
            return {}
