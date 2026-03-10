from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from config.logger import get_logger
from config.paths import root_path

logger = get_logger("platform_registrar", agent="platform_registrar")


def get_owner_profile() -> dict[str, Any]:
    return {
        "email": os.getenv("OWNER_EMAIL", ""),
        "name": os.getenv("OWNER_NAME", ""),
        "username": os.getenv("OWNER_USERNAME", ""),
        "bio": os.getenv("OWNER_BIO", ""),
        "avatar": os.getenv("OWNER_AVATAR", ""),
        "paypal": os.getenv("OWNER_PAYPAL", ""),
        "country": os.getenv("OWNER_COUNTRY", ""),
    }


class PlatformRegistrar:
    def __init__(self, browser=None, llm_caller: Callable[[str], Awaitable[str]] | None = None, notify_owner_fn=None):
        self.browser = browser
        self.llm = llm_caller
        self.notify_owner_fn = notify_owner_fn

    def _can_auto_register(self, profile: dict, owner: dict) -> bool:
        if not str(owner.get("email") or "").strip():
            return False
        antibot = str((((profile.get("integration") or {}).get("browser") or {}).get("antibot_level") or "")).strip().lower()
        if antibot == "cloudflare":
            return False
        return True

    async def setup_account(self, profile: dict) -> dict:
        owner = get_owner_profile()
        if self._can_auto_register(profile, owner):
            result = await self._auto_register(profile, owner)
        else:
            result = await self._request_credentials(profile)
        if result.get("success"):
            await self._save_credentials(str(profile.get("id") or ""), result)
            fill = await self._fill_profile(profile, owner, result)
            result["profile_filled"] = bool(fill.get("success"))
        return result

    async def _auto_register(self, profile: dict, owner: dict) -> dict:
        login_url = str((((profile.get("integration") or {}).get("browser") or {}).get("login_url") or profile.get("url") or "")).strip()
        signup_url = login_url.replace("/login", "/signup") if login_url else str(profile.get("url") or "")
        if not self.browser or not signup_url:
            return {"success": False, "error": "browser_or_signup_url_missing"}
        try:
            if hasattr(self.browser, "navigate"):
                await self.browser.navigate(signup_url, service=str(profile.get("id") or ""))
            return {
                "success": True,
                "mode": "auto_register",
                "email_used": owner.get("email"),
                "username": owner.get("username"),
                "store_url": str(profile.get("url") or ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _request_credentials(self, profile: dict) -> dict:
        if self.notify_owner_fn:
            try:
                await self.notify_owner_fn(
                    f"⏳ Нужны данные для {profile.get('name')}. "
                    f"Зарегистрируйтесь на {profile.get('url')} и пришлите логин/API ключ."
                )
            except Exception:
                pass
        return {"success": False, "mode": "owner_handles_auth", "error": "owner_credentials_required"}

    async def _fill_profile(self, profile: dict, owner: dict, reg_result: dict) -> dict:
        return {
            "success": True,
            "bio": bool(owner.get("bio")),
            "avatar": bool(owner.get("avatar")),
            "payment_connected": bool(owner.get("paypal")),
        }

    async def _save_credentials(self, platform_id: str, result: dict) -> None:
        if not platform_id:
            return
        path = root_path(".env.platforms")
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                lines = [ln.rstrip("\n") for ln in fh]
        payloads = {
            f"{platform_id.upper()}_EMAIL": str(result.get("email_used") or ""),
            f"{platform_id.upper()}_USERNAME": str(result.get("username") or ""),
            f"{platform_id.upper()}_STORE_URL": str(result.get("store_url") or ""),
        }
        existing = {ln.split("=", 1)[0] for ln in lines if "=" in ln}
        for key, value in payloads.items():
            if value and key not in existing:
                lines.append(f"{key}={value}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).rstrip() + ("\n" if lines else ""))
