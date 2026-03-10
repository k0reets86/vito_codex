from __future__ import annotations

from datetime import datetime, timezone
from telegram.error import BadRequest as TgBadRequest


def _lane_logger(agent):
    return getattr(agent, "_logger", None) or getattr(agent, "logger", None)


async def safe_edit_callback_message(agent, query, text: str) -> None:
    try:
        await query.edit_message_text(text=text)
    except TgBadRequest:
        log = _lane_logger(agent)
        if log is not None:
            log.info(
                "Callback message edit skipped (non-editable or unchanged).",
                extra={"event": "callback_edit_skipped"},
            )
    except Exception:
        log = _lane_logger(agent)
        if log is not None:
            log.warning(
                "Callback message edit failed unexpectedly.",
                extra={"event": "callback_edit_failed"},
                exc_info=True,
            )


async def handle_callback(agent, update, context) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if query.from_user.id != agent._owner_id:
        await query.answer("Доступ запрещён", show_alert=True)
        return
    parts = query.data.split(":", 1)
    if len(parts) != 2:
        await query.answer("Неизвестная команда")
        return
    action, request_id = parts

    if action == "help_topic":
        topic = str(request_id or "").strip().lower()
        await query.answer("Открываю")
        text = agent._render_help(topic if topic in {"daily", "rare", "system"} else None)
        await safe_edit_callback_message(agent, query, text)
        return

    if action == "auth_cancel":
        agent._pending_service_auth.pop(request_id, None)
        await query.answer("Отменено")
        await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— Отменено")
        return

    if action == "auth_done":
        service = str(request_id or "").strip().lower()
        pending = agent._pending_service_auth.pop(service, None) or {}
        agent._touch_service_context(service)
        try:
            ok, detail = await agent._verify_service_auth(service)
        except Exception as e:
            ok, detail = False, f"Ошибка проверки авторизации: {e}"
        title, _ = agent._service_auth_meta(service)
        if ok:
            stamp = datetime.now(timezone.utc).isoformat()
            agent._service_auth_confirmed[service] = stamp
            agent._save_auth_state()
            label = f"Вход подтверждён: {title}"
            await query.answer("Вход подтверждён")
            await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— {label}")
            log = _lane_logger(agent)
            if log is not None:
                log.info(
                    f"Inline auth_done: {service}",
                    extra={"event": "inline_auth_done", "context": {"service": service, "mode": "verified"}},
                )
            await agent.send_message(label, level="result")
            return
        if agent._requires_strict_auth_verification(service):
            since = str(pending.get("requested_at") or "")
            has_storage, storage_detail = agent._has_cookie_storage_state(service, since_iso=since)
            if bool(pending.get("mode") == "remote") and has_storage:
                stamp = datetime.now(timezone.utc).isoformat()
                agent._service_auth_confirmed[service] = stamp
                agent._save_auth_state()
                label = f"Вход подтверждён: {title} (server storage захвачен)"
                await query.answer("Вход подтверждён")
                await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— {label}\n({storage_detail})")
                await agent.send_message(label, level="result")
                return
            agent._clear_service_auth_confirmed(service)
            extra = f" {agent._manual_capture_hint(service)}" if agent._is_challenge_detail(detail) else ""
            await query.answer("Нужно обновить сессию", show_alert=False)
            await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— Нужно обновить сессию.\n{detail}{extra}")
            await agent.send_message(agent._service_needs_session_refresh_text(service, title, detail) + extra, level="warning")
            return
        if agent._is_manual_auth_service(service):
            stamp = datetime.now(timezone.utc).isoformat()
            agent._service_auth_confirmed[service] = stamp
            agent._save_auth_state()
            label = f"Вход зафиксирован вручную: {title}"
            await query.answer("Принято")
            await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— {label}\n(Проверка: {detail})")
            log = _lane_logger(agent)
            if log is not None:
                log.info(
                    f"Inline auth_done: {service}",
                    extra={"event": "inline_auth_done", "context": {"service": service, "mode": "manual_fallback", "detail": detail[:200]}},
                )
            await agent.send_message(f"{label}. Можно продолжать работу.", level="result")
            return
        await query.answer("Не подтверждено", show_alert=True)
        await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— Вход не подтверждён.\n{detail}")
        await agent.send_message(f"Не удалось подтвердить вход: {title}. Деталь: {detail}", level="warning")
        return

    future = agent._pending_approvals.pop(request_id, None)
    if future is None:
        await query.answer("Запрос уже обработан или не найден")
        await query.edit_message_reply_markup(reply_markup=None)
        return
    approved = action == "approve"
    if not future.done():
        future.set_result(approved)
    label = "Одобрено" if approved else "Отклонено"
    await query.answer(label)
    await safe_edit_callback_message(agent, query, f"{query.message.text}\n\n— {label}")
    log = _lane_logger(agent)
    if log is not None:
        log.info(
            f"Inline {label.lower()}: {request_id}",
            extra={"event": f"inline_{'approved' if approved else 'rejected'}", "context": {"request_id": request_id}},
        )
