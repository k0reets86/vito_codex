from __future__ import annotations

from typing import Any

from config.settings import settings


async def maybe_handle_owner_shortcuts(agent: Any, text: str) -> bool:
    lower = str(text or "").lower()
    strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not agent._autonomy_max_enabled()
    if agent._is_what_do_you_need_prompt(text):
        await agent.send_message(
            "Сейчас от тебя ничего не нужно. Если захочешь продолжить работу или поставить новую цель, напиши это одной фразой.",
            level="result",
        )
        return True
    if agent._is_what_is_ready_prompt(text):
        await agent.send_message(
            "Сейчас могу коротко показать только подтвержденные результаты и активные задачи. Для деталей скажи: «сводка» или «что по задачам».",
            level="result",
        )
        return True
    if agent._is_what_should_i_do_prompt(text):
        await agent.send_message(
            "Пока от тебя ничего не нужно. Если понадобится код, логин или подтверждение, я скажу это прямо.",
            level="result",
        )
        return True
    if agent._is_do_not_publish_prompt(text):
        await agent.send_message(
            "Ок. Публикацию не запускаю без отдельного явного указания.",
            level="result",
        )
        return True
    if agent._is_remove_this_prompt(text):
        await agent.send_message(
            "Уточни, что именно убрать: текущую задачу, публикацию, черновик или сообщение.",
            level="result",
        )
        return True
    if agent._is_do_not_do_now_prompt(text):
        await agent.send_message(
            "Ок. Сейчас не запускаю. Можем вернуться к этому позже или по новой команде.",
            level="result",
        )
        return True
    if agent._is_not_understood_prompt(text):
        await agent.send_message(
            "Уточни, что именно непонятно: задача, статус, платформа или следующий шаг.",
            level="result",
        )
        return True
    if agent._is_why_stopped_prompt(text):
        await agent.send_message(
            "Если я остановился, значит либо нет активной задачи, либо нужен явный следующий шаг, либо сработала пауза/блокер. Скажи: «что по задачам» или «продолжай».",
            level="result",
        )
        return True
    if agent._is_do_not_touch_old_prompt(text):
        await agent.send_message(
            "Правило зафиксировано: старые и опубликованные объекты не трогаются без явного указания и target id.",
            level="result",
        )
        return True
    if agent._is_create_new_prompt(text):
        await agent.send_message(
            "Уточни, что именно создать и на какой платформе: например «создай новый товар на etsy» или «создай новую книгу на amazon kdp».",
            level="result",
        )
        return True
    if agent._is_postpone_prompt(text):
        await agent.send_message("Ок, отложил. Можем вернуться к этому позже.", level="result")
        return True
    if agent._is_nevermind_prompt(text):
        agent._pending_system_action = None
        agent._pending_owner_confirmation = None
        await agent.send_message("Ок, отменил текущий запрос.", level="result")
        return True
    if agent._is_resume_prompt(text):
        if agent._cancel_state:
            try:
                agent._cancel_state.clear()
            except Exception:
                pass
        if agent._decision_loop and not agent._decision_loop.running:
            try:
                agent._decision_loop.start()
            except Exception:
                pass
        await agent.send_message("Продолжаю работу. Если нужна новая цель, напиши ее одной фразой.", level="result")
        return True
    if agent._is_pause_prompt(text):
        cancelled = cancel_all_owner_work(agent, reason="owner_text_pause")
        await agent.send_message(
            f"Остановил текущую работу. Снято задач из очереди: {cancelled}. Для продолжения напиши: «продолжай».",
            level="result",
        )
        return True
    if agent._is_cancel_all_tasks_prompt(text):
        cancelled = cancel_all_owner_work(agent, reason="owner_text_cancel_all")
        await agent.send_message(
            f"Все текущие задачи снял. Отменено из очереди: {cancelled}.",
            level="result",
        )
        return True
    if agent._is_how_are_you_prompt(text):
        await agent.send_message(render_owner_brief_status(agent), level="result")
        return True
    if text.isdigit() and agent._prime_research_pending_actions_from_owner_state(text):
        idx = int(text)
        picked = agent._select_pending_research_option(idx)
        if picked is not None:
            title = str(picked.get("title") or "").strip()
            score = int(picked.get("score", 0) or 0)
            await agent.send_message(
                f"Зафиксировал вариант {idx}: {title} ({score}/100). Если запускать сразу, напиши: «создавай» или укажи платформу.",
                level="result",
            )
            return True
    if (not strict_cmds) and any(x in lower for x in ("llm_mode ", "режим llm", "режим lmm", "llm режим")):
        mode = "status"
        if any(x in lower for x in (" free", " тест", " gemini", " flash")):
            mode = "free"
        elif any(x in lower for x in (" prod", " боев", " production")):
            mode = "prod"
        ok, msg = agent._apply_llm_mode(mode)
        await agent.send_message(msg if ok else "Используй: /llm_mode free|prod|status", level="result")
        return True
    return False


