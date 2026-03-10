from __future__ import annotations

import json
import subprocess
import re
from typing import Any, Awaitable, Callable

import aiohttp

from config.logger import get_logger

logger = get_logger("integration_detector", agent="integration_detector")

DETECT_PROMPT = """
Проанализируй данные о платформе и определи лучший способ интеграции.

ДАННЫЕ О ПЛАТФОРМЕ:
{platform_data}

Ответь JSON:
{{
  "method": "api|browser|hybrid",
  "rationale": "почему этот метод",
  "api_confidence": 0.0,
  "auth_type": "oauth2|api_key|basic|none|app_password|email",
  "auth_url": null,
  "base_url": null,
  "key_endpoints": {{}},
  "browser_needed_for": [],
  "antibot_level": "low|medium|high|cloudflare",
  "existing_python_lib": null,
  "setup_steps": []
}}
Только JSON.
""".strip()

KNOWN_PLATFORMS = {
    "gumroad": {"method": "api", "auth": "api_key", "base": "https://api.gumroad.com/v2", "lib": None},
    "etsy": {"method": "api", "auth": "oauth2", "base": "https://openapi.etsy.com/v3", "lib": None},
    "patreon": {"method": "api", "auth": "oauth2", "base": "https://www.patreon.com/api/oauth2/v2", "lib": None},
    "ko-fi": {"method": "hybrid", "auth": "api_key", "base": "https://ko-fi.com/api", "lib": None},
    "medium": {"method": "api", "auth": "api_key", "base": "https://api.medium.com/v1", "lib": None},
    "wordpress": {"method": "api", "auth": "app_password", "base": "/wp-json/wp/v2", "lib": None},
    "redbubble": {"method": "browser", "auth": "email", "base": None, "lib": None},
    "teepublic": {"method": "browser", "auth": "email", "base": None, "lib": None},
    "sellfy": {"method": "api", "auth": "oauth2", "base": "https://api.sellfy.com/v1", "lib": None},
    "shopify": {"method": "api", "auth": "api_key", "base": "https://{shop}.myshopify.com/admin/api", "lib": "shopify"},
}


class IntegrationDetector:
    def __init__(self, llm_caller: Callable[[str], Awaitable[str]] | None = None, browser=None):
        self.llm = llm_caller
        self.browser = browser

    async def detect(self, platform_profile: dict) -> dict:
        name = str(platform_profile.get("id") or platform_profile.get("name") or "").lower()
        for known_name, config in KNOWN_PLATFORMS.items():
            if known_name in name:
                result = self._build_result(config, platform_profile)
                result["api_verified"] = await self._verify_api(result.get("base_url"))
                return result
        result = await self._llm_detect(platform_profile)
        if result.get("method") in {"api", "hybrid"} and result.get("base_url"):
            verified = await self._verify_api(result["base_url"])
            result["api_verified"] = verified
            if not verified:
                result["method"] = "browser"
                result["rationale"] = str(result.get("rationale") or "") + " (API verify failed, fallback to browser)"
        if result.get("existing_python_lib"):
            result["lib_available"] = self._check_pip(str(result["existing_python_lib"]))
        return result

    async def _llm_detect(self, profile: dict) -> dict:
        if not self.llm:
            return {"method": "browser", "rationale": "No LLM detector configured", "browser_needed_for": ["registration", "profile_setup"], "setup_steps": []}
        prompt = DETECT_PROMPT.format(platform_data=json.dumps(profile, ensure_ascii=False)[:3000])
        try:
            raw = await self.llm(prompt)
            m = re.search(r"\{.*\}", raw or "", re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"method": "browser", "rationale": "LLM parse failed, defaulting to browser", "browser_needed_for": ["registration", "profile_setup"], "setup_steps": []}

    async def _verify_api(self, base_url: str | None) -> bool:
        if not base_url:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(base_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return r.status in {200, 401, 403, 422}
        except Exception:
            return False

    def _check_pip(self, lib_name: str) -> bool:
        r = subprocess.run(["pip", "show", lib_name], capture_output=True)
        return r.returncode == 0

    def _build_result(self, config: dict, profile: dict) -> dict:
        return {
            "method": config["method"],
            "auth_type": config["auth"],
            "base_url": config.get("base"),
            "existing_python_lib": config.get("lib"),
            "api_verified": True,
            "rationale": "Known platform configuration",
            "browser_needed_for": ["registration", "profile_setup"],
            "antibot_level": "medium",
            "setup_steps": [f"Get {config['auth']} credentials for {profile.get('name') or profile.get('id')}"],
            "key_endpoints": {},
        }
