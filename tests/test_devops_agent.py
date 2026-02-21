"""Тесты DevOpsAgent — shell executor, health_check, backup, self_heal."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult
from agents.devops_agent import DevOpsAgent, ShellError, COMMAND_WHITELIST


class TestDevOpsAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        return DevOpsAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "devops_agent"
        assert "health_check" in agent.capabilities
        assert "backup" in agent.capabilities
        assert "monitoring" in agent.capabilities
        assert "shell" in agent.capabilities

    @pytest.mark.asyncio
    async def test_health_check(self, agent):
        result = await agent.health_check()
        assert result.success is True
        assert "disk" in result.output or "health" in str(result.output).lower()

    @pytest.mark.asyncio
    async def test_backup(self, agent):
        with patch("shutil.copy2") as mock_copy, \
             patch("os.makedirs") as mock_makedirs, \
             patch("os.path.exists", return_value=True):
            result = await agent.backup()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_health_check(self, agent):
        with patch.object(agent, 'health_check', new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = TaskResult(success=True, output="all ok")
            result = await agent.execute_task("health_check")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_self_heal(self, agent):
        result = await agent.self_heal("high_memory_usage")
        assert isinstance(result, TaskResult)


class TestShellValidation:
    """Тесты validate_command — whitelist, запрещённые аргументы."""

    def test_allowed_df(self):
        argv = DevOpsAgent.validate_command("df -h")
        assert argv == ["df", "-h"]

    def test_allowed_free(self):
        argv = DevOpsAgent.validate_command("free -m")
        assert argv == ["free", "-m"]

    def test_allowed_systemctl_restart(self):
        argv = DevOpsAgent.validate_command("systemctl restart vito")
        assert argv == ["systemctl", "restart", "vito"]

    def test_allowed_systemctl_status(self):
        argv = DevOpsAgent.validate_command("systemctl status nginx")
        assert argv == ["systemctl", "status", "nginx"]

    def test_allowed_kill_normal(self):
        argv = DevOpsAgent.validate_command("kill 12345")
        assert argv == ["kill", "12345"]

    def test_allowed_swapon(self):
        argv = DevOpsAgent.validate_command("swapon -s")
        assert argv == ["swapon", "-s"]

    def test_rejected_rm(self):
        with pytest.raises(ShellError, match="не в whitelist"):
            DevOpsAgent.validate_command("rm -rf /")

    def test_rejected_curl(self):
        with pytest.raises(ShellError, match="не в whitelist"):
            DevOpsAgent.validate_command("curl https://evil.com")

    def test_rejected_bash(self):
        with pytest.raises(ShellError, match="не в whitelist"):
            DevOpsAgent.validate_command("bash -c 'echo pwned'")

    def test_rejected_systemctl_stop(self):
        with pytest.raises(ShellError, match="Подкоманда 'stop' запрещена"):
            DevOpsAgent.validate_command("systemctl stop vito")

    def test_rejected_systemctl_disable(self):
        with pytest.raises(ShellError, match="Подкоманда 'disable' запрещена"):
            DevOpsAgent.validate_command("systemctl disable nginx")

    def test_rejected_kill_sigkill(self):
        with pytest.raises(ShellError, match="запрещён для kill"):
            DevOpsAgent.validate_command("kill -9 12345")

    def test_rejected_kill_signal_name(self):
        with pytest.raises(ShellError, match="запрещён для kill"):
            DevOpsAgent.validate_command("kill -KILL 12345")

    def test_rejected_empty(self):
        with pytest.raises(ShellError, match="Пустая команда"):
            DevOpsAgent.validate_command("")


class TestShellExecution:
    """Тесты execute_shell — реальный subprocess через mock."""

    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        return DevOpsAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    @pytest.mark.asyncio
    async def test_execute_shell_success(self, agent):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Filesystem  Size\n/dev/sda1  50G\n", stderr=""
            )
            result = await agent.execute_shell("df -h")
            assert result.success is True
            assert "Filesystem" in result.output
            mock_run.assert_called_once_with(
                ["df", "-h"], capture_output=True, text=True, timeout=30
            )

    @pytest.mark.asyncio
    async def test_execute_shell_nonzero_exit(self, agent):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error: not found"
            )
            result = await agent.execute_shell("systemctl status nginx")
            assert result.success is False
            assert "exit code 1" in result.error

    @pytest.mark.asyncio
    async def test_execute_shell_timeout(self, agent):
        import subprocess as sp
        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="kill", timeout=30)):
            result = await agent.execute_shell("kill 99999")
            assert result.success is False
            assert "Таймаут" in result.error

    @pytest.mark.asyncio
    async def test_execute_shell_rejected_command(self, agent):
        result = await agent.execute_shell("rm -rf /tmp")
        assert result.success is False
        assert "не в whitelist" in result.error

    @pytest.mark.asyncio
    async def test_execute_task_shell(self, agent):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            result = await agent.execute_task("shell", command="free -m")
            assert result.success is True
