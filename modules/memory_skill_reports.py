from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from config.settings import settings
from memory.memory_manager import MemoryManager
from modules.skill_registry import SkillRegistry


class MemorySkillReporter:
    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
        sqlite_path: str | None = None,
    ):
        self.memory = memory_manager or MemoryManager()
        self.registry = skill_registry or SkillRegistry()
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH

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
        learning_map = self._self_learning_map(
            skill_names=[
                (self._parse_metadata(b.get("metadata_json", "{}")).get("skill_name") or str(b.get("doc_id", "")).replace("skill_block_", ""))
                for b in blocks
            ],
            window_days=45,
        )
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
            learning = learning_map.get(skill_name, {})
            promotion_rate = float(learning.get("promotion_rate") or 0.0)
            flaky_rate = float(learning.get("flaky_rate") or 0.0)
            learning_health = max(0.0, min(1.0, (0.55 * success_rate) + (0.35 * promotion_rate) + (0.10 * (1.0 - flaky_rate))))
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
                "learning_health": round(learning_health, 3),
                "promotion_rate_45d": round(promotion_rate, 3),
                "flaky_rate_45d": round(flaky_rate, 3),
                "outcomes_weight_45d": round(float(learning.get("outcomes_weight") or 0.0), 3),
                "test_runs_45d": int(learning.get("test_runs") or 0),
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
            headers = "| Skill | Success Rate | Learning Health | Promote 45d | Flaky 45d | Tests Coverage | Risk Score | Stage | Updated | Acceptance |"
            dividers = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
            lines.extend([headers, dividers])
            for skill in skills:
                lines.append(
                    f"| {skill['skill_name']} | {skill['success_rate']:.3f} | "
                    f"{skill.get('learning_health', 0.0):.3f} | {skill.get('promotion_rate_45d', 0.0):.3f} | "
                    f"{skill.get('flaky_rate_45d', 0.0):.3f} | {skill.get('tests_coverage', 'n/a')} | {skill.get('risk_score', 'n/a')} | "
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

    def _self_learning_map(self, skill_names: Iterable[str], window_days: int = 45) -> dict[str, dict[str, Any]]:
        names = [str(s or "").strip() for s in skill_names if str(s or "").strip()]
        if not names:
            return {}
        unique = list(dict.fromkeys(names))
        placeholders = ",".join(["?"] * len(unique))
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            events = conn.execute(
                f"""
                SELECT skill_name,
                       SUM(CASE WHEN decision='promoted' THEN 1 ELSE 0 END) AS promoted_n,
                       COUNT(*) AS total_n
                FROM self_learning_promotion_events
                WHERE skill_name IN ({placeholders})
                  AND created_at >= datetime('now', ?)
                GROUP BY skill_name
                """,
                tuple(unique) + (f"-{max(1, int(window_days))} day",),
            ).fetchall()
            jobs = conn.execute(
                f"""
                SELECT skill_name,
                       SUM(CASE WHEN flaky = 1 THEN 1 ELSE 0 END) AS flaky_n,
                       COUNT(*) AS total_n
                FROM self_learning_test_jobs
                WHERE skill_name IN ({placeholders})
                  AND status IN ('passed','failed')
                  AND updated_at >= datetime('now', ?)
                GROUP BY skill_name
                """,
                tuple(unique) + (f"-{max(1, int(window_days))} day",),
            ).fetchall()
        except Exception:
            return {}
        finally:
            conn.close()
        out: dict[str, dict[str, Any]] = {}
        for row in events:
            total_n = int(row["total_n"] or 0)
            promoted_n = int(row["promoted_n"] or 0)
            out[str(row["skill_name"])] = {
                "promotion_rate": (promoted_n / max(1, total_n)) if total_n > 0 else 0.0,
                "outcomes_weight": float(total_n),
            }
        for row in jobs:
            key = str(row["skill_name"])
            total_n = int(row["total_n"] or 0)
            flaky_n = int(row["flaky_n"] or 0)
            slot = out.setdefault(key, {"promotion_rate": 0.0, "outcomes_weight": 0.0})
            slot["flaky_rate"] = (flaky_n / max(1, total_n)) if total_n > 0 else 0.0
            slot["test_runs"] = total_n
        return out
