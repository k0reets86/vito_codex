from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.platform_onboarding_agent import PlatformOnboardingAgent
from modules.platform_onboarding_records import PlatformOnboardingRecords
from modules.platform_registry import PlatformRegistry


async def run_validation(platform_name: str = "Substack", platform_url: str = "https://substack.com") -> dict:
    registry = PlatformRegistry()
    agent = PlatformOnboardingAgent(platform_registry=registry)
    profile = await agent._phase1_research(platform_name, platform_url)
    integration = await agent._phase2_detect(profile)
    decision = await agent._phase3_report(profile, integration)
    platform_id = str(profile.get("id") or profile.get("name") or "platform")
    records = PlatformOnboardingRecords()
    return {
        "ok": True,
        "platform_id": platform_id,
        "profile_has_id": bool(profile.get("id")),
        "integration_method": integration.get("method"),
        "decision": decision,
        "report_path": records.base_dir.joinpath(f"{platform_id}_report.json").as_posix(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    import asyncio

    result = asyncio.run(run_validation())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
