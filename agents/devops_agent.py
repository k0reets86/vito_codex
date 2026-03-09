"""DevOpsAgent — Agent 14: здоровье системы и обслуживание.

Функции: health_check (SQLite, диск, RAM), backup, self_heal, execute_shell.
Shell executor использует строгий whitelist команд.
"""

import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings

logger = get_logger("devops_agent", agent="devops_agent")

BACKUP_DIR = "/home/vito/vito-agent/backups"

SHELL_TIMEOUT = 30  # секунд

# Whitelist: команда → допустимые подкоманды/аргументы (None = любые аргументы)
COMMAND_WHITELIST: dict[str, list[str] | None] = {
    "df": None,              # df -h, df /home и т.д.
    "free": None,            # free -m, free -h
    "kill": None,            # kill <pid> (без -9 — см. валидацию)
    "swapon": None,          # swapon -s, swapon /swapfile
    "swapoff": None,         # swapoff /swapfile
    "systemctl": ["restart", "status", "is-active"],  # только безопасные подкоманды
    "journalctl": None,      # для диагностики логов
    "sqlite3": None,         # PRAGMA integrity_check и т.д.
}

# Флаги, запрещённые для kill (защита от -9 -KILL)
KILL_FORBIDDEN_ARGS = {"-9", "-KILL", "-SIGKILL", "--signal=9", "--signal=KILL"}


class ShellError(Exception):
    """Команда не в whitelist или запрещена."""


