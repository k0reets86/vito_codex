"""Тесты для SelfUpdater."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from self_updater import SelfUpdater


@pytest.fixture
def mock_memory_with_sqlite_updater(tmp_sqlite):
    """Memory с реальным SQLite для SelfUpdater."""
    import sqlite3
    conn = sqlite3.connect(tmp_sqlite)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, description TEXT,
            success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            last_used TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY, module TEXT, error_type TEXT, message TEXT,
            resolution TEXT, resolved INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY, category TEXT, pattern_key TEXT, pattern_value TEXT,
            confidence REAL DEFAULT 0.5, times_applied INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')), UNIQUE(category, pattern_key)
        );
    """)
    conn.commit()

    mem = MagicMock()
    mem._get_sqlite.return_value = conn
    return mem


@pytest.fixture
def updater(mock_memory_with_sqlite_updater, mock_comms, tmp_path):
    return SelfUpdater(
        memory=mock_memory_with_sqlite_updater,
        comms=mock_comms,
        backup_dir=str(tmp_path / "backups"),
    )


class TestSelfUpdaterInit:
    def test_init(self, updater):
        assert updater.memory is not None
        assert updater.comms is not None
        assert updater.backup_dir.exists()

    def test_init_creates_backup_dir(self, mock_memory_with_sqlite_updater, mock_comms, tmp_path):
        backup_dir = tmp_path / "new_backups"
        upd = SelfUpdater(mock_memory_with_sqlite_updater, mock_comms, str(backup_dir))
        assert backup_dir.exists()

    def test_init_creates_update_history_table(self, updater):
        conn = updater.memory._get_sqlite()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='update_history'").fetchall()
        assert len(rows) == 1


class TestBackup:
    def test_backup_current_code(self, updater, tmp_path):
        # Создаём fake project files
        with patch("self_updater.PROJECT_ROOT", tmp_path):
            (tmp_path / "main.py").write_text("print('hello')")
            (tmp_path / "test.py").write_text("assert True")
            updater.backup_dir = tmp_path / "backups"
            updater.backup_dir.mkdir(exist_ok=True)

            backup_path = updater.backup_current_code()
            assert backup_path is not None
            assert Path(backup_path).exists()

    def test_backup_excludes_pycache(self, updater, tmp_path):
        with patch("self_updater.PROJECT_ROOT", tmp_path):
            (tmp_path / "main.py").write_text("print('hello')")
            cache_dir = tmp_path / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "main.cpython-311.pyc").write_text("bytecode")
            updater.backup_dir = tmp_path / "backups"
            updater.backup_dir.mkdir(exist_ok=True)

            backup_path = updater.backup_current_code()
            assert backup_path is not None
            bp = Path(backup_path)
            assert not (bp / "__pycache__").exists()


class TestRollback:
    def test_rollback_success(self, updater, tmp_path):
        with patch("self_updater.PROJECT_ROOT", tmp_path):
            # Create original file
            (tmp_path / "original.py").write_text("original")

            # Create backup
            backup = tmp_path / "my_backup"
            backup.mkdir()
            (backup / "original.py").write_text("backup_version")

            result = updater.rollback(str(backup))
            assert result is True
            assert (tmp_path / "original.py").read_text() == "backup_version"

    def test_rollback_no_backup(self, updater):
        result = updater.rollback("/nonexistent/path")
        assert result is False


class TestRunTests:
    def test_run_tests_returns_dict(self, updater):
        result = updater.run_tests(test_path="tests/test_self_updater.py")
        assert "success" in result
        assert "passed" in result
        assert "failed" in result
        assert "output" in result


class TestUpdateFromGit:
    @pytest.mark.asyncio
    async def test_update_from_git_backup_fails(self, updater):
        with patch.object(updater, "backup_current_code", return_value=None):
            result = await updater.update_from_git()
            assert result["success"] is False
            assert "бэкап" in result["error"]

    @pytest.mark.asyncio
    async def test_update_from_git_pull_fails(self, updater, tmp_path):
        with patch.object(updater, "backup_current_code", return_value=str(tmp_path / "backup")):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="fatal: not a git repo")
                with patch.object(updater, "rollback"):
                    result = await updater.update_from_git()
                    assert result["success"] is False


class TestApplyPatch:
    @pytest.mark.asyncio
    async def test_apply_patch_backup_fails(self, updater):
        with patch.object(updater, "backup_current_code", return_value=None):
            result = await updater.apply_patch("diff content")
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_apply_patch_check_fails(self, updater, tmp_path):
        with patch.object(updater, "backup_current_code", return_value=str(tmp_path / "backup")):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="patch does not apply")
                result = await updater.apply_patch("bad patch")
                assert result["success"] is False


class TestUpdateHistory:
    def test_get_update_history_empty(self, updater):
        history = updater.get_update_history()
        assert history == []

    def test_record_and_get_history(self, updater):
        updater._record_update("git_pull", "main", "/backup", 10, 0, "applied")
        history = updater.get_update_history()
        assert len(history) == 1
        assert history[0]["update_type"] == "git_pull"
        assert history[0]["status"] == "applied"
