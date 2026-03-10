from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.browser_agent import _resolve_browser_engine
from modules.browser_runtime_policy import get_browser_runtime_profile
from modules.human_browser import HumanBrowser


def run_diagnostics(services: list[str] | None = None) -> dict:
    services = services or ["etsy", "gumroad", "printful"]
    browser = HumanBrowser()
    engine, _ = _resolve_browser_engine()
    profiles = {}
    for service in services:
        policy = get_browser_runtime_profile(service)
        spec = browser.build_context_spec(
            {
                "service": service,
                "storage_state_path": policy.get("storage_state_path"),
                "persistent_profile_dir": policy.get("persistent_profile_dir"),
                "screenshot_first_default": policy.get("screenshot_first_default"),
                "anti_bot_humanize": policy.get("anti_bot_humanize"),
                "headless_preferred": policy.get("headless_preferred"),
                "llm_navigation_allowed": policy.get("llm_navigation_allowed"),
            }
        )
        profiles[service] = {
            "service": spec.service,
            "persistent_profile_dir": spec.persistent_profile_dir,
            "storage_state_path": spec.storage_state_path,
            "screenshot_first_default": spec.screenshot_first_default,
            "anti_bot_humanize": spec.anti_bot_humanize,
            "llm_navigation_allowed": spec.llm_navigation_allowed,
        }
    return {
        "ok": True,
        "engine": engine,
        "services": profiles,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    print(json.dumps(run_diagnostics(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
