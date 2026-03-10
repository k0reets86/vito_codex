from pathlib import Path

from modules.capability_pack_runner import CapabilityPackRunner


def test_capability_pack_runner(tmp_path: Path):
    pack_dir = tmp_path / "capability_packs" / "demo"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "spec.json").write_text(
        '{"name":"demo","category":"x","acceptance_status":"accepted","inputs":[],"outputs":[],"version":"0.1.0","risk_score":0.1,"tests_coverage":0}',
        encoding="utf-8",
    )
    (pack_dir / "adapter.py").write_text(
        """def run(input_data):\n    return {\"status\": \"ok\", \"output\": input_data}\n""",
        encoding="utf-8",
    )
    runner = CapabilityPackRunner(root=str(tmp_path / "capability_packs"))
    res = runner.run("demo", {"x": 1})
    assert res["status"] == "ok"
    assert res["output"]["x"] == 1
    assert res["output"]["capability"] == "demo"
    assert res["output"]["runtime_profile"]["version"] == "0.1.0"
