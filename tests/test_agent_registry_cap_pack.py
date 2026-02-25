import asyncio
from pathlib import Path

import pytest

from agents.agent_registry import AgentRegistry


def test_agent_registry_capability_pack_fallback(tmp_path: Path, monkeypatch):
    pack_dir = tmp_path / "capability_packs" / "demo_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "adapter.py").write_text(
        """def run(input_data):\n    return {\"status\": \"ok\", \"output\": {\"echo\": input_data.get('step')}}\n""",
        encoding="utf-8",
    )

    from modules import capability_pack_runner
    orig = capability_pack_runner.CapabilityPackRunner
    monkeypatch.setattr(capability_pack_runner, "CapabilityPackRunner", lambda root=None: orig(root=str(tmp_path / "capability_packs")))

    reg = AgentRegistry()

    res = asyncio.run(reg.dispatch("demo_pack", step="x"))
    assert res is not None
    assert res.success is True
    assert res.output.get("echo") == "x"
