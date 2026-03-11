from pathlib import Path

from modules.runtime_hygiene import (
    cleanup_project_artifacts,
    cleanup_reports_artifacts,
    cleanup_runtime_db_artifacts,
    cleanup_simulator_artifacts,
)


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


def test_cleanup_project_artifacts_removes_magicmock_and_caches(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    magic_dir = project_root / "<MagicMock name='settings.CHROMA_PATH'>"
    magic_dir.mkdir()
    (magic_dir / "chroma.sqlite3").write_text("db", encoding="utf-8")
    cache_dir = project_root / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "a.pyc").write_text("x", encoding="utf-8")
    learn_dir = project_root / ".learnings"
    learn_dir.mkdir()

    import modules.runtime_hygiene as rh

    monkeypatch.setattr(rh, "PROJECT_ROOT", project_root)
    result = cleanup_project_artifacts(apply=True)

    assert any("MagicMock" in item for item in result.removed_dirs)
    assert "__pycache__" in result.removed_dirs
    assert ".learnings" in result.removed_dirs
    assert not magic_dir.exists()
    assert not cache_dir.exists()
    assert not learn_dir.exists()


def test_cleanup_reports_artifacts_keeps_latest(tmp_path, monkeypatch):
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    for idx in range(5):
        path = reports_root / f"r_{idx}.json"
        path.write_text("{}", encoding="utf-8")

    import modules.runtime_hygiene as rh
    monkeypatch.setattr(rh, "REPORTS_ROOT", reports_root)

    result = cleanup_reports_artifacts(keep_latest=2, apply=True)
    remaining = sorted(p.name for p in reports_root.iterdir())
    assert len(remaining) == 2
    assert len(result.removed_files) == 3


def test_cleanup_runtime_db_artifacts_keeps_permanent_and_simulator(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "knowledge_graph.db").write_text("db", encoding="utf-8")
    (runtime_root / "platform_auth_interrupts.db").write_text("db", encoding="utf-8")
    transient = runtime_root / "tmp.sqlite3"
    transient.write_text("db", encoding="utf-8")
    sim_root = runtime_root / "simulator" / "run1"
    sim_root.mkdir(parents=True)
    (sim_root / "vito_local_sim.db").write_text("db", encoding="utf-8")

    import modules.runtime_hygiene as rh
    monkeypatch.setattr(rh, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(rh, "RUNTIME_SIMULATOR_ROOT", runtime_root / "simulator")

    result = cleanup_runtime_db_artifacts(apply=True)
    assert "runtime/tmp.sqlite3" in result.removed_files
    assert "runtime/knowledge_graph.db" in result.kept_files
    assert "runtime/platform_auth_interrupts.db" in result.kept_files
    assert "runtime/simulator/run1/vito_local_sim.db" in result.kept_files
    assert not transient.exists()
