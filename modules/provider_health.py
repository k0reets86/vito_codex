"""Provider health and key-rotation reminders (offline-safe checks)."""

from __future__ import annotations

import os
from datetime import datetime, timezone


class ProviderHealth:
    def __init__(self):
        self.provider_keys = {
            "openai": ["OPENAI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "openrouter": ["OPENROUTER_API_KEY"],
            "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "perplexity": ["PERPLEXITY_API_KEY"],
            "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID"],
            "threads": ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"],
            "tiktok": ["TIKTOK_ACCESS_TOKEN"],
            "gumroad": ["GUMROAD_API_KEY", "GUMROAD_OAUTH_TOKEN"],
            "twitter": ["TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET"],
        }

    @staticmethod
    def _env(key: str) -> str:
        return str(os.getenv(key, "") or "")

    @staticmethod
    def _parse_dt(raw: str) -> datetime | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _key_rotation_age_days(self, key: str) -> int | None:
        rotated_key = f"{key}_ROTATED_AT"
        dt = self._parse_dt(self._env(rotated_key))
        if not dt:
            return None
        age = datetime.now(timezone.utc) - dt
        return max(0, int(age.days))

    def summary(self, rotation_days_max: int = 90) -> dict:
        providers = []
        stale_keys = []
        for provider, keys in self.provider_keys.items():
            present = [k for k in keys if self._env(k).strip()]
            missing = [k for k in keys if k not in present]
            ages = [(k, self._key_rotation_age_days(k)) for k in present]
            known_ages = [a for _, a in ages if a is not None]
            max_age = max(known_ages) if known_ages else None
            rotation_due = any(a is not None and a > int(rotation_days_max) for _, a in ages)
            if rotation_due:
                stale_keys.extend([k for k, a in ages if a is not None and a > int(rotation_days_max)])
            if not present:
                status = "missing"
            elif missing:
                status = "partial"
            elif rotation_due:
                status = "stale"
            else:
                status = "ok"
            providers.append(
                {
                    "provider": provider,
                    "status": status,
                    "configured": len(present),
                    "required": len(keys),
                    "missing_keys": missing,
                    "rotation_due": rotation_due,
                    "max_key_age_days": max_age,
                }
            )
        missing_total = sum(1 for p in providers if p["status"] in {"missing", "partial"})
        stale_total = sum(1 for p in providers if p["status"] == "stale")
        overall = "ok"
        if missing_total > 0:
            overall = "degraded"
        if stale_total > 0 and overall == "ok":
            overall = "warning"
        remediations = []
        if missing_total > 0:
            remediations.append("Add missing provider keys and verify credentials in dashboard secrets.")
        if stale_total > 0:
            remediations.append("Rotate stale API keys and set *_ROTATED_AT timestamps.")
        return {
            "overall_status": overall,
            "providers": providers,
            "missing_provider_count": missing_total,
            "stale_provider_count": stale_total,
            "stale_keys": stale_keys[:30],
            "rotation_days_max": int(rotation_days_max),
            "safe_actions": [
                "apply_profile_economy",
                "disable_tooling_live",
                "enable_guardrails_block",
                "set_notify_minimal",
            ],
            "remediations": remediations,
        }
