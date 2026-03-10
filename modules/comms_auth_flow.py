from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.paths import PROJECT_ROOT
from config.settings import settings


async def verify_service_auth(agent: Any, service: str) -> tuple[bool, str]:
    svc = str(service or "").strip().lower()
    if not svc:
        return False, "service_missing"
    if bool(getattr(settings, "AUTH_PREFER_BROWSER_COOKIE", True)):
        if svc == "gumroad":
            cookie_file = Path("/tmp/gumroad_cookie.txt")
            if cookie_file.exists() and cookie_file.read_text(encoding="utf-8", errors="ignore").strip():
                agent._auth_broker.mark_authenticated(
                    svc,
                    method="cookie_import",
                    detail="gumroad_cookie_file",
                    ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800),
                )
                return True, "Gumroad: cookie-сессия зафиксирована."
        has_storage, detail = agent._has_cookie_storage_state(svc)
        if has_storage:
            agent._auth_broker.mark_authenticated(
                svc,
                method="browser_storage",
                detail=detail,
                ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800),
            )
            return True, f"{svc}: browser storage_state подтверждён ({detail})."
    try:
        cached = agent._auth_broker.get(svc)
        if bool(cached.get("is_valid")) and not agent._requires_strict_auth_verification(svc):
            method = str(cached.get("method") or "cached")
            return True, f"{svc}: сессия подтверждена AuthBroker ({method})."
    except Exception:
        pass
    if svc == "amazon_kdp":
        probe_rc, probe_out = await agent._run_kdp_probe_stable()
        if probe_rc == 0:
            agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="kdp_probe_ok", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
            return True, "Amazon KDP сессия подтверждена."
        has_storage, _ = agent._has_cookie_storage_state("amazon_kdp")
        if has_storage:
            agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="kdp_storage_state", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
            return True, "Amazon KDP: browser storage_state зафиксирован."
        rc, out = await agent._run_kdp_auto_login()
        if rc == 0:
            agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="kdp_auto_login", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
            return True, "Amazon KDP вход подтверждён и сессия сохранена."
        if "OTP_REQUIRED" in out:
            agent._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat()}
            return False, agent._auth_interrupt_prompt("amazon_kdp")
        agent._auth_broker.mark_failed(svc, detail="kdp_verify_failed")
        return False, "Не удалось подтвердить вход Amazon автоматически."
    if svc == "printful":
        try:
            from platforms.printful import PrintfulPlatform

            p = PrintfulPlatform()
            ok = await p.authenticate()
            await p.close()
            if ok:
                agent._auth_broker.mark_authenticated(svc, method="api_key", detail="printful_api_auth", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Printful авторизация подтверждена."
            has_storage, _ = agent._has_cookie_storage_state("printful")
            if has_storage:
                agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="printful_storage_state", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Printful: browser storage_state зафиксирован."
            agent._auth_broker.mark_failed(svc, detail="printful_not_confirmed")
            return False, "Printful авторизация не подтверждена."
        except Exception:
            agent._auth_broker.mark_failed(svc, detail="printful_verify_error")
            return False, "Ошибка проверки Printful."
    if svc == "gumroad":
        mode = str(getattr(settings, "GUMROAD_MODE", "api") or "api").strip().lower()
        if mode in {"browser", "browser_only"}:
            cookie_file = Path("/tmp/gumroad_cookie.txt")
            if cookie_file.exists() and cookie_file.read_text(encoding="utf-8", errors="ignore").strip():
                agent._auth_broker.mark_authenticated(svc, method="cookie_import", detail="gumroad_cookie_file", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Gumroad browser cookie зафиксирован."
            has_storage, detail = agent._has_cookie_storage_state("gumroad")
            if has_storage:
                agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail=detail, ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, f"Gumroad browser storage_state: {detail}."
            agent._auth_broker.mark_failed(svc, detail="gumroad_browser_session_missing")
            return False, "Gumroad browser-сессия не подтверждена."
        try:
            from platforms.gumroad import GumroadPlatform

            p = GumroadPlatform()
            ok = await p.authenticate()
            await p.close()
            if ok:
                agent._auth_broker.mark_authenticated(svc, method="oauth_token", detail="gumroad_api_auth", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
            else:
                agent._auth_broker.mark_failed(svc, detail="gumroad_api_not_confirmed")
            return ok, ("Gumroad авторизация подтверждена." if ok else "Gumroad авторизация не подтверждена.")
        except Exception:
            agent._auth_broker.mark_failed(svc, detail="gumroad_verify_error")
            return False, "Ошибка проверки Gumroad."
    if svc == "twitter":
        mode = str(getattr(settings, "TWITTER_MODE", "api") or "api").strip().lower()
        if mode in {"browser", "browser_only"}:
            has_storage, detail = agent._has_cookie_storage_state("twitter")
            if has_storage:
                return True, f"Twitter/X browser storage_state: {detail}."
            return False, "Twitter/X browser-сессия не подтверждена."
        try:
            from platforms.twitter import TwitterPlatform

            p = TwitterPlatform()
            ok = await p.authenticate()
            await p.close()
            if ok:
                agent._auth_broker.mark_authenticated(svc, method="oauth_token", detail="twitter_api_auth", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Twitter/X авторизация подтверждена."
            agent._auth_broker.mark_failed(svc, detail="twitter_api_not_confirmed")
            return False, "Twitter/X API пока не подтверждает вход. Зафиксировал ручную авторизацию."
        except Exception:
            agent._auth_broker.mark_failed(svc, detail="twitter_verify_error")
            return False, "Twitter/X API проверка недоступна. Зафиксировал ручную авторизацию."
    if svc == "etsy":
        try:
            from platforms.etsy import EtsyPlatform

            p = EtsyPlatform()
            ok = await p.authenticate()
            await p.close()
            if ok:
                agent._auth_broker.mark_authenticated(svc, method="oauth_token", detail="etsy_api_auth", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Etsy авторизация подтверждена."
            mode = str(getattr(settings, "ETSY_MODE", "api") or "api").lower()
            if mode in {"browser", "browser_only"}:
                has_storage, _ = agent._has_cookie_storage_state("etsy")
                if has_storage:
                    agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="etsy_storage_state", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                    return True, "Etsy: browser storage_state зафиксирован."
                rc, out = await agent._run_etsy_auto_login()
                if rc == 0:
                    agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="etsy_auto_login", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                    return True, "Etsy browser-сессия захвачена автоматически."
                low = str(out or "").lower()
                if "otp_required" in low or "challenge" in low or "captcha" in low or "datadome" in low:
                    agent._auth_broker.mark_failed(svc, detail="etsy_challenge")
                    return False, "Etsy challenge/captcha: нужен ручной server-capture сессии."
                agent._auth_broker.mark_failed(svc, detail="etsy_auto_login_failed")
                return False, "Etsy browser-сессия не подтверждена. Авто-вход не прошёл."
            agent._auth_broker.mark_failed(svc, detail="etsy_api_not_confirmed")
            return False, "Etsy API не подтвердил вход. Зафиксировал ручную авторизацию."
        except Exception:
            mode = str(getattr(settings, "ETSY_MODE", "api") or "api").lower()
            if mode in {"browser", "browser_only"}:
                agent._auth_broker.mark_failed(svc, detail="etsy_browser_check_error")
                return False, "Etsy browser-проверка недоступна."
            agent._auth_broker.mark_failed(svc, detail="etsy_api_check_error")
            return False, "Etsy API проверка недоступна. Зафиксировал ручную авторизацию."
    if svc == "kofi":
        try:
            from platforms.kofi import KofiPlatform

            p = KofiPlatform()
            ok = await p.authenticate()
            await p.close()
            if ok:
                agent._auth_broker.mark_authenticated(svc, method="api_key", detail="kofi_api_auth", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Ko-fi авторизация подтверждена."
            has_storage, _ = agent._has_cookie_storage_state("kofi")
            if has_storage:
                agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail="kofi_storage_state", ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
                return True, "Ko-fi: browser storage_state зафиксирован."
            agent._auth_broker.mark_failed(svc, detail="kofi_not_confirmed")
            return False, "Ko-fi авторизация не подтверждена."
        except Exception:
            agent._auth_broker.mark_failed(svc, detail="kofi_verify_error")
            return False, "Ko-fi проверка недоступна."
    if svc == "reddit":
        has_storage, detail = agent._has_cookie_storage_state("reddit")
        if has_storage:
            agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail=detail, ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
            return True, f"Reddit browser storage_state: {detail}."
        agent._auth_broker.mark_failed(svc, detail="reddit_browser_session_missing")
        return False, "Reddit в browser_only режиме; нужен storage_state после входа."
    has_storage, detail = agent._has_cookie_storage_state(svc)
    if has_storage:
        agent._auth_broker.mark_authenticated(svc, method="browser_storage", detail=detail, ttl_sec=int(getattr(settings, "AUTH_SESSION_TTL_SEC", 10800) or 10800))
        return True, f"{svc}: browser storage_state подтверждён."
    if agent._is_manual_auth_service(svc):
        title, _ = agent._service_auth_meta(svc)
        return False, f"{title}: подтверждение только вручную (browser-only)."
    return False, "Проверка сервиса не реализована."


async def start_service_auth_flow(agent: Any, service: str, send_reply, with_button: bool = True) -> bool:
    svc = str(service or "").strip().lower()
    if not svc:
        return False
    agent._touch_service_context(svc)
    title, auth_url = agent._service_auth_meta(svc)
    if not auth_url:
        return False
    if agent._requires_strict_auth_verification(svc):
        ok = False
        try:
            if svc == "amazon_kdp":
                probe_rc, _ = await agent._run_kdp_probe_stable()
                ok = probe_rc == 0
            else:
                ok, _ = await verify_service_auth(agent, svc)
        except Exception:
            ok = False
        if ok:
            agent._mark_service_auth_confirmed(svc)
            await send_reply(f"{title}: активная сессия уже подтверждена, повторный логин не требуется.")
            return True
        agent._clear_service_auth_confirmed(svc)
    if svc in {"etsy", "amazon_kdp", "kofi", "printful"}:
        rc, out = await agent._run_remote_auth_session(svc, "start")
        if rc == 0:
            kv = agent._parse_remote_kv(out)
            remote_url = kv.get("remote_url", "")
            direct_url = kv.get("direct_url", "")
            vnc_password = kv.get("vnc_password", "")
            agent._pending_service_auth[svc] = {
                "service": svc,
                "url": remote_url or direct_url or auth_url,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "mode": "remote",
            }
            msg = (
                f"Запускаю вход {title} в удалённом браузере сервера.\n"
                f"Ссылка: {remote_url or direct_url or auth_url}\n"
                f"Пароль: {vnc_password or f'(см. /auth {svc} remote)'}\n"
                "После входа нажми «Я вошел»."
            )
            if direct_url:
                msg += f"\nРезервная ссылка: {direct_url}"
            if with_button and (remote_url or direct_url or auth_url):
                kb = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton(f"Открыть вход {title}", url=(remote_url or direct_url or auth_url))],
                        [InlineKeyboardButton("Я вошел", callback_data=f"auth_done:{svc}")],
                        [InlineKeyboardButton("Отмена", callback_data=f"auth_cancel:{svc}")],
                    ]
                )
                await send_reply(msg, kb)
            else:
                await send_reply(msg)
            return True
    last = agent._service_auth_confirmed.get(svc, "")
    if last and not agent._requires_strict_auth_verification(svc):
        try:
            dt = datetime.fromisoformat(last)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
            if age_sec < 12 * 3600:
                await send_reply(f"{title}: вход уже подтверждён недавно. Можешь работать без повторного логина.")
                return True
        except Exception:
            pass
    payload = {
        "service": svc,
        "url": auth_url,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    agent._pending_service_auth[svc] = payload
    if with_button:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(f"Войти в {title}", url=auth_url)],
                [InlineKeyboardButton("Я вошел", callback_data=f"auth_done:{svc}")],
                [InlineKeyboardButton("Отмена", callback_data=f"auth_cancel:{svc}")],
            ]
        )
        await send_reply(f"Открой вход в {title}, авторизуйся, затем нажми «Я вошел».", kb)
        return True
    await send_reply(f"Ссылка для входа в {title}: {auth_url}\nПосле входа ответь: «я вошел».")
    return True


async def handle_kdp_login_flow(agent: Any, text: str, send_reply, with_button: bool = False) -> bool:
    maybe_otp = agent._extract_otp_code(text)
    if agent._pending_kdp_otp and maybe_otp:
        await send_reply("Код получен. Подтверждаю вход в Amazon KDP...")
        await agent._cleanup_browser_runtime()
        try:
            pre_probe_rc, _ = await agent._run_kdp_probe_stable()
        except Exception:
            pre_probe_rc = 1
        if pre_probe_rc == 0:
            agent._pending_kdp_otp = None
            agent._mark_service_auth_confirmed("amazon_kdp")
            agent._pending_service_auth.pop("amazon_kdp", None)
            await send_reply("Готово: вход в KDP подтвержден (live-check OK).")
            return True
        prepared_mode = bool((agent._pending_kdp_otp or {}).get("prepared", False)) or agent._kdp_preauth_ready()
        attempts: list[tuple[str, tuple[int, str]]] = []
        if prepared_mode:
            attempts.append(("submit_otp_prepared", await agent._run_kdp_submit_otp(maybe_otp)))
            if attempts[-1][1][0] != 0:
                prep_rc, _prep_out = await agent._run_kdp_prepare_otp()
                if prep_rc == 0 or agent._kdp_prepare_has_mfa_evidence(_prep_out):
                    attempts.append(("submit_otp_refreshed", await agent._run_kdp_submit_otp(maybe_otp)))
        if not attempts:
            attempts.append(("auto_login", await agent._run_kdp_auto_login(otp_code=maybe_otp)))
        for _mode, (rc_try, _out_try) in attempts:
            if rc_try == 0:
                agent._pending_kdp_otp = None
                agent._mark_service_auth_confirmed("amazon_kdp")
                agent._pending_service_auth.pop("amazon_kdp", None)
                await send_reply("Готово: вход в KDP подтвержден, сессия сохранена.")
                return True
            try:
                probe_rc_try, _ = await agent._run_kdp_probe_stable()
            except Exception:
                probe_rc_try = 1
            if probe_rc_try == 0:
                agent._pending_kdp_otp = None
                agent._mark_service_auth_confirmed("amazon_kdp")
                agent._pending_service_auth.pop("amazon_kdp", None)
                await send_reply("Готово: вход в KDP подтвержден (live-check OK).")
                return True
        out = attempts[0][1][1] if attempts else ""
        out2 = attempts[-1][1][1] if attempts else ""
        agent._pending_kdp_otp = {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "retry": True,
            "prepared": prepared_mode,
        }
        msg = "Код не подтвердился. Пришли новый 6-значный код (без /kdp_login)."
        low_all = f"{str(out or '').lower()}\n{str(out2 or '').lower()}"
        if "otp_rejected" in low_all or "expired" in low_all or "invalid" in low_all:
            msg = "Код отклонен или истек. Пришли новый 6-значный код из аутентификатора."
        await send_reply(msg)
        return True
    if agent._is_kdp_login_request(text):
        agent._touch_service_context("amazon_kdp")
        await send_reply("Готовлю окно входа Amazon KDP...")
        await agent._cleanup_browser_runtime()
        attempts = 0
        try:
            rc, out = await agent._run_kdp_prepare_otp()
            attempts += 1
        except Exception as e:
            rc, out = 1, str(e)
            attempts += 1
        low = str(out or "").lower()
        while rc != 0 and attempts < 5 and ("prepare_otp_exception" in low or "chromium launch failed" in low or "error:" in low):
            try:
                rc, out = await agent._run_kdp_prepare_otp()
                attempts += 1
            except Exception as e:
                rc, out = 1, str(e)
                attempts += 1
            low = str(out or "").lower()
        if rc == 0 or agent._kdp_prepare_has_mfa_evidence(out) or "otp_required" in str(out or "").lower():
            agent._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat(), "prepared": True}
            await send_reply(agent._auth_interrupt_prompt("amazon_kdp"))
            return True
        if "prepare_otp_exception" in low or "chromium launch failed" in low or "error:" in low:
            agent._pending_kdp_otp = {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "forced": True,
            }
            await send_reply(
                "Нужен 6-значный код Amazon Authenticator. "
                "Пришли 6-значный код одним сообщением, и я попробую завершить вход."
            )
            return True
        rc2, out2 = await agent._run_kdp_auto_login()
        if rc2 == 0:
            agent._mark_service_auth_confirmed("amazon_kdp")
            await send_reply("Готово: вход в KDP подтвержден, сессия сохранена.")
            return True
        if "otp_required" in str(out2 or "").lower():
            agent._pending_kdp_otp = {"requested_at": datetime.now(timezone.utc).isoformat()}
            await send_reply(agent._auth_interrupt_prompt("amazon_kdp"))
            return True
        await send_reply("Не удалось запустить вход KDP автоматически. Попробуй еще раз.")
        return True
    return False
