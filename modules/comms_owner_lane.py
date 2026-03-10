from config.logger import get_logger
from config.settings import settings

logger = get_logger("comms_owner_lane", agent="comms_owner_lane")


async def handle_owner_text(agent, text: str, source: str = "owner_inbox") -> None:
    """Process owner text without Telegram Update (offline inbox)."""
    text = (text or "").strip()
    if not text:
        return
    agent._log_owner_request(text, source=source)

    async def _owner_reply(msg: str, markup=None) -> None:
        del markup
        await agent.send_message(msg)

    login_svc = agent._detect_service_login_request(text)
    if login_svc and agent._is_inventory_prompt(text):
        agent._touch_service_context(login_svc)
        if agent._service_auth_confirmed.get(login_svc):
            await agent.send_message(await agent._format_service_inventory_snapshot(login_svc), level="result")
            return
    if await agent._handle_kdp_login_flow(text, _owner_reply, with_button=False):
        agent._touch_service_context("amazon_kdp")
        return
    svc = login_svc
    if svc and svc != "amazon_kdp":
        if await agent._start_service_auth_flow(svc, _owner_reply, with_button=False):
            return

    lower = text.lower()
    if agent._pending_service_auth and agent._is_auth_done_text(lower):
        service = next(reversed(agent._pending_service_auth))
        pending = agent._pending_service_auth.pop(service, None) or {}
        ok, detail = await agent._verify_service_auth(service)
        title, _ = agent._service_auth_meta(service)
        agent._touch_service_context(service)
        if ok:
            agent._mark_service_auth_confirmed(service)
            await agent.send_message(f"Вход подтверждён: {title}.")
        else:
            if agent._requires_strict_auth_verification(service):
                since = str(pending.get("requested_at") or "")
                has_storage, storage_detail = agent._has_cookie_storage_state(service, since_iso=since)
                if bool(pending.get("mode") == "remote") and has_storage:
                    agent._mark_service_auth_confirmed(service)
                    await agent.send_message(f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail}).")
                    return
                agent._clear_service_auth_confirmed(service)
                extra = f" {agent._manual_capture_hint(service)}" if agent._is_challenge_detail(detail) else ""
                await agent.send_message(agent._service_needs_session_refresh_text(service, title, detail) + extra)
            elif agent._is_manual_auth_service(service):
                agent._mark_service_auth_confirmed(service)
                await agent.send_message(f"Вход зафиксирован вручную: {title}. Проверка: {detail}")
            else:
                await agent.send_message(f"Не удалось подтвердить вход: {detail}")
        return

    service_inventory = agent._detect_contextual_service_inventory_request(text)
    if service_inventory:
        await agent.send_message(await agent._format_service_inventory_snapshot(service_inventory), level="result")
        return
    service_status = agent._detect_contextual_service_status_request(text)
    if service_status:
        await agent.send_message(await agent._format_service_auth_status_live(service_status), level="result")
        return
    if agent._is_auth_issue_prompt(text):
        svc = agent._last_service_context if agent._has_fresh_service_context() else ""
        if svc:
            await agent.send_message(await agent._format_service_auth_status_live(svc), level="result")
            return

    if agent._try_set_env_from_text(text):
        await agent.send_message("Ключ принят и сохранён. Если нужен перезапуск сервиса — скажи 'перезапусти'.")
        return
    if agent._try_deactivate_preference_from_text(text):
        await agent.send_message("Предпочтение деактивировано.")
        return
    if agent._try_set_preference_from_text(text):
        await agent.send_message("Предпочтение сохранено. Могу учитывать в будущих задачах.")
        return

    lower = text.lower()
    if agent._pending_service_auth and agent._is_auth_done_text(lower):
        service = next(reversed(agent._pending_service_auth))
        pending = agent._pending_service_auth.pop(service, None) or {}
        ok, detail = await agent._verify_service_auth(service)
        title, _ = agent._service_auth_meta(service)
        agent._touch_service_context(service)
        if ok:
            agent._mark_service_auth_confirmed(service)
            await agent.send_message(f"Вход подтверждён: {title}.")
            logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text"}})
        else:
            if agent._requires_strict_auth_verification(service):
                since = str(pending.get("requested_at") or "")
                has_storage, storage_detail = agent._has_cookie_storage_state(service, since_iso=since)
                if bool(pending.get("mode") == "remote") and has_storage:
                    agent._mark_service_auth_confirmed(service)
                    await agent.send_message(
                        f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail})."
                    )
                    return
                agent._clear_service_auth_confirmed(service)
                extra = f" {agent._manual_capture_hint(service)}" if agent._is_challenge_detail(detail) else ""
                await agent.send_message(agent._service_needs_session_refresh_text(service, title, detail) + extra)
            elif agent._is_manual_auth_service(service):
                agent._mark_service_auth_confirmed(service)
                await agent.send_message(f"Вход зафиксирован вручную: {title}. Проверка: {detail}")
                logger.info("Inline auth_done via text", extra={"event": "inline_auth_done", "context": {"service": service, "mode": "text_manual"}})
            else:
                await agent.send_message(f"Не удалось подтвердить вход: {detail}")
        return
    if agent._pending_owner_confirmation and (agent._is_yes_token(lower) or agent._is_no_token(lower)):
        payload = agent._pending_owner_confirmation or {}
        agent._pending_owner_confirmation = None
        kind = str(payload.get("kind") or "")
        if agent._is_yes_token(lower):
            if kind == "clear_goals" and agent._goal_engine:
                removed = int(agent._goal_engine.clear_all_goals() or 0)
                await agent.send_message(f"Готово. Очередь целей очищена ({removed}).", level="result")
            elif kind == "rollback" and agent._self_updater:
                backup_path = str(payload.get("backup_path") or "")
                if not backup_path:
                    await agent.send_message("Нет пути к бэкапу для отката.", level="result")
                else:
                    success = agent._self_updater.rollback(backup_path)
                    status = "Откат выполнен" if success else "Ошибка отката"
                    await agent.send_message(f"{status}: {backup_path}", level="result")
            else:
                await agent.send_message("Принял. Выполняю.", level="result")
        else:
            await agent.send_message("Ок, отменил.", level="result")
        return
    strict_cmds = bool(getattr(settings, "TELEGRAM_STRICT_COMMANDS", True)) and not agent._autonomy_max_enabled()
    if agent._pending_system_action:
        pending_kind = str((agent._pending_system_action or {}).get("kind") or "").strip().lower()
        allow_numeric_choice = text.isdigit() and (
            (not strict_cmds) or pending_kind == "research_options"
        )
        if allow_numeric_choice:
            idx = int(text)
            picked = agent._select_pending_research_option(idx)
            if picked is not None:
                await agent.send_message(f"Принял вариант {idx}. Запускаю.", level="result")
                await agent._execute_pending_system_action()
                return
            actions = list((agent._pending_system_action or {}).get("actions") or [])
            if 1 <= idx <= len(actions):
                agent._pending_system_action = {"actions": [actions[idx - 1]], "origin_text": f"choice:{idx}"}
                await agent.send_message(f"Принял вариант {idx}. Запускаю.", level="result")
                await agent._execute_pending_system_action()
                return
        if agent._is_yes_token(lower):
            payload = agent._pending_system_action or {}
            if str(payload.get("kind") or "").strip().lower() == "research_options":
                rec_idx = int(payload.get("recommended_index") or 1)
                agent._select_pending_research_option(rec_idx)
            await agent._execute_pending_system_action()
            return
        if agent._is_no_token(lower):
            agent._pending_system_action = None
            await agent.send_message("Ок, отменил.", level="result")
            return

    for candidate in (
        agent._maybe_handle_owner_shortcuts,
        agent._maybe_handle_owner_service_commands,
        agent._maybe_handle_owner_menu_commands,
        agent._maybe_handle_owner_task_commands,
        agent._maybe_handle_owner_publish_commands,
        agent._maybe_handle_owner_webop_commands,
    ):
        handled = await candidate(text)
        if handled:
            return

    if agent._conversation_engine:
        try:
            if hasattr(agent._conversation_engine, "set_session"):
                agent._conversation_engine.set_session("owner_inbox")
            if hasattr(agent._conversation_engine, "set_defer_owner_actions"):
                agent._conversation_engine.set_defer_owner_actions(True)
            result = await agent._conversation_engine.process_message(text)
            if result.get("create_goal") and agent._goal_engine:
                from goal_engine import GoalPriority, GoalStatus

                priority_map = {
                    "CRITICAL": GoalPriority.CRITICAL,
                    "HIGH": GoalPriority.HIGH,
                    "MEDIUM": GoalPriority.MEDIUM,
                    "LOW": GoalPriority.LOW,
                }
                goal = agent._goal_engine.create_goal(
                    title=result.get("goal_title", text[:100]),
                    description=result.get("goal_description", text),
                    priority=priority_map.get(result.get("goal_priority", "HIGH"), GoalPriority.HIGH),
                    source="owner",
                    estimated_cost_usd=result.get("estimated_cost_usd", 0.05),
                )
                if result.get("needs_approval", False):
                    goal.status = GoalStatus.WAITING_APPROVAL
                    agent._goal_engine._persist_goal(goal)
                response = result.get("response", f"Цель создана: {goal.title}")
                response = agent._owner_goal_response_override(text, response, goal.title)
                if result.get("needs_approval"):
                    response += "\n\nПодтверди запуск: да/нет."
                response = agent._decorate_with_numeric_hint(response, result.get("actions", []))
                response = agent._normalize_owner_control_reply(text, response)
                agent._remember_choice_context(response)
                await agent.send_message(response, level="result")
            elif result.get("response"):
                response = agent._decorate_with_numeric_hint(result["response"], result.get("actions", []))
                response = agent._normalize_owner_control_reply(text, response)
                agent._remember_choice_context(response)
                await agent.send_message(response, level="result")
                agent._prime_research_pending_actions_from_owner_state(text)
                if result.get("actions") and result.get("needs_confirmation"):
                    if agent._autonomy_max_enabled() and agent._conversation_engine:
                        out = await agent._conversation_engine._execute_actions(result.get("actions", []))
                        await agent.send_message(out or "Действие выполнено.", level="result")
                    else:
                        agent._pending_system_action = {
                            "actions": result.get("actions", []),
                            "origin_text": text,
                        }
                elif result.get("actions"):
                    agent._schedule_system_actions_background(
                        result.get("actions", []),
                        origin_text=text,
                    )
            else:
                await agent.send_message("Понял. Чем могу помочь?")
            return
        except Exception as e:
            logger.warning(f"ConversationEngine error: {e}", extra={"event": "conversation_error"})

    await agent.send_message("Не понял: это вопрос или задача? Напиши одним предложением, что нужно сделать.")
