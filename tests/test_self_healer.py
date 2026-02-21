"""Тесты для SelfHealer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult
from self_healer import SelfHealer, MAX_AUTO_FIX_ATTEMPTS


@pytest.fixture
def mock_devops():
    """Mock DevOpsAgent с execute_shell."""
    devops = MagicMock()
    devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="ok"))
    return devops


@pytest.fixture
def healer(mock_llm_router, mock_memory, mock_comms, mock_devops):
    return SelfHealer(
        llm_router=mock_llm_router, memory=mock_memory, comms=mock_comms,
        devops_agent=mock_devops,
    )


@pytest.fixture
def mock_memory_with_sqlite(tmp_sqlite):
    """Memory с реальным SQLite для тестов поиска ошибок."""
    import sqlite3
    conn = sqlite3.connect(tmp_sqlite)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            error_type TEXT,
            message TEXT,
            resolution TEXT,
            resolved INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            pattern_value TEXT,
            confidence REAL DEFAULT 0.5,
            times_applied INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(category, pattern_key)
        );
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            last_used TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    mem = MagicMock()
    mem._get_sqlite.return_value = conn
    mem.log_error = MagicMock()
    mem.store_knowledge = MagicMock()
    mem.search_knowledge = MagicMock(return_value=[])
    return mem


class TestSelfHealerInit:
    def test_init(self, healer):
        assert healer.llm_router is not None
        assert healer.memory is not None
        assert healer.comms is not None
        assert healer.devops is not None
        assert healer._attempt_counts == {}

    def test_init_no_devops(self, mock_llm_router, mock_memory, mock_comms):
        h = SelfHealer(mock_llm_router, mock_memory, mock_comms)
        assert h.devops is None

    def test_set_devops_agent(self, mock_llm_router, mock_memory, mock_comms, mock_devops):
        h = SelfHealer(mock_llm_router, mock_memory, mock_comms)
        assert h.devops is None
        h.set_devops_agent(mock_devops)
        assert h.devops is mock_devops


class TestHandleError:
    @pytest.mark.asyncio
    async def test_handle_error_no_similar_no_llm(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """Ошибка без похожих решений, LLM не может починить."""
        mock_llm_router.call_llm = AsyncMock(return_value=None)
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        result = await healer.handle_error("test_agent", ValueError("test error"))
        assert result["resolved"] is False
        assert result["method"] == "pending"
        mock_memory_with_sqlite.log_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_found_in_db(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """Ошибка найдена в базе решённых."""
        conn = mock_memory_with_sqlite._get_sqlite()
        conn.execute(
            "INSERT INTO errors (module, error_type, message, resolution, resolved) VALUES (?, ?, ?, ?, ?)",
            ("test_agent", "ValueError", "test error", "restart the module", 1),
        )
        conn.commit()

        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        result = await healer.handle_error("test_agent", ValueError("test error"))
        assert result["resolved"] is True
        assert result["method"] == "database"
        assert "restart" in result["description"]

    @pytest.mark.asyncio
    async def test_handle_error_llm_fix_applied(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """LLM анализирует, предлагает shell-команду, devops её выполняет."""
        mock_llm_router.call_llm = AsyncMock(
            return_value='{"can_auto_fix": true, "fix_description": "Перезапустить сервис", "shell_command": "systemctl restart vito"}'
        )
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="restarted"))
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        result = await healer.handle_error("test_agent", TimeoutError("connection timeout"))
        assert result["resolved"] is True
        assert result["method"] == "llm_fix_applied"
        assert "shell_output" in result
        mock_devops.execute_shell.assert_awaited_once_with("systemctl restart vito")

    @pytest.mark.asyncio
    async def test_handle_error_llm_fix_no_shell(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """LLM says can_auto_fix but no shell_command → fix not applied."""
        mock_llm_router.call_llm = AsyncMock(
            return_value='{"can_auto_fix": true, "fix_description": "Увеличить timeout", "shell_command": null}'
        )
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        result = await healer.handle_error("test_agent", TimeoutError("timeout"))
        assert result["resolved"] is False
        assert result["method"] == "llm_fix_failed"

    @pytest.mark.asyncio
    async def test_handle_error_llm_fix_shell_fails(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """LLM proposes shell command but it fails."""
        mock_llm_router.call_llm = AsyncMock(
            return_value='{"can_auto_fix": true, "fix_description": "Restart", "shell_command": "systemctl restart broken"}'
        )
        mock_devops.execute_shell = AsyncMock(
            return_value=TaskResult(success=False, error="exit code 1: unit not found")
        )
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        result = await healer.handle_error("test_agent", RuntimeError("service down"))
        assert result["resolved"] is False
        assert result["method"] == "llm_fix_failed"

    @pytest.mark.asyncio
    async def test_handle_error_escalation_after_max_attempts(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """После MAX_AUTO_FIX_ATTEMPTS попыток → эскалация."""
        mock_llm_router.call_llm = AsyncMock(return_value=None)
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        error = RuntimeError("persistent error")
        for i in range(MAX_AUTO_FIX_ATTEMPTS):
            result = await healer.handle_error("test_agent", error)

        assert result["method"] == "escalated"
        assert result["resolved"] is False
        mock_comms.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_error_with_context(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """Ошибка с контекстом передаётся в LLM."""
        mock_llm_router.call_llm = AsyncMock(
            return_value='{"can_auto_fix": false, "fix_description": "manual fix needed", "shell_command": null}'
        )
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        context = {"step": "publishing", "platform": "etsy"}

        result = await healer.handle_error("ecommerce_agent", ValueError("API error"), context)
        assert result["resolved"] is False


class TestApplyFix:
    @pytest.mark.asyncio
    async def test_apply_fix_success(self, healer, mock_devops):
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="done"))
        result = await healer._apply_fix({"shell_command": "free -m", "fix_description": "check ram"})
        assert result["applied"] is True
        assert "done" in result["output"]

    @pytest.mark.asyncio
    async def test_apply_fix_no_command(self, healer):
        result = await healer._apply_fix({"fix_description": "just a description"})
        assert result["applied"] is False

    @pytest.mark.asyncio
    async def test_apply_fix_no_devops(self, mock_llm_router, mock_memory, mock_comms):
        healer = SelfHealer(mock_llm_router, mock_memory, mock_comms, devops_agent=None)
        result = await healer._apply_fix({"shell_command": "free -m"})
        assert result["applied"] is False

    @pytest.mark.asyncio
    async def test_apply_fix_shell_error(self, healer, mock_devops):
        mock_devops.execute_shell = AsyncMock(
            return_value=TaskResult(success=False, error="command failed")
        )
        result = await healer._apply_fix({"shell_command": "systemctl restart bad"})
        assert result["applied"] is False


class TestFindSimilarErrors:
    def test_find_exact_match(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        conn = mock_memory_with_sqlite._get_sqlite()
        conn.execute(
            "INSERT INTO errors (module, error_type, message, resolution, resolved) VALUES (?, ?, ?, ?, ?)",
            ("agent_x", "TypeError", "int not callable", "fix type cast", 1),
        )
        conn.commit()

        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        result = healer._find_similar_errors("agent_x", "TypeError", "int not callable")
        assert result is not None
        assert "fix type cast" in result["resolution"]

    def test_find_partial_match(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        conn = mock_memory_with_sqlite._get_sqlite()
        conn.execute(
            "INSERT INTO errors (module, error_type, message, resolution, resolved) VALUES (?, ?, ?, ?, ?)",
            ("agent_y", "ConnectionError", "timeout connecting to API server", "retry with backoff", 1),
        )
        conn.commit()

        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        result = healer._find_similar_errors("other_agent", "ConnectionError", "timeout connecting to API")
        assert result is not None

    def test_no_match(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        result = healer._find_similar_errors("agent", "UnknownError", "never seen before")
        assert result is None


class TestAnalyzeWithLLM:
    @pytest.mark.asyncio
    async def test_analyze_success(self, healer):
        healer.llm_router.call_llm = AsyncMock(
            return_value='{"can_auto_fix": true, "fix_description": "Restart service", "shell_command": "systemctl restart vito"}'
        )
        result = await healer._analyze_with_llm("test", ValueError("err"), None)
        assert result is not None
        assert result["can_auto_fix"] is True
        assert result["shell_command"] == "systemctl restart vito"

    @pytest.mark.asyncio
    async def test_analyze_with_markdown_json(self, healer):
        healer.llm_router.call_llm = AsyncMock(
            return_value='```json\n{"can_auto_fix": false, "fix_description": "manual", "shell_command": null}\n```'
        )
        result = await healer._analyze_with_llm("test", ValueError("err"), None)
        assert result is not None
        assert result["can_auto_fix"] is False

    @pytest.mark.asyncio
    async def test_analyze_llm_returns_none(self, healer):
        healer.llm_router.call_llm = AsyncMock(return_value=None)
        result = await healer._analyze_with_llm("test", ValueError("err"), None)
        assert result is None


class TestErrorStats:
    def test_get_error_stats_empty(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        stats = healer.get_error_stats()
        assert stats["total"] == 0
        assert stats["resolved"] == 0
        assert stats["unresolved"] == 0

    def test_get_error_stats_with_data(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        conn = mock_memory_with_sqlite._get_sqlite()
        conn.execute("INSERT INTO errors (module, error_type, message, resolved) VALUES ('a', 'E', 'm1', 1)")
        conn.execute("INSERT INTO errors (module, error_type, message, resolved) VALUES ('a', 'E', 'm2', 0)")
        conn.execute("INSERT INTO errors (module, error_type, message, resolved) VALUES ('b', 'F', 'm3', 1)")
        conn.commit()

        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        stats = healer.get_error_stats()
        assert stats["total"] == 3
        assert stats["resolved"] == 2
        assert stats["unresolved"] == 1
        assert len(stats["recent"]) == 3
        assert len(stats["by_module"]) == 2
