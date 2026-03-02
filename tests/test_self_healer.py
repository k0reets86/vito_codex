"""Тесты для SelfHealer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult
from config.settings import settings
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
            return_value='{"can_auto_fix": true, "fix_description": "Проверить память", "shell_command": "free -m"}'
        )
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="restarted"))
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)

        result = await healer.handle_error("test_agent", TimeoutError("connection timeout"))
        assert result["resolved"] is True
        assert result["method"] == "llm_fix_applied"
        assert "shell_output" in result
        mock_devops.execute_shell.assert_awaited_once_with("free -m")

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
    async def test_handle_error_quarantine_cooldown_after_escalation(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """После эскалации одинаковая ошибка сразу уходит в cooldown и не эскалируется повторно."""
        mock_llm_router.call_llm = AsyncMock(return_value=None)
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        error = RuntimeError("persistent cooldown error")

        for _ in range(MAX_AUTO_FIX_ATTEMPTS):
            out = await healer.handle_error("test_agent", error)
        assert out["method"] == "escalated"
        initial_calls = mock_comms.send_message.call_count

        out2 = await healer.handle_error("test_agent", error)
        assert out2["method"] == "cooldown"
        assert mock_comms.send_message.call_count == initial_calls
        stats = healer.get_error_stats()
        assert int(stats.get("quarantine_errors", 0) or 0) >= 1

    @pytest.mark.asyncio
    async def test_quarantine_persists_across_healer_instances(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops):
        """Quarantine сохраняется в SQLite и действует после рестарта SelfHealer."""
        mock_llm_router.call_llm = AsyncMock(return_value=None)
        err = RuntimeError("persistent cross-instance error")

        h1 = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        for _ in range(MAX_AUTO_FIX_ATTEMPTS):
            out = await h1.handle_error("test_agent", err)
        assert out["method"] == "escalated"
        calls_after_escalation = mock_comms.send_message.call_count

        h2 = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        out2 = await h2.handle_error("test_agent", err)
        assert out2["method"] == "cooldown"
        assert mock_comms.send_message.call_count == calls_after_escalation

    @pytest.mark.asyncio
    async def test_quarantine_uses_runtime_settings(self, mock_llm_router, mock_comms, mock_memory_with_sqlite, mock_devops, monkeypatch):
        mock_llm_router.call_llm = AsyncMock(return_value=None)
        monkeypatch.setattr(settings, "SELF_HEALER_QUARANTINE_SEC", 5)
        monkeypatch.setattr(settings, "SELF_HEALER_QUARANTINE_MAX_MULT", 2)
        healer = SelfHealer(mock_llm_router, mock_memory_with_sqlite, mock_comms, mock_devops)
        error = RuntimeError("runtime configured quarantine error")
        for _ in range(MAX_AUTO_FIX_ATTEMPTS):
            out = await healer.handle_error("test_agent", error)
        assert out["method"] == "escalated"
        assert "quarantine=5s" in out["description"]

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

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_dangerous(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "git reset --hard"})
        assert result["applied"] is False
        assert "rejected_by_judge" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_test_softening(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "sed -i 's/assert True/assert False/' tests/test_core.py"})
        assert result["applied"] is False
        assert "rejected_by_judge" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_rm_rf(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "rm -rf ./tmp_build"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_host_reboot(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "reboot"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_host_shutdown_legacy_init(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "init 0"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_disk_format_tool(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "mkfs.ext4 /dev/sda"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_destructive_dd(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "dd if=/dev/zero of=/dev/sda bs=1M count=1"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_recursive_chown(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "chown -R root:root /var/app"})
        assert result["applied"] is False
        assert "rejected_by_judge: dangerous_command" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_not_in_whitelist(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "ls -la"})
        assert result["applied"] is False
        assert "rejected_by_judge: not_in_whitelist" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_process_kill(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "kill 1234"})
        assert result["applied"] is False
        assert "rejected_by_judge: process_kill_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_process_killall(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "killall python3"})
        assert result["applied"] is False
        assert "rejected_by_judge: process_kill_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl stop vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_isolate(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl isolate rescue.target"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_set_default(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl set-default rescue.target"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_daemon_reexec(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl daemon-reexec"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_restart(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl restart vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_reload(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl reload vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_disruption_reenable(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "systemctl reenable vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_legacy_stop(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "service nginx stop"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_legacy_chkconfig(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "chkconfig nginx off"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_legacy_update_rcd_disable(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "update-rc.d nginx disable"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_legacy_insserv_remove(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "insserv -r nginx"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_openrc_rc_update_del(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "rc-update del nginx default"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_openrc_rc_service_stop(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "rc-service nginx stop"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_runit_sv_down(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "sv down nginx"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_s6_svc_down(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "s6-svc -d /run/service/nginx"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_launchctl_unload(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "launchctl unload /Library/LaunchDaemons/com.vito.agent.plist"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_launchctl_bootout(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "launchctl bootout system/com.vito.agent"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_launchctl_disable(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "launchctl disable system/com.vito.agent"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_launchctl_remove(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "launchctl remove com.vito.agent"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_service_launchctl_kickstart_k(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "launchctl kickstart -k system/com.vito.agent"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "ufw disable"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_nft(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "nft flush ruleset"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_ip6tables(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "ip6tables -F"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_ufw_reset(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "ufw reset"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_setenforce_permissive(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "setenforce permissive"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_semanage_permissive(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "semanage permissive -a httpd_t"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_iptables_policy(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "iptables -P ACCEPT"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_security_degradation_user_lock(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "passwd -l vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: security_degradation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_db_mutation(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "sqlite3 memory/vito_local.db \"DELETE FROM errors;\""})
        assert result["applied"] is False
        assert "rejected_by_judge: db_mutation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_supply_chain_risk(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "pip install requests"})
        assert result["applied"] is False
        assert "rejected_by_judge: supply_chain_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_supply_chain_risk_python_m_pip(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "python3 -m pip install requests"})
        assert result["applied"] is False
        assert "rejected_by_judge: supply_chain_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_privilege_escalation(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "sudo systemctl restart vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: privilege_escalation_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_multi_command_chain(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "free -m && df -h"})
        assert result["applied"] is False
        assert "rejected_by_judge: multi_command_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_background_chain(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "free -m &"})
        assert result["applied"] is False
        assert "rejected_by_judge: multi_command_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_detached_background(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "nohup free -m"})
        assert result["applied"] is False
        assert "rejected_by_judge: multi_command_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_judge_shell_redirection(self, healer, mock_devops):
        result = await healer._apply_fix({"shell_command": "free -m > /tmp/vito.txt"})
        assert result["applied"] is False
        assert "rejected_by_judge: shell_redirection_risk" in result["output"]
        mock_devops.execute_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_fix_rejected_by_change_budget_and_rolled_back(self, healer, mock_devops, monkeypatch):
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="done"))
        updater = MagicMock()
        updater.backup_current_code.return_value = "/tmp/backup.tar.gz"
        updater.rollback = MagicMock()
        updater.run_tests.return_value = {"success": True, "output": "ok"}
        healer.self_updater = updater
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_FILES", 1)
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_LINES", 5)
        with patch("self_healer.subprocess.run") as run_mock:
            run_mock.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="4\t3\tapp.py\n"),
            ]
            result = await healer._apply_fix({"shell_command": "free -m", "fix_description": "small fix"})
        assert result["applied"] is False
        assert "rejected_by_budget" in result["output"]
        updater.rollback.assert_called_once()


class TestJudgePolicyMode:
    @pytest.mark.asyncio
    async def test_balanced_mode_blocks_restart_without_explicit_flag(self, healer, mock_devops, monkeypatch):
        monkeypatch.setattr(settings, "SELF_HEALER_POLICY_MODE", "balanced", raising=False)
        monkeypatch.setattr(settings, "SELF_HEALER_BALANCED_ALLOW_SERVICE_RESTART", False, raising=False)
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="ok"))
        result = await healer._apply_fix({"shell_command": "systemctl restart vito"})
        assert result["applied"] is False
        assert "rejected_by_judge: service_disruption_risk" in result["output"]

    @pytest.mark.asyncio
    async def test_balanced_mode_can_allow_restart_with_explicit_flag(self, healer, mock_devops, monkeypatch):
        monkeypatch.setattr(settings, "SELF_HEALER_POLICY_MODE", "balanced", raising=False)
        monkeypatch.setattr(settings, "SELF_HEALER_BALANCED_ALLOW_SERVICE_RESTART", True, raising=False)
        mock_devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="service restarted"))
        result = await healer._apply_fix({"shell_command": "systemctl restart vito"})
        assert result["applied"] is True
        mock_devops.execute_shell.assert_awaited_once_with("systemctl restart vito")


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
        assert "quarantine_errors" in stats

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


class TestFailureSnapshot:
    def test_build_failure_snapshot_contains_location_and_attempt(self):
        try:
            raise ValueError("boom")
        except ValueError as err:
            snap = SelfHealer._build_failure_snapshot("agent_x", err, {"phase": "exec"}, attempt=2)
        assert snap["agent"] == "agent_x"
        assert snap["attempt"] == 2
        assert snap["error_type"] == "ValueError"
        assert snap["context"]["phase"] == "exec"
        assert "ts" in snap
        assert isinstance(snap.get("location"), dict)


class TestChangeBudget:
    def test_check_git_change_budget_ok(self, monkeypatch):
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_FILES", 3)
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_LINES", 20)
        with patch("self_healer.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout="2\t1\ta.py\n1\t0\tb.py\n")
            ok, detail = SelfHealer._check_git_change_budget()
        assert ok is True
        assert "files=2" in detail

    def test_check_git_change_budget_exceeds_files(self, monkeypatch):
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_FILES", 1)
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_LINES", 100)
        with patch("self_healer.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout="1\t0\ta.py\n1\t0\tb.py\n")
            ok, detail = SelfHealer._check_git_change_budget()
        assert ok is False
        assert "changed_files_exceeded" in detail

    def test_check_git_change_budget_exceeds_lines(self, monkeypatch):
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_FILES", 10)
        monkeypatch.setattr(settings, "SELF_HEALER_MAX_CHANGED_LINES", 2)
        with patch("self_healer.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout="2\t2\ta.py\n")
            ok, detail = SelfHealer._check_git_change_budget()
        assert ok is False
        assert "changed_lines_exceeded" in detail
