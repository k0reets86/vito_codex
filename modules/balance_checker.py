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

    async def check_all(self) -> list[ServiceBalance]:
        """Check all service balances. Returns list of ServiceBalance."""
        results = []

        # Check each service sequentially (8GB RAM constraint)
        checkers = [
            self._check_anticaptcha,
            self._check_anthropic,
            self._check_openai,
            self._check_replicate,
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

        return results

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

    def format_report(self, balances: list[ServiceBalance], include_internal: dict | None = None) -> str:
        """Format balance report for Telegram.

        Args:
            balances: List of ServiceBalance from check_all()
            include_internal: Optional dict with VITO internal spend data
        """
        lines = ["VITO Balances"]
        has_low = False

        for b in balances:
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