def render_owner_brief_status(agent: Any) -> str:
    running = False
    if agent._decision_loop:
        try:
            st = agent._decision_loop.get_status() or {}
            running = bool(st.get("running", False))
        except Exception:
            pass
    active_text = ""
    if agent._owner_task_state:
        try:
            active = agent._owner_task_state.get_active() or {}
            active_text = str(active.get("text") or "").strip()
        except Exception:
            pass
    pending_approvals = len(getattr(agent, "_pending_approvals", {}) or {})
    queued = 0
    if agent._goal_engine:
        try:
            goals = agent._goal_engine.get_all_goals(status=None) or []
            queued = sum(
                1
                for g in goals
                if str(getattr(getattr(g, "status", None), "value", "") or "")
                not in {"completed", "failed", "cancelled"}
            )
        except Exception:
            pass
    lines = []
    if active_text:
        lines.append(f"Сейчас в работе: {active_text[:200]}")
    else:
        lines.append("Сейчас активной задачи от тебя не зафиксировано.")
    lines.append(f"Decision Loop: {'работает' if running else 'на паузе'}.")
    if pending_approvals:
        lines.append(f"Ожидают подтверждения: {pending_approvals}.")
    if queued:
        lines.append(f"В системной очереди еще {queued}. Если это старые хвосты, напиши: «отмени все задачи»." )
    return "\n".join(lines)


def cancel_all_owner_work(agent: Any, reason: str = "owner_cancelled") -> int:
    if agent._cancel_state:
        try:
            agent._cancel_state.cancel(reason=reason)
        except Exception:
            pass
    cancelled_goals = agent._cancel_goal_queue(reason=reason)
    if agent._owner_task_state:
        try:
            agent._owner_task_state.cancel(note=reason)
        except Exception:
            pass
    agent._pending_approvals.clear()
    agent._pending_schedule_update = None
    agent._pending_owner_confirmation = None
    agent._pending_choice_context = None
    agent._pending_system_action = None
    if agent._decision_loop:
        try:
            agent._decision_loop.stop()
        except Exception:
            pass
    return int(cancelled_goals or 0)


async def maybe_handle_owner_service_commands(agent: Any, text: str) -> bool:
    service_status = agent._detect_contextual_service_status_request(text)
    if service_status:
        await agent.send_message(await agent._format_service_auth_status_live(service_status), level="result")
        return True
    service_inventory = agent._detect_contextual_service_inventory_request(text)
    if service_inventory:
        await agent.send_message(await agent._format_service_inventory_snapshot(service_inventory), level="result")
        agent._record_context_learning(
            skill_name="contextual_service_inventory_resolution",
            description=(
                "Если активен контекст платформы, запросы вида 'проверь товары/листинги' выполняются как проверка аккаунта этой платформы, а не как market research."
            ),
            anti_pattern=(
                "Плохо: отправлять владельца в analyze_niche, когда он просит проверить товары в текущем аккаунте."
            ),
            method={"service": service_inventory, "source_text": text[:120]},
        )
        return True
    return False


async def maybe_handle_owner_menu_commands(agent: Any, text: str) -> bool:
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


async def maybe_handle_owner_task_commands(agent: Any, text: str) -> bool:
    lower = str(text or "").lower().strip()
    if lower in (
        "задачи",
        "что по задачам",
        "что по задач",
        "че по задач",
        "очередь",
        "очередь задач",
    ):
        await agent.send_message(render_owner_brief_status(agent), level="result")
        return True
    if lower in ("/task_current", "task_current"):
        if agent._owner_task_state:
            active = agent._owner_task_state.get_active()
            if active:
                await agent.send_message(
                    "Текущая задача владельца:\n"
                    f"- {str(active.get('text', ''))[:800]}\n"
                    f"- intent: {active.get('intent', '')}\n"
                    f"- status: {active.get('status', 'active')}\n"
                    f"- service: {active.get('service_context', '') or 'n/a'}",
                    level="result",
                )
            else:
                await agent.send_message("Текущая задача не зафиксирована.", level="result")
            return True
    if lower in ("/task_done", "task_done"):
        if agent._owner_task_state:
            agent._owner_task_state.complete(note="owner_marked_done")
            await agent.send_message("Текущая задача отмечена как выполненная.", level="result")
            return True
    if lower in ("/task_cancel", "task_cancel"):
        if agent._owner_task_state:
            agent._owner_task_state.cancel(note="owner_task_cancel")
            await agent.send_message("Текущая задача отменена.", level="result")
            return True
    if lower.startswith("/task_replace ") or lower.startswith("task_replace "):
        if agent._owner_task_state:
            parts = text.split(maxsplit=1)
            if len(parts) >= 2 and parts[1].strip():
                agent._owner_task_state.set_active(parts[1].strip(), source="owner_inbox", intent="manual_replace", force=True)
                await agent.send_message("Текущая задача заменена.", level="result")
            else:
                await agent.send_message("Использование: /task_replace <новая задача>", level="result")
            return True
    return False
