from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.paths import root_path
from modules.browser_proxy_pool import select_proxy_for_service


@dataclass(frozen=True)
class BrowserRuntimeProfile:
    service: str
    session_scope: str
    storage_state_path: str
    persistent_profile_dir: str
    screenshot_first_default: bool
    anti_bot_humanize: bool
    headless_preferred: bool
    llm_navigation_allowed: bool
    requires_profile_completion: bool
    profile_completion_route: str
    otp_supported: bool
    otp_prompt: str
    proxy: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "session_scope": self.session_scope,
            "storage_state_path": self.storage_state_path,
            "persistent_profile_dir": self.persistent_profile_dir,
            "screenshot_first_default": self.screenshot_first_default,
            "anti_bot_humanize": self.anti_bot_humanize,
            "headless_preferred": self.headless_preferred,
            "llm_navigation_allowed": self.llm_navigation_allowed,
            "requires_profile_completion": self.requires_profile_completion,
            "profile_completion_route": self.profile_completion_route,
            "otp_supported": self.otp_supported,
            "otp_prompt": self.otp_prompt,
            "proxy": dict(self.proxy or {}) if self.proxy else None,
        }


_SERVICE_MAP: dict[str, dict[str, Any]] = {
    "amazon_kdp": {
        "storage": "runtime/kdp_storage_state.json",
        "profile_dir": "runtime/browser_profiles/amazon_kdp",
        "scope": "marketplace_publishing",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://kdp.amazon.com/account",
        "otp_supported": True,
        "otp_prompt": "Нужен 6-значный код Amazon Authenticator. Отправь 6 цифр одним сообщением.",
    },
    "etsy": {
        "storage": "runtime/etsy_storage_state.json",
        "profile_dir": "runtime/browser_profiles/etsy",
        "scope": "marketplace_listing",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://www.etsy.com/your/account",
        "otp_supported": False,
        "otp_prompt": "Для Etsy нужен ручной вход или подтверждение в браузерной сессии.",
    },
    "gumroad": {
        "storage": "runtime/gumroad_storage_state.json",
        "profile_dir": "runtime/browser_profiles/gumroad",
        "scope": "digital_product_listing",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": False,
        "profile_route": "https://app.gumroad.com/settings",
        "otp_supported": True,
        "otp_prompt": "Для Gumroad нужен код двухфакторной проверки. Отправь код одним сообщением.",
    },
    "kofi": {
        "storage": "runtime/kofi_storage_state.json",
        "profile_dir": "runtime/browser_profiles/kofi",
        "scope": "creator_storefront",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://ko-fi.com/manage/profile",
        "otp_supported": False,
        "otp_prompt": "Для Ko-fi нужен ручной вход в browser-сессии и сохранение storage_state.",
    },
    "printful": {
        "storage": "runtime/printful_storage_state.json",
        "profile_dir": "runtime/browser_profiles/printful",
        "scope": "print_on_demand",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://www.printful.com/dashboard/store/connect",
        "otp_supported": False,
        "otp_prompt": "Для Printful нужен ручной вход в browser-сессии и сохранение storage_state.",
    },
    "reddit": {
        "storage": "runtime/reddit_storage_state.json",
        "profile_dir": "runtime/browser_profiles/reddit",
        "scope": "community_posting",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://www.reddit.com/settings/profile",
        "otp_supported": False,
        "otp_prompt": "Для Reddit нужен ручной вход в browser-сессии и сохранение storage_state.",
    },
    "twitter": {
        "storage": "runtime/twitter_storage_state.json",
        "profile_dir": "runtime/browser_profiles/twitter",
        "scope": "social_posting",
        "screenshot_first": False,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://x.com/settings/profile",
        "otp_supported": False,
        "otp_prompt": "Для X нужен ручной вход или код подтверждения, если платформа его запросит.",
    },
    "pinterest": {
        "storage": "runtime/pinterest_storage_state.json",
        "profile_dir": "runtime/browser_profiles/pinterest",
        "scope": "social_pinning",
        "screenshot_first": True,
        "humanize": True,
        "headless": True,
        "llm_navigation_allowed": True,
        "profile_completion": True,
        "profile_route": "https://www.pinterest.com/settings/profile/",
        "otp_supported": False,
        "otp_prompt": "Для Pinterest нужен ручной вход в browser-сессии и сохранение storage_state.",
    },
}


def browser_capability_map() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in _SERVICE_MAP.items()}


