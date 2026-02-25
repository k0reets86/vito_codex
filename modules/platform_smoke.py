"""Safe platform smoke checks with evidence logging."""

from __future__ import annotations

import asyncio
from typing import Any

from config.logger import get_logger
from modules.execution_facts import ExecutionFacts

logger = get_logger("platform_smoke", agent="platform_smoke")


class PlatformSmoke:
    def __init__(self, platforms: dict[str, Any]):
        self.platforms = platforms or {}
        self.facts = ExecutionFacts()

    async def _check_one(self, name: str, platform: Any) -> dict:
        status = "failed"
        detail = f"{name}:unreachable"
        evidence = ""
        out: dict[str, Any] = {}
        try:
            auth_ok = False
            if hasattr(platform, "authenticate"):
                auth_ok = bool(await platform.authenticate())
            if auth_ok:
                status = "success"
                detail = f"{name}:auth_ok"
            else:
                status = "failed"
                detail = f"{name}:auth_failed"

            # Read-only capability checks
            if hasattr(platform, "get_analytics"):
                try:
                    out["analytics"] = await platform.get_analytics()
                    if status == "success":
                        detail = f"{name}:auth_ok+analytics_ok"
                except Exception as e:
                    out["analytics_error"] = str(e)
            if hasattr(platform, "get_products"):
                try:
                    prods = await platform.get_products()
                    out["products_count"] = len(prods) if isinstance(prods, list) else 0
                except Exception as e:
                    out["products_error"] = str(e)

            if status == "success":
                evidence = f"smoke:{name}"
        except Exception as e:
            status = "failed"
            detail = f"{name}:exception:{e}"

        try:
            self.facts.record(
                action="platform:smoke",
                status=status,
                detail=detail[:500],
                evidence=evidence,
                source="platform_smoke",
                evidence_dict={"platform": name, "output": out},
            )
        except Exception:
            pass
        return {"platform": name, "status": status, "detail": detail, "output": out}

    async def run(self, names: list[str] | None = None) -> list[dict]:
        selected = names or list(self.platforms.keys())
        tasks = []
        for n in selected:
            p = self.platforms.get(n)
            if p is None:
                continue
            tasks.append(self._check_one(n, p))
        if not tasks:
            return []
        return await asyncio.gather(*tasks)
