from __future__ import annotations

from typing import Any

from config.settings import settings


def chromium_launch_args() -> list[str]:
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-background-networking",
        "--renderer-process-limit=1",
        "--disable-blink-features=AutomationControlled",
        "--js-flags=--max-old-space-size=256",
    ]
    if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
        args.extend(["--no-zygote", "--single-process"])
    return args


def resolve_browser_engine() -> tuple[str, Any]:
    preferred = str(getattr(settings, "BROWSER_AUTOMATION_ENGINE", "auto") or "auto").strip().lower()
    preferred = preferred if preferred in {"auto", "playwright", "patchright"} else "auto"
    errors: list[str] = []
    if preferred in {"auto", "patchright"}:
        try:
            from patchright.async_api import async_playwright as async_patchright

            return "patchright", async_patchright
        except Exception as e:
            errors.append(f"patchright:{e}")
            if preferred == "patchright":
                raise RuntimeError("patchright_unavailable")
    try:
        from playwright.async_api import async_playwright

        return "playwright", async_playwright
    except Exception as e:
        errors.append(f"playwright:{e}")
    raise RuntimeError("browser_engine_unavailable:" + " | ".join(errors))


async def launch_browser(playwright_instance: Any, *, profile: dict[str, Any]) -> Any:
    return await playwright_instance.chromium.launch(
        headless=bool(profile.get("headless_preferred", True)),
        args=chromium_launch_args(),
        proxy=profile.get("proxy") or None,
        chromium_sandbox=False,
    )
