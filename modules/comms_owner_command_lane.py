from __future__ import annotations

from config.settings import settings


async def maybe_handle_owner_menu_commands(agent, text: str) -> bool:
    lower = str(text or "").lower().strip()
    strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not agent._autonomy_max_enabled()
    if not strict_cmds:
        text = agent._expand_short_choice(text)
        lower = text.lower().strip()
    if lower in ("/help", "help"):
        await agent.send_message(agent._render_help())
        return True
    if lower in ("/help_daily", "help_daily", "/help daily", "help daily", "/help daily_commands"):
        await agent.send_message(agent._render_help("daily"))
        return True
    if lower in ("/help_rare", "help_rare", "/help rare", "help rare"):
        await agent.send_message(agent._render_help("rare"))
        return True
    if lower in ("/help_system", "help_system", "/help system", "help system"):
        await agent.send_message(agent._render_help("system"))
        return True
    if (not strict_cmds and any(kw in lower for kw in ["статус", "/status"])) or lower in ("/status", "status"):
        await agent.send_message(agent._render_unified_status())
        return True
    if lower in ("/workflow", "workflow"):
        try:
            from modules.workflow_state_machine import WorkflowStateMachine
            h = WorkflowStateMachine().health()
            await agent.send_message(f"Workflow\nВсего: {h.get('workflows_total',0)}\nОбновлён: {h.get('last_update','-')}")
            return True
        except Exception:
            return False
    if lower in ("/handoffs", "handoffs"):
        try:
            from modules.data_lake import DataLake
            rows = DataLake().handoff_summary(days=7)[:5]
            if not rows:
                await agent.send_message("Handoffs: нет событий за 7 дней")
                return True
            lines = ["Handoffs (7d):"]
            for r in rows:
                lines.append(f"- {r.get('from','?')} -> {r.get('to','?')}: ok={r.get('ok',0)} fail={r.get('fail',0)} total={r.get('total',0)}")
            await agent.send_message("\n".join(lines))
            return True
        except Exception:
            return False
    if lower in ("/prefs", "prefs", "предпочтения"):
        try:
            await agent._send_prefs()
            return True
        except Exception:
            return False
    if lower in ("/prefs_metrics", "prefs_metrics"):
        try:
            await agent._send_prefs_metrics()
            return True
        except Exception:
            return False
    if lower in ("/packs", "packs"):
        try:
            await agent._send_packs()
            return True
        except Exception:
            return False
    return False


async def maybe_handle_owner_publish_commands(agent, text: str) -> bool:
    lower = str(text or "").lower().strip()
    if lower in ("/pubq", "pubq"):
        try:
            if not agent._publisher_queue:
                await agent.send_message("PublisherQueue не подключён.")
                return True
            st = agent._publisher_queue.stats()
            await agent.send_message(
                f"Publish Queue\nqueued={st.get('queued',0)} running={st.get('running',0)} done={st.get('done',0)} failed={st.get('failed',0)} total={st.get('total',0)}"
            )
            return True
        except Exception:
            return False
    if lower.startswith("/pubrun") or lower == "pubrun":
        try:
            if not agent._publisher_queue:
                await agent.send_message("PublisherQueue не подключён.")
                return True
            lim = 5
            parts = lower.split()
            if len(parts) >= 2 and parts[1].isdigit():
                lim = max(1, min(20, int(parts[1])))
            rows = await agent._publisher_queue.process_all(limit=lim)
            await agent.send_message(f"Publish run: processed={len(rows)}")
            return True
        except Exception:
            return False
    return False


async def maybe_handle_owner_webop_commands(agent, text: str) -> bool:
    lower = str(text or "").lower().strip()
    if lower.startswith("/webop") or lower.startswith("webop"):
        try:
            if not agent._agent_registry:
                await agent.send_message("AgentRegistry не подключён.")
                return True
            from modules.web_operator_pack import WebOperatorPack
            pack = WebOperatorPack(agent._agent_registry)
            parts = lower.split()
            if len(parts) == 1 or parts[1] in {"list", "ls"}:
                items = pack.list_scenarios()
                await agent.send_message("WebOp scenarios:\n" + ("\n".join(f"- {x}" for x in items) if items else "- empty"))
                return True
            if len(parts) >= 3 and parts[1] == "run":
                res = await pack.run(parts[2], overrides={})
                await agent.send_message(f"WebOp run: {parts[2]}\nstatus={res.get('status')}\nerror={res.get('error','')}")
                return True
        except Exception:
            return False
    return False
