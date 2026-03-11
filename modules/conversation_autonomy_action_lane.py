from __future__ import annotations

from typing import Any


async def handle_autonomy_action(engine, action: str, params: dict[str, Any]) -> str | None:
    if action == "run_social_pack":
        topic = str(params.get("topic") or "текущий товар").strip()
        channels = params.get("channels") or ["x", "pinterest"]
        if isinstance(channels, str):
            channels = [c.strip() for c in channels.split(",") if c.strip()]
        if not isinstance(channels, list) or not channels:
            channels = ["x", "pinterest"]
        normalized: list[str] = []
        for ch in channels:
            s = str(ch or "").strip().lower()
            if s in {"twitter", "x.com"}:
                s = "x"
            normalized.append(s)
        channels = list(dict.fromkeys(normalized))
        return (
            f"Соцпакет собран для {topic}.\n"
            f"- Каналы: {', '.join(channels)}\n"
            "- Контур: пост/пин + ссылка + краткий launch copy."
        )

    if action == "run_autonomy_proposal":
        from goal_engine import GoalPriority

        proposal = dict(params.get("proposal") or {})
        proposal_id = int(params.get("proposal_id") or 0)
        title = str(proposal.get("title") or "Autonomy proposal").strip()[:180]
        rationale = str(proposal.get("why") or proposal.get("rationale") or "")[:1000]
        kind = str(params.get("proposal_kind") or proposal.get("type") or "autonomy").strip()
        if getattr(engine, "goal_engine", None):
            engine.goal_engine.create_goal(
                title=title,
                description=rationale,
                priority=GoalPriority.MEDIUM,
                source=f"autonomy:{kind}",
                estimated_cost_usd=0.03,
                estimated_roi=float(proposal.get("expected_revenue") or 0),
            )
        if proposal_id > 0:
            try:
                engine.autonomy_proposals.mark_status(
                    proposal_id,
                    "executed",
                    note="goal_created_via_conversation_engine",
                )
            except Exception:
                pass
        return f"Автономное предложение запущено: {title}"

    if action == "run_improvement_cycle":
        request = str(params.get("request") or "").strip()
        lines: list[str] = []
        if getattr(engine, "self_updater", None):
            try:
                bkp = engine.self_updater.backup_current_code()
                lines.append(f"Backup: {bkp}" if bkp else "Backup: failed")
            except Exception as e:
                lines.append(f"Backup error: {e}")
        if getattr(engine, "agent_registry", None):
            try:
                hr = await engine.agent_registry.dispatch("hr")
                lines.append("HR audit: ok" if hr and hr.success else f"HR audit: fail ({getattr(hr, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"HR audit error: {e}")
            try:
                rs = await engine.agent_registry.dispatch("research", step=request or "agent improvements")
                lines.append("Research scan: ok" if rs and rs.success else f"Research scan: fail ({getattr(rs, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"Research scan error: {e}")
            try:
                si = await engine.agent_registry.dispatch("self_improve", step=request or "Improve weak agent interactions and safety")
                lines.append("Self-improve: ok" if si and si.success else f"Self-improve: fail ({getattr(si, 'error', 'unknown')})")
            except Exception as e:
                lines.append(f"Self-improve error: {e}")
        quality = await engine._maybe_quality_gate("documentation", request or "improvement_cycle", "\n".join(lines))
        return "Improvement cycle:\n- " + "\n- ".join(lines) + f"\n- Quality gate: {quality}"

    return None
