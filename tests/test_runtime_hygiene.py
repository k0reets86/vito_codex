from pathlib import Path

from modules.runtime_hygiene import cleanup_simulator_artifacts


def test_cleanup_simulator_artifacts_keeps_latest(tmp_path, monkeypatch):
    root = tmp_path / "runtime" / "simulator"
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for idx in range(5):
        path = root / f"run_{idx}"
        path.mkdir()
        (path / "vito_local_sim.db").write_text("db", encoding="utf-8")
        created.append(path)
    import modules.runtime_hygiene as rh

    monkeypatch.setattr(rh, "RUNTIME_SIMULATOR_ROOT", root)
    result = cleanup_simulator_artifacts(keep_latest=2, apply=True)
    remaining = sorted(p.name for p in root.iterdir() if p.is_dir())
    assert len(remaining) == 2
    assert len(result.removed_dirs) == 3
