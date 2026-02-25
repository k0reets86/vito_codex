import asyncio
from pathlib import Path

import pytest

from agents.agent_registry import AgentRegistry


def test_agent_registry_capability_pack_fallback(tmp_path: Path, monkeypatch):
    pack_dir = tmp_path / "capability_packs" / "demo_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "spec.json").write_text(
        '{"name":"demo_pack","category":"x","acceptance_status":"accepted","inputs":[],"outputs":[],"version":"0.1.0","risk_score":0.1,"tests_coverage":0}',
        encoding="utf-8",
    )
    (pack_dir / "adapter.py").write_text(
        """def run(input_data):\n    return {\"status\": \"ok\", \"output\": {\"echo\": input_data.get('step')}}\n""",
        encoding="utf-8",
    )

    from modules import capability_pack_runner
    from config.settings import settings
    orig = capability_pack_runner.CapabilityPackRunner
    monkeypatch.setattr(capability_pack_runner, "CapabilityPackRunner", lambda root=None: orig(root=str(tmp_path / "capability_packs")))
    monkeypatch.setattr(settings, "CAPABILITY_PACK_ALLOW_PENDING", True)

    reg = AgentRegistry()

    res = asyncio.run(reg.dispatch("demo_pack", step="x"))
    assert res is not None
    assert res.success is True
    assert res.output.get("echo") == "x"