def storage_state_path_for_service(service: str) -> Path | None:
    data = _SERVICE_MAP.get(str(service or "").strip().lower())
    if not data:
        return None
    return Path(root_path(str(data["storage"])))


def get_browser_runtime_profile(service: str) -> dict[str, Any]:
    svc = str(service or "").strip().lower()
    data = _SERVICE_MAP.get(svc)
    proxy = select_proxy_for_service(svc)
    if not data:
        return BrowserRuntimeProfile(
            service=svc,
            session_scope="generic_browser",
            storage_state_path="",
            persistent_profile_dir=str(root_path("runtime", "browser_profiles", "generic")),
            screenshot_first_default=False,
            anti_bot_humanize=True,
            headless_preferred=True,
            llm_navigation_allowed=False,
            requires_profile_completion=False,
            profile_completion_route="",
            otp_supported=False,
            otp_prompt="",
            proxy=proxy,
        ).to_dict()
    return BrowserRuntimeProfile(
        service=svc,
        session_scope=str(data["scope"]),
        storage_state_path=str(root_path(str(data["storage"]))),
        persistent_profile_dir=str(root_path(str(data["profile_dir"]))),
        screenshot_first_default=bool(data["screenshot_first"]),
        anti_bot_humanize=bool(data["humanize"]),
        headless_preferred=bool(data["headless"]),
        llm_navigation_allowed=bool(data.get("llm_navigation_allowed", False)),
        requires_profile_completion=bool(data["profile_completion"]),
        profile_completion_route=str(data["profile_route"]),
        otp_supported=bool(data["otp_supported"]),
        otp_prompt=str(data["otp_prompt"]),
        proxy=proxy,
    ).to_dict()


def detect_auth_interrupt(service: str, *, url: str = "", body_text: str = "") -> dict[str, Any] | None:
    svc = str(service or "").strip().lower()
    text = f"{str(url or '')}\n{str(body_text or '')}".lower()
    if svc == "amazon_kdp" and any(tok in text for tok in ("ap/mfa", "two-step verification", "otp", "authenticator app")):
        profile = get_browser_runtime_profile(svc)
        return {
            "type": "otp_required",
            "service": svc,
            "requires_owner_code": True,
            "prompt": profile.get("otp_prompt") or "Нужен код двухфакторной проверки.",
        }
    if svc == "gumroad" and any(tok in text for tok in ("two-factor", "otp", "verification code")):
        profile = get_browser_runtime_profile(svc)
        return {
            "type": "otp_required",
            "service": svc,
            "requires_owner_code": True,
            "prompt": profile.get("otp_prompt") or "Нужен код двухфакторной проверки.",
        }
    if svc in {"etsy", "kofi", "printful", "reddit", "pinterest", "twitter"} and any(
        tok in text for tok in ("log in", "sign in", "just a moment", "verify", "challenge", "security check")
    ):
        profile = get_browser_runtime_profile(svc)
        return {
            "type": "interactive_auth_required",
            "service": svc,
            "requires_owner_code": False,
            "prompt": profile.get("otp_prompt") or "Нужен ручной вход в browser-сессии.",
        }
    return None


def build_auth_interrupt_output(service: str, *, url: str = "", body_text: str = "", screenshot_path: str = "") -> dict[str, Any] | None:
    interrupt = detect_auth_interrupt(service, url=url, body_text=body_text)
    if not interrupt:
        return None
    profile = get_browser_runtime_profile(service)
    return {
        "auth_interrupt": interrupt,
        "browser_runtime_profile": profile,
        "needs_manual_auth": True,
        "screenshot": str(screenshot_path or ""),
        "url": str(url or ""),
    }


def get_profile_completion_runbook(service: str) -> dict[str, Any]:
    svc = str(service or "").strip().lower()
    profile = get_browser_runtime_profile(svc)
    routes = {
        "amazon_kdp": ["tax/payment identity", "author/publisher details", "rights/pricing prerequisites"],
        "etsy": ["shop manager profile", "seller details", "listing category/type prerequisites"],
        "gumroad": ["creator profile basics", "payout/settings sanity"],
        "kofi": ["shop/profile basics", "payment method"],
        "printful": ["store connection", "billing/settings"],
        "reddit": ["profile basics", "community-specific flair/rules check"],
        "twitter": ["profile basics", "account reputation sanity"],
        "pinterest": ["business profile basics", "website claim/link"],
    }
    return {
        "service": svc,
        "requires_profile_completion": bool(profile.get("requires_profile_completion")),
        "route": str(profile.get("profile_completion_route") or ""),
        "required_steps": routes.get(svc, []),
    }
