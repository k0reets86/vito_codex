from __future__ import annotations

from typing import Any


async def handle_contextual_service_prompts(agent, update, text: str) -> bool:
    service_inventory = agent._detect_contextual_service_inventory_request(text)
    if service_inventory:
        await update.message.reply_text(
            await agent._format_service_inventory_snapshot(service_inventory),
            reply_markup=agent._main_keyboard(),
        )
        agent._record_context_learning(
            skill_name="contextual_service_inventory_resolution",
            description=(
                "Если активен контекст платформы, запросы вида 'проверь товары/листинги' "
                "выполняются как проверка аккаунта этой платформы, а не как market research."
            ),
            anti_pattern=(
                "Плохо: отправлять владельца в analyze_niche, когда он просит проверить товары в текущем аккаунте."
            ),
            method={"service": service_inventory, "source_text": text[:120]},
        )
        return True
    service_status = agent._detect_contextual_service_status_request(text)
    if service_status:
        await update.message.reply_text(
            await agent._format_service_auth_status_live(service_status),
            reply_markup=agent._main_keyboard(),
        )
        agent._record_context_learning(
            skill_name="contextual_service_status_resolution",
            description=(
                "Если у владельца активный контекст платформы, короткий запрос 'статус' трактуется "
                "как статус входа/аккаунта этой платформы."
            ),
            anti_pattern=(
                "Плохо: игнорировать недавний контекст сервиса и отвечать системным статусом VITO "
                "вместо статуса нужной платформы."
            ),
            method={"service": service_status, "source_text": text[:120]},
        )
        return True
    if agent._is_auth_issue_prompt(text):
        svc = agent._last_service_context if agent._has_fresh_service_context() else ""
        if svc:
            await update.message.reply_text(
                await agent._format_service_auth_status_live(svc),
                reply_markup=agent._main_keyboard(),
            )
            return True
    return False


async def handle_pending_service_auth(agent, update, lower: str) -> bool:
    if not (agent._pending_service_auth and agent._is_auth_done_text(lower)):
        return False
    service = next(reversed(agent._pending_service_auth))
    pending = agent._pending_service_auth.pop(service, None) or {}
    ok, detail = await agent._verify_service_auth(service)
    title, _ = agent._service_auth_meta(service)
    agent._touch_service_context(service)
    if ok:
        agent._mark_service_auth_confirmed(service)
        await update.message.reply_text(f"Вход подтверждён: {title}.", reply_markup=agent._main_keyboard())
        return True
    if agent._requires_strict_auth_verification(service):
        since = str(pending.get("requested_at") or "")
        has_storage, storage_detail = agent._has_cookie_storage_state(service, since_iso=since)
        if bool(pending.get("mode") == "remote") and has_storage:
            agent._mark_service_auth_confirmed(service)
            await update.message.reply_text(
                f"Вход подтверждён: {title} (server storage захвачен, detail={storage_detail}).",
                reply_markup=agent._main_keyboard(),
            )
            return True
        agent._clear_service_auth_confirmed(service)
        extra = f" {agent._manual_capture_hint(service)}" if agent._is_challenge_detail(detail) else ""
        await update.message.reply_text(
            agent._service_needs_session_refresh_text(service, title, detail) + extra,
            reply_markup=agent._main_keyboard(),
        )
        return True
    if agent._is_manual_auth_service(service):
        agent._mark_service_auth_confirmed(service)
        await update.message.reply_text(
            f"Вход зафиксирован вручную: {title}. Проверка: {detail}",
            reply_markup=agent._main_keyboard(),
        )
        return True
    await update.message.reply_text(f"Не удалось подтвердить вход: {detail}", reply_markup=agent._main_keyboard())
    return True


