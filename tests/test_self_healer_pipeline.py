"""Pipeline-level tests for SelfHealer apply/rollback flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.base_agent import TaskResult
from config.settings import settings
from self_healer import SelfHealer


@pytest.fixture
def healer_with_updater(mock_llm_router, mock_memory, mock_comms):
    devops = MagicMock()
    devops.execute_shell = AsyncMock(return_value=TaskResult(success=True, output="ok"))
    updater = MagicMock()
    updater.backup_current_code.return_value = "/tmp/backup.zip"
    updater.run_tests.return_value = {"success": True, "output": "all green"}
    updater.rollback = MagicMock()
    h = SelfHealer(
        llm_router=mock_llm_router,
        memory=mock_memory,
        comms=mock_comms,
        devops_agent=devops,
        self_updater=updater,
    )
    return h, devops, updater


@pytest.mark.asyncio
async def test_apply_fix_pipeline_success(healer_with_updater):
    healer, devops, updater = healer_with_updater
    result = await healer._apply_fix({"shell_command": "free -m"})
    assert result["applied"] is True
    devops.execute_shell.assert_awaited_once()
    updater.backup_current_code.assert_called_once()
    updater.run_tests.assert_called_once()
    updater.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_apply_fix_pipeline_rolls_back_when_tests_fail(healer_with_updater):
    healer, devops, updater = healer_with_updater
    updater.run_tests.return_value = {"success": False, "output": "failing tests"}
    result = await healer._apply_fix({"shell_command": "free -m"})
    assert result["applied"] is False
    assert "rolled back" in result["output"]
    updater.rollback.assert_called_once_with("/tmp/backup.zip")


@pytest.mark.asyncio
async def test_apply_fix_pipeline_rolls_back_when_command_fails(healer_with_updater):
    healer, devops, updater = healer_with_updater
    devops.execute_shell = AsyncMock(return_value=TaskResult(success=False, error="exit 1"))
    healer.devops = devops
    result = await healer._apply_fix({"shell_command": "free -m"})
    assert result["applied"] is False
    updater.rollback.assert_called_once_with("/tmp/backup.zip")


@pytest.mark.asyncio
async def test_apply_fix_pipeline_canary_success(healer_with_updater, monkeypatch):
    healer, devops, updater = healer_with_updater
    devops.execute_shell = AsyncMock(
        side_effect=[
            TaskResult(success=True, output="fix ok"),
            TaskResult(success=True, output="canary ok"),
        ]
    )
    healer.devops = devops
    monkeypatch.setattr(settings, "SELF_HEALER_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SELF_HEALER_CANARY_COMMAND", "free -m", raising=False)
    result = await healer._apply_fix({"shell_command": "free -m"})
    assert result["applied"] is True
    assert devops.execute_shell.await_count == 2
    updater.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_apply_fix_pipeline_canary_failure_rolls_back(healer_with_updater, monkeypatch):
    healer, devops, updater = healer_with_updater
    devops.execute_shell = AsyncMock(
        side_effect=[
            TaskResult(success=True, output="fix ok"),
            TaskResult(success=False, error="canary failed"),
        ]
    )
    healer.devops = devops
    monkeypatch.setattr(settings, "SELF_HEALER_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SELF_HEALER_CANARY_COMMAND", "free -m", raising=False)
    result = await healer._apply_fix({"shell_command": "free -m"})
    assert result["applied"] is False
    assert "canary_failed" in result["output"]
    updater.rollback.assert_called_once_with("/tmp/backup.zip")
