from pathlib import Path

from modules.capability_pack_runner import CapabilityPackRunner


def test_capability_pack_runner(tmp_path: Path):
    pack_dir = tmp_path / "capability_packs" / "demo"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "adapter.py").write_text(
        """def run(input_data):\n    return {\"status\": \"ok\", \"output\": input_data}\n""",
        encoding="utf-8",
    )
    runner = CapabilityPackRunner(root=str(tmp_path / "capability_packs"))
    res = runner.run("demo", {"x": 1})
    assert res["status"] == "ok"
    assert res["output"]["x"] == 1