async def handle_pending_owner_confirmation(agent, update, lower: str) -> bool:
    if not (agent._pending_owner_confirmation and (agent._is_yes_token(lower) or agent._is_no_token(lower))):
        return False
    payload = agent._pending_owner_confirmation or {}
    agent._pending_owner_confirmation = None
    kind = str(payload.get("kind") or "")
    if agent._is_yes_token(lower):
        if kind == "clear_goals" and agent._goal_engine:
            removed = int(agent._goal_engine.clear_all_goals() or 0)
            await update.message.reply_text(
                f"Готово. Очередь целей очищена ({removed}).",
                reply_markup=agent._main_keyboard(),
            )
        elif kind == "rollback" and agent._self_updater:
            backup_path = str(payload.get("backup_path") or "")
            if not backup_path:
                await update.message.reply_text("Нет пути к бэкапу для отката.", reply_markup=agent._main_keyboard())
            else:
                success = agent._self_updater.rollback(backup_path)
                status = "Откат выполнен" if success else "Ошибка отката"
                await update.message.reply_text(f"{status}: {backup_path}", reply_markup=agent._main_keyboard())
        else:
            await update.message.reply_text("Принял. Выполняю.", reply_markup=agent._main_keyboard())
    else:
        await update.message.reply_text("Ок, отменил.", reply_markup=agent._main_keyboard())
    return True


async def handle_pending_system_action(agent, update, text: str, lower: str, strict_cmds: bool) -> bool:
    if not agent._pending_system_action:
        return False
    pending_kind = str((agent._pending_system_action or {}).get("kind") or "").strip().lower()
    allow_numeric_choice = text.isdigit() and ((not strict_cmds) or pending_kind == "research_options")
    if allow_numeric_choice:
        idx = int(text)
        picked = agent._select_pending_research_option(idx)
        if picked is not None:
            await update.message.reply_text(
                f"Принял вариант {idx}. Запускаю.",
                reply_markup=agent._main_keyboard(),
            )
            await agent._execute_pending_system_action(update)
            return True
        actions = list((agent._pending_system_action or {}).get("actions") or [])
        if 1 <= idx <= len(actions):
            agent._pending_system_action = {"actions": [actions[idx - 1]], "origin_text": f"choice:{idx}"}
            await update.message.reply_text(
                f"Принял вариант {idx}. Запускаю.",
                reply_markup=agent._main_keyboard(),
            )
            await agent._execute_pending_system_action(update)
            return True
    if agent._is_yes_token(lower):
        payload = agent._pending_system_action or {}
        if str(payload.get("kind") or "").strip().lower() == "research_options":
            rec_idx = int(payload.get("recommended_index") or 1)
            agent._select_pending_research_option(rec_idx)
        await agent._execute_pending_system_action(update)
        return True
    if agent._is_no_token(lower):
        agent._pending_system_action = None
        await update.message.reply_text(
            "Ок, системное действие отменено.",
            reply_markup=agent._main_keyboard(),
        )
        return True
    return False


async def handle_pending_schedule_update(agent, update, text: str) -> bool:
    if not agent._pending_schedule_update:
        return False
    sel = text.strip()
    if not sel.isdigit():
        return False
    idx = int(sel)
    choices = agent._pending_schedule_update.get("choices", [])
    new_sched = agent._pending_schedule_update.get("new_schedule")
    mode = agent._pending_schedule_update.get("mode", "update")
    if not (1 <= idx <= len(choices)):
        return False
    task = choices[idx - 1]
    try:
        if mode == "delete":
            agent._schedule_manager.delete_task(task.id)
            await update.message.reply_text(
                f"Готово. Расписание #{task.id} удалено.",
                reply_markup=agent._main_keyboard(),
            )
        else:
            agent._schedule_manager.update_task(
                task.id,
                schedule_type=new_sched.schedule_type,
                time_of_day=new_sched.time_of_day,
                weekday=new_sched.weekday,
                run_at=new_sched.run_at,
            )
            await update.message.reply_text(
                f"Готово. Обновил расписание для задачи #{task.id}.",
                reply_markup=agent._main_keyboard(),
            )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка обновления расписания: {e}",
            reply_markup=agent._main_keyboard(),
        )
    agent._pending_schedule_update = None
    return True
