import asyncio
from pathlib import Path

from config.paths import PROJECT_ROOT
from config.settings import settings


async def cmd_auth(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    args = list(getattr(context, "args", None) or [])
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: /auth <service> <status|refresh|verify>\n"
            "Пример: /auth etsy refresh",
            reply_markup=agent._main_keyboard(),
        )
        return
    service = agent._resolve_service_key(args[0])
    action = str(args[1] or "").strip().lower()
    if not service:
        await update.message.reply_text(
            "Неизвестный сервис. Примеры: etsy, amazon_kdp, gumroad, printful, twitter, kofi, reddit.",
            reply_markup=agent._main_keyboard(),
        )
        return

    async def _reply(msg: str, markup=None) -> None:
        kwargs = {"reply_markup": markup} if markup is not None else {"reply_markup": agent._main_keyboard()}
        await update.message.reply_text(msg, **kwargs)

    if action == "status":
        await _reply(await agent._format_service_auth_status_live(service))
        return
    if action == "refresh":
        if service == "amazon_kdp":
            await agent._handle_kdp_login_flow("зайди на amazon kdp", _reply, with_button=True)
            return
        started = await agent._start_service_auth_flow(service, _reply, with_button=True)
        if not started:
            title, _ = agent._service_auth_meta(service)
            await _reply(f"Не удалось запустить flow входа для {title}.")
        return
    if action == "verify":
        ok, detail = await agent._verify_service_auth(service)
        title, _ = agent._service_auth_meta(service)
        if ok:
            agent._mark_service_auth_confirmed(service)
            await _reply(f"Вход подтверждён: {title}.")
        else:
            agent._clear_service_auth_confirmed(service)
            await _reply(agent._service_needs_session_refresh_text(service, title, detail))
        return

    if action == "remote":
        if service not in {"etsy", "amazon_kdp", "kofi", "printful"}:
            await update.message.reply_text(
                "Remote browser-сессия сейчас поддержана для Etsy/Amazon KDP/Ko-fi/Printful.",
                reply_markup=agent._main_keyboard(),
            )
            return
        rc, out = await agent._run_remote_auth_session(service, "start")
        if rc != 0:
            await update.message.reply_text(
                f"Не удалось запустить remote session для {service}.\n{out[:800]}",
                reply_markup=agent._main_keyboard(),
            )
            return
        await update.message.reply_text(
            "Etsy remote-сессия запущена.\n"
            f"{out[:1200]}\n"
            "Открой REMOTE_URL, введи VNC_PASSWORD, пройди вход Etsy в окне браузера, "
            "потом нажми «Я вошел» в Telegram.",
            reply_markup=agent._main_keyboard(),
        )
        return

    await update.message.reply_text(
        "Неизвестное действие. Используй: status, refresh, verify или remote (для Etsy).",
        reply_markup=agent._main_keyboard(),
    )


async def cmd_auth_status(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    services = sorted(agent._SERVICE_CATALOG.keys())
    lines = ["Auth Broker:"]
    for svc in services:
        node = agent._auth_broker.get(svc)
        status = str(node.get("status", "unknown"))
        method = str(node.get("method", "-"))
        valid = "yes" if bool(node.get("is_valid")) else "no"
        exp = str(node.get("expires_at", ""))[:19] if node.get("expires_at") else "-"
        lines.append(f"- {svc}: {status} via {method}, valid={valid}, exp={exp}")
    await update.message.reply_text("\n".join(lines[:80]), reply_markup=agent._main_keyboard())


async def cmd_auth_cookie(agent, update, context) -> None:
    if await agent._reject_stranger(update):
        return
    args = list(getattr(context, "args", None) or [])
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: /auth_cookie <service> <cookies_json_path> [verify]\n"
            "Пример: /auth_cookie etsy input/owner_inbox/etsy.cookies.json verify",
            reply_markup=agent._main_keyboard(),
        )
        return
    service = agent._resolve_service_key(args[0])
    if not service:
        await update.message.reply_text("Неизвестный сервис.", reply_markup=agent._main_keyboard())
        return
    cookies_path = str(args[1] or "").strip()
    verify = any(str(a).strip().lower() in {"verify", "check", "1", "true"} for a in args[2:])
    if not cookies_path:
        await update.message.reply_text("Не указан путь к cookies JSON.", reply_markup=agent._main_keyboard())
        return
    cookie_file = Path(cookies_path)
    if not cookie_file.is_absolute():
        cookie_file = PROJECT_ROOT / cookie_file
    if not cookie_file.exists():
        await update.message.reply_text(f"Файл не найден: {cookie_file}", reply_markup=agent._main_keyboard())
        return

    cmd = [
        "python3",
        "scripts/browser_session_import.py",
        "--service",
        service,
        "--cookies-file",
        str(cookie_file),
    ]
    if verify:
        cmd.append("--verify")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    output = (out_b or b"").decode("utf-8", errors="ignore").strip()
    if int(proc.returncode or 0) == 0:
        try:
            agent._auth_broker.mark_authenticated(
                service,
                method="cookie_import",
                detail="auth_cookie_import_ok",
                ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800),
            )
        except Exception:
            pass
        agent._mark_service_auth_confirmed(service)
        await update.message.reply_text(
            f"Cookie-импорт выполнен: {service}.\n{output[:1200]}",
            reply_markup=agent._main_keyboard(),
        )
        return

    agent._auth_broker.mark_failed(service, detail=f"auth_cookie_import_failed_rc={int(proc.returncode or 0)}")
    await update.message.reply_text(
        f"Cookie-импорт не удался: {service}\n{output[:1200]}",
        reply_markup=agent._main_keyboard(),
    )
