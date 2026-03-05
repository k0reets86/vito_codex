"""Balance Checker — checks account balances across all VITO services.

Supports:
  - Anti-Captcha ($)
  - Anthropic (usage/credit)
  - OpenAI (usage/credit)
  - Replicate ($)
  - VITO internal spend tracking (FinancialController)

Usage:
    checker = BalanceChecker()
    report = await checker.check_all()
    text = checker.format_report(report)
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from modules.network_utils import network_available, network_status

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("vito.balance_checker")

# Thresholds for "low balance" warnings
LOW_BALANCE_THRESHOLDS = {
    "anti_captcha": 2.0,    # $2 — ~1000 solves
    "anthropic": 5.0,       # $5 credit remaining
    "openai": 5.0,          # $5 credit remaining
    "replicate": 2.0,       # $2
}


@dataclass
class ServiceBalance:
    name: str
    balance: Optional[float] = None
    currency: str = "USD"
    is_low: bool = False
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


class BalanceChecker:
    """Check balances across all VITO external services."""

    def _env_keys(self) -> set[str]:
        """Return all keys present in .env file."""
        env_path = Path(__file__).resolve().parent.parent / ".env"
        keys = set()
        try:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if not line or line.strip().startswith("#") or "=" not in line:
                        continue
                    k = line.split("=", 1)[0].strip()
                    if k:
                        keys.add(k)
        except Exception:
            pass
        return keys

    def _service_key_map(self) -> dict[str, list[str]]:
        """Map service names to possible env keys."""
        return {
            "anticaptcha": ["ANTI_CAPTCHA_KEY", "ANTICAPTCHA_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "replicate": ["REPLICATE_API_TOKEN"],
            "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "openrouter": ["OPENROUTER_API_KEY"],
            "perplexity": ["PERPLEXITY_API_KEY"],
            "gumroad": ["GUMROAD_API_KEY", "GUMROAD_OAUTH_TOKEN", "GUMROAD_REFRESH_TOKEN"],
            "kofi": ["KOFI_API_KEY"],
            "etsy": ["ETSY_API_KEY", "ETSY_API_SECRET", "ETSY_SHARED_SECRET"],
            "printful": ["PRINTFUL_API_KEY"],
            "medium": ["MEDIUM_API_KEY", "MEDIUM_ACCESS_TOKEN"],
            "wordpress": ["WORDPRESS_API_KEY", "WORDPRESS_USER", "WORDPRESS_PASS"],
            "twitter": [
                "TWITTER_BEARER_TOKEN", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
                "TWITTER_CLIENT_SECRET", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
            ],
            "cloudinary": ["CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"],
            "bfl": ["BFL_API_KEY"],
            "wavespeed": ["WAVESPEED_API_KEY"],
            "telegram": ["TELEGRAM_BOT_TOKEN"],
            "gmail": ["GMAIL_PASSWORD"],
            "google": ["GOOGLE_API_KEY"],
            "shopify": ["SHOPIFY_ACCESS_TOKEN", "SHOPIFY_API_KEY"],
            "pinterest": ["PINTEREST_ACCESS_TOKEN", "PINTEREST_APP_ID"],
            "instagram": ["INSTAGRAM_ACCESS_TOKEN", "META_APP_ID"],
            "threads": ["THREADS_ACCESS_TOKEN", "META_APP_ID"],
            "linkedin": ["LINKEDIN_ACCESS_TOKEN", "LINKEDIN_CLIENT_ID"],
        }

    async def check_all(self, include_env_keys: bool = False) -> list[ServiceBalance]:
        """Check all service balances. Returns list of ServiceBalance."""
        results = []

        net = network_status()
        if not net["ok"]:
            # Fast path: no DNS/network — report network_unavailable for configured services
            env_keys = self._env_keys()
            for service, keys in self._service_key_map().items():
                present = any(os.getenv(k, "") for k in keys)
                if present:
                    results.append(ServiceBalance(
                        name=service,
                        error=f"network_unavailable:{net['reason']}",
                        details={"status": "network_unavailable", "reason": net["reason"]},
                    ))
            # Optionally show raw env keys if explicitly requested
            if include_env_keys:
                for key in sorted(env_keys):
                    if key.endswith("_KEY") or key.endswith("_TOKEN") or key.endswith("_SECRET") or key.endswith("_PASSWORD"):
                        if os.getenv(key, ""):
                            results.append(ServiceBalance(
                                name=key.lower(),
                                details={"status": "key_present", "note": "network_unavailable", "source": "env_key"},
                            ))
            return results

        # Check each service sequentially (8GB RAM constraint)
        checkers = [
            self._check_anticaptcha,
            self._check_anthropic,
            self._check_openai,
            self._check_replicate,
            self._check_gemini,
            self._check_openrouter,
            self._check_perplexity,
            self._check_gumroad,
            self._check_kofi,
            self._check_etsy,
            self._check_printful,
            self._check_medium,
            self._check_wordpress,
            self._check_twitter,
            self._check_cloudinary,
            self._check_bfl,
            self._check_wavespeed,
        ]

        for checker in checkers:
            try:
                result = await checker()
                results.append(result)
            except Exception as e:
                logger.warning(f"Balance check failed for {checker.__name__}: {e}")
                results.append(ServiceBalance(
                    name=checker.__name__.replace("_check_", ""),
                    error=str(e),
                ))

        # Add services that have keys but no dedicated balance endpoint
        known_names = {b.name for b in results}
        env_keys = self._env_keys()
        for service, keys in self._service_key_map().items():
            if service in known_names:
                continue
            present = any(os.getenv(k, "") for k in keys)
            if present:
                results.append(ServiceBalance(
                    name=service,
                    details={"status": "active", "note": "no balance endpoint", "source": "service_map"},
                ))

        # Optionally add raw env keys (diagnostic)
        if include_env_keys:
            for key in sorted(env_keys):
                if key.endswith("_KEY") or key.endswith("_TOKEN") or key.endswith("_SECRET") or key.endswith("_PASSWORD"):
                    name = key.lower()
                    if name in known_names:
                        continue
                    if os.getenv(key, ""):
                        results.append(ServiceBalance(
                            name=name,
                            details={
                                "status": "key_present",
                                "note": "validation_not_implemented",
                                "source": "env_key",
                            },
                        ))
                    else:
                        results.append(ServiceBalance(
                            name=name,
                            error=f"{key} not set",
                            details={"source": "env_key"},
                        ))

        return results

    async def _check_gemini(self) -> ServiceBalance:
        key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            return ServiceBalance(name="gemini", error="GEMINI_API_KEY/GOOGLE_API_KEY not set")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1/models?key={key}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    return ServiceBalance(name="gemini", details={"status": "active"})
                if resp.status_code == 401:
                    return ServiceBalance(name="gemini", error="Invalid API key")
                return ServiceBalance(name="gemini", error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ServiceBalance(name="gemini", error=str(e))

    async def _check_openrouter(self) -> ServiceBalance:
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            return ServiceBalance(name="openrouter", error="OPENROUTER_API_KEY not set")
        try:
            import requests
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return ServiceBalance(name="openrouter", details={"status": "active"})
            if resp.status_code == 401:
                return ServiceBalance(name="openrouter", error="Invalid API key")
            return ServiceBalance(name="openrouter", error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ServiceBalance(name="openrouter", error=str(e))

    async def _check_perplexity(self) -> ServiceBalance:
        key = os.getenv("PERPLEXITY_API_KEY", "")
        if not key:
            return ServiceBalance(name="perplexity", error="PERPLEXITY_API_KEY not set")
        # No official balance endpoint known in codebase
        return ServiceBalance(name="perplexity", details={"status": "active", "note": "no balance endpoint"})

    async def _check_gumroad(self) -> ServiceBalance:
        from platforms.gumroad import GumroadPlatform
        return await self._check_platform_auth("gumroad", GumroadPlatform)

    async def _check_kofi(self) -> ServiceBalance:
        from platforms.kofi import KofiPlatform
        return await self._check_platform_auth("kofi", KofiPlatform)

    async def _check_etsy(self) -> ServiceBalance:
        from platforms.etsy import EtsyPlatform
        return await self._check_platform_auth("etsy", EtsyPlatform)

    async def _check_printful(self) -> ServiceBalance:
        from platforms.printful import PrintfulPlatform
        return await self._check_platform_auth("printful", PrintfulPlatform)

    async def _check_medium(self) -> ServiceBalance:
        from platforms.medium import MediumPlatform
        return await self._check_platform_auth("medium", MediumPlatform)

    async def _check_wordpress(self) -> ServiceBalance:
        from platforms.wordpress import WordPressPlatform
        return await self._check_platform_auth("wordpress", WordPressPlatform)

    async def _check_twitter(self) -> ServiceBalance:
        from platforms.twitter import TwitterPlatform
        return await self._check_platform_auth("twitter", TwitterPlatform)

    async def _check_platform_auth(self, service_name: str, platform_cls) -> ServiceBalance:
        p = None
        try:
            p = platform_cls()
            ok = await p.authenticate()
            return ServiceBalance(name=service_name, details={"status": "active" if ok else "not_authenticated"})
        except Exception as e:
            return ServiceBalance(name=service_name, error=str(e))
        finally:
            try:
                if p and hasattr(p, "close"):
                    await p.close()
            except Exception:
                pass

    async def _check_cloudinary(self) -> ServiceBalance:
        # No simple validation without signed request
        if not all([os.getenv("CLOUDINARY_CLOUD_NAME", ""), os.getenv("CLOUDINARY_API_KEY", ""), os.getenv("CLOUDINARY_API_SECRET", "")]):
            return ServiceBalance(name="cloudinary", error="CLOUDINARY_* not set")
        return ServiceBalance(name="cloudinary", details={"status": "active", "note": "no balance endpoint"})

    async def _check_bfl(self) -> ServiceBalance:
        key = os.getenv("BFL_API_KEY", "")
        if not key:
            return ServiceBalance(name="bfl", error="BFL_API_KEY not set")
        return ServiceBalance(name="bfl", details={"status": "active", "note": "no balance endpoint"})

    async def _check_wavespeed(self) -> ServiceBalance:
        key = os.getenv("WAVESPEED_API_KEY", "")
        if not key:
            return ServiceBalance(name="wavespeed", error="WAVESPEED_API_KEY not set")
        return ServiceBalance(name="wavespeed", details={"status": "active", "note": "no balance endpoint"})

    async def _check_anticaptcha(self) -> ServiceBalance:
        """Check anti-captcha.com account balance."""
        key = os.getenv("ANTICAPTCHA_KEY", "")
        if not key:
            return ServiceBalance(name="anti_captcha", error="ANTICAPTCHA_KEY not set")

        try:
            from anticaptchaofficial.antinetworking import antiNetworking
            client = antiNetworking()
            client.client_key = key
            balance = client.get_balance()

            if balance is None:
                return ServiceBalance(name="anti_captcha", error=client.err_string)

            bal = float(balance)
            threshold = LOW_BALANCE_THRESHOLDS.get("anti_captcha", 2.0)
            return ServiceBalance(
                name="anti_captcha",
                balance=bal,
                is_low=bal < threshold,
                details={"threshold": threshold},
            )
        except Exception as e:
            return ServiceBalance(name="anti_captcha", error=str(e))

    async def _check_anthropic(self) -> ServiceBalance:
        """Check Anthropic API credit balance via billing API."""
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return ServiceBalance(name="anthropic", error="ANTHROPIC_API_KEY not set")

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Try the billing endpoint
                resp = await client.get(
                    "https://api.anthropic.com/v1/usage",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=10,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # Parse usage data
                    return ServiceBalance(
                        name="anthropic",
                        balance=None,  # Anthropic doesn't expose balance directly
                        details={"status": "active", "raw": data},
                    )
                elif resp.status_code == 401:
                    return ServiceBalance(name="anthropic", error="Invalid API key")
                elif resp.status_code == 404:
                    # Usage endpoint might not exist — just verify key works
                    resp2 = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                        timeout=10,
                    )
                    if resp2.status_code in (200, 529):
                        return ServiceBalance(name="anthropic", details={"status": "active", "note": "key valid, no balance endpoint"})
                    elif resp2.status_code == 401:
                        return ServiceBalance(name="anthropic", error="Invalid API key")
                    elif resp2.status_code == 429:
                        return ServiceBalance(name="anthropic", details={"status": "rate_limited", "note": "key valid but rate limited"})
                    else:
                        return ServiceBalance(name="anthropic", details={"status": f"http_{resp2.status_code}"})
                else:
                    return ServiceBalance(name="anthropic", error=f"HTTP {resp.status_code}")
        except ImportError:
            # Try with requests if httpx not available
            return await self._check_anthropic_sync(key)
        except Exception as e:
            return ServiceBalance(name="anthropic", error=str(e))

    async def _check_anthropic_sync(self, key: str) -> ServiceBalance:
        """Fallback: check Anthropic key validity with requests."""
        import requests
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "1"}]},
                timeout=10,
            )
            if resp.status_code == 200:
                return ServiceBalance(name="anthropic", details={"status": "active"})
            elif resp.status_code == 401:
                return ServiceBalance(name="anthropic", error="Invalid API key")
            else:
                return ServiceBalance(name="anthropic", details={"status": f"http_{resp.status_code}"})
        except Exception as e:
            return ServiceBalance(name="anthropic", error=str(e))

    async def _check_openai(self) -> ServiceBalance:
        """Check OpenAI API credit/usage."""
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return ServiceBalance(name="openai", error="OPENAI_API_KEY not set")

        import requests
        try:
            # Check organization billing
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return ServiceBalance(name="openai", details={"status": "active", "note": "key valid"})
            elif resp.status_code == 401:
                return ServiceBalance(name="openai", error="Invalid API key")
            elif resp.status_code == 429:
                error_data = resp.json().get("error", {})
                msg = error_data.get("message", "")
                if "exceeded" in msg.lower() or "quota" in msg.lower():
                    return ServiceBalance(name="openai", balance=0, is_low=True, error="Quota exceeded")
                return ServiceBalance(name="openai", details={"status": "rate_limited"})
            else:
                return ServiceBalance(name="openai", error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ServiceBalance(name="openai", error=str(e))

    async def _check_replicate(self) -> ServiceBalance:
        """Check Replicate API balance."""
        key = os.getenv("REPLICATE_API_TOKEN", "")
        if not key:
            return ServiceBalance(name="replicate", error="REPLICATE_API_TOKEN not set")

        import requests
        try:
            resp = requests.get(
                "https://api.replicate.com/v1/account",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return ServiceBalance(
                    name="replicate",
                    details={"status": "active", "username": data.get("username", ""), "type": data.get("type", "")},
                )
            elif resp.status_code == 401:
                return ServiceBalance(name="replicate", error="Invalid API key")
            else:
                return ServiceBalance(name="replicate", error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ServiceBalance(name="replicate", error=str(e))

    def format_report(
        self,
        balances: list[ServiceBalance],
        include_internal: dict | None = None,
        show_env_keys: bool = False,
    ) -> str:
        """Format balance report for Telegram.

        Args:
            balances: List of ServiceBalance from check_all()
            include_internal: Optional dict with VITO internal spend data
        """
        lines = ["VITO Balances"]
        has_low = False

        for b in balances:
            if not show_env_keys and b.details.get("source") == "env_key":
                continue
            if b.error:
                lines.append(f"  {b.name}: ERROR — {b.error}")
            elif b.balance is not None:
                status = "LOW" if b.is_low else "OK"
                if b.is_low:
                    has_low = True
                lines.append(f"  {b.name}: ${b.balance:.2f} [{status}]")
            else:
                status = b.details.get("status", "unknown")
                note = b.details.get("note", "")
                line = f"  {b.name}: {status}"
                if note:
                    line += f" ({note})"
                lines.append(line)

        if include_internal:
            lines.append("")
            lines.append("VITO Internal")
            if "daily_spent" in include_internal:
                lines.append(f"  Today spent: ${include_internal['daily_spent']:.2f}")
            if "daily_limit" in include_internal:
                lines.append(f"  Daily limit: ${include_internal['daily_limit']:.2f}")
            if "daily_earned" in include_internal:
                lines.append(f"  Today earned: ${include_internal['daily_earned']:.2f}")

        if has_low:
            lines.insert(1, "WARNING: Low balance detected!")

        if len(lines) == 1:
            lines.append("  Нет доступных проверок балансов")
        return "\n".join(lines)

    def get_low_balance_alerts(self, balances: list[ServiceBalance]) -> list[str]:
        """Return list of alert messages for low balances."""
        alerts = []
        for b in balances:
            if b.is_low:
                alerts.append(f"{b.name}: ${b.balance:.2f} (threshold: ${b.details.get('threshold', '?')})")
            elif b.error and "quota" in (b.error or "").lower():
                alerts.append(f"{b.name}: {b.error}")
        return alerts