class DevOpsAgent(BaseAgent):
    NEEDS = {
        "health_check": ["system_state", "sqlite_state"],
        "backup": ["filesystem_state"],
        "self_heal": ["failure_substrate", "self_healer"],
        "shell": ["command_whitelist"],
        "*": ["ops_runbooks"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="devops_agent", description="Мониторинг здоровья, бэкапы, самовосстановление", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["health_check", "backup", "monitoring", "shell"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "health_check":
                result = await self.health_check()
            elif task_type == "backup":
                result = await self.backup()
            elif task_type == "shell":
                command = kwargs.get("command", kwargs.get("step", ""))
                result = await self.execute_shell(command)
            elif task_type in ("monitoring", "self_heal"):
                issue = kwargs.get("issue", kwargs.get("step", ""))
                result = await self.self_heal(issue)
            else:
                result = TaskResult(success=False, error=f"Неизвестный task_type: {task_type}")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e), duration_ms=int((time.monotonic() - start) * 1000))
        finally:
            self._status = AgentStatus.IDLE

    # ── Shell executor с whitelist ──

    @staticmethod
    def validate_command(command: str) -> list[str]:
        """Парсит и валидирует команду по whitelist. Возвращает argv или raises ShellError."""
        try:
            argv = shlex.split(command)
        except ValueError as e:
            raise ShellError(f"Невалидный синтаксис команды: {e}")

        if not argv:
            raise ShellError("Пустая команда")

        binary = os.path.basename(argv[0])

        if binary not in COMMAND_WHITELIST:
            raise ShellError(
                f"Команда '{binary}' не в whitelist. "
                f"Допустимые: {', '.join(sorted(COMMAND_WHITELIST))}"
            )

        allowed_subs = COMMAND_WHITELIST[binary]

        # Для systemctl — проверяем подкоманду
        if allowed_subs is not None and len(argv) > 1:
            subcmd = argv[1]
            if subcmd not in allowed_subs:
                raise ShellError(
                    f"Подкоманда '{subcmd}' запрещена для '{binary}'. "
                    f"Допустимые: {', '.join(allowed_subs)}"
                )

        # Для kill — запрещаем SIGKILL
        if binary == "kill":
            for arg in argv[1:]:
                if arg.upper() in {a.upper() for a in KILL_FORBIDDEN_ARGS}:
                    raise ShellError(f"Аргумент '{arg}' запрещён для kill (опасный сигнал)")

        return argv

    async def execute_shell(self, command: str) -> TaskResult:
        """Выполняет shell-команду с whitelist-валидацией и таймаутом."""
        try:
            argv = self.validate_command(command)
        except ShellError as e:
            logger.warning(
                f"Shell: команда отклонена: {e}",
                extra={"event": "shell_rejected", "context": {"command": command}},
            )
            return TaskResult(success=False, error=str(e))

        logger.info(
            f"Shell: выполняю {argv}",
            extra={"event": "shell_exec", "context": {"argv": argv}},
        )

        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=SHELL_TIMEOUT,
            )
            output = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode != 0:
                logger.warning(
                    f"Shell: returncode={proc.returncode}, stderr={stderr[:200]}",
                    extra={"event": "shell_nonzero", "context": {"returncode": proc.returncode}},
                )
                return TaskResult(
                    success=False,
                    output=output,
                    error=f"exit code {proc.returncode}: {stderr[:500]}",
                )

            logger.info(
                f"Shell: OK, {len(output)} chars output",
                extra={"event": "shell_success"},
            )
            return TaskResult(success=True, output=output)

        except subprocess.TimeoutExpired:
            logger.error(
                f"Shell: таймаут {SHELL_TIMEOUT}s для {argv}",
                extra={"event": "shell_timeout"},
            )
            return TaskResult(success=False, error=f"Таймаут {SHELL_TIMEOUT}s")
        except OSError as e:
            return TaskResult(success=False, error=f"OS error: {e}")

    # ── Health check ──

    async def health_check(self) -> TaskResult:
        checks: dict[str, Any] = {}
        # Disk
        try:
            stat = os.statvfs("/")
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            checks["disk"] = {"total_gb": round(total_gb, 1), "free_gb": round(free_gb, 1), "ok": free_gb > 1.0}
        except Exception as e:
            checks["disk"] = {"ok": False, "error": str(e)}
        # RAM
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem = {}
            for line in lines[:3]:
                parts = line.split()
                mem[parts[0].rstrip(":")] = int(parts[1])
            total_mb = mem.get("MemTotal", 0) / 1024
            free_mb = mem.get("MemAvailable", mem.get("MemFree", 0)) / 1024
            checks["ram"] = {"total_mb": round(total_mb), "free_mb": round(free_mb), "ok": free_mb > 256}
        except Exception as e:
            checks["ram"] = {"ok": True, "note": "Could not read /proc/meminfo"}
        # SQLite
        checks["sqlite"] = {"path": settings.SQLITE_PATH, "ok": os.path.exists(settings.SQLITE_PATH)}
        # Overall
        all_ok = all(c.get("ok", True) for c in checks.values())
        logger.info(f"Health check: {'OK' if all_ok else 'ISSUES'}", extra={"event": "health_check", "context": checks})
        return TaskResult(success=True, output={"health": "ok" if all_ok else "degraded", "checks": checks, "skill_pack": self.get_skill_pack()})

    # ── Backup ──

    async def backup(self) -> TaskResult:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(BACKUP_DIR, ts)
        os.makedirs(backup_dir, exist_ok=True)
        backed_up = []
        files_to_backup = [settings.SQLITE_PATH, "/home/vito/vito-agent/.env", "/home/vito/vito-agent/config/settings.py"]
        for src in files_to_backup:
            if os.path.exists(src):
                dst = os.path.join(backup_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                backed_up.append(src)
        logger.info(f"Backup: {len(backed_up)} файлов", extra={"event": "backup_done", "context": {"dir": backup_dir}})
        return TaskResult(success=True, output={"backup_dir": backup_dir, "files": backed_up, "skill_pack": self.get_skill_pack()})

    # ── Self-heal (теперь использует execute_shell) ──

    async def self_heal(self, issue: str) -> TaskResult:
        logger.info(f"Self-heal: {issue}", extra={"event": "self_heal_start"})
        actions_taken = []
        issue_lower = issue.lower()

        if "memory" in issue_lower or "ram" in issue_lower or "oom" in issue_lower:
            diag = await self.execute_shell("free -m")
            actions_taken.append({"action": "free -m", "result": diag.output if diag.success else diag.error})

        if "disk" in issue_lower or "space" in issue_lower:
            diag = await self.execute_shell("df -h")
            actions_taken.append({"action": "df -h", "result": diag.output if diag.success else diag.error})

        if "swap" in issue_lower:
            diag = await self.execute_shell("swapon -s")
            actions_taken.append({"action": "swapon -s", "result": diag.output if diag.success else diag.error})

        if "database" in issue_lower or "sqlite" in issue_lower:
            diag = await self.execute_shell(f"sqlite3 {settings.SQLITE_PATH} 'PRAGMA integrity_check'")
            actions_taken.append({"action": "sqlite3 integrity_check", "result": diag.output if diag.success else diag.error})

        if not actions_taken:
            actions_taken.append({"action": "none", "result": f"Проблема '{issue}' зафиксирована, требуется ручной анализ"})

        return TaskResult(success=True, output={"issue": issue, "actions": actions_taken, "skill_pack": self.get_skill_pack()})
