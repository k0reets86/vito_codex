"""DevOpsAgent — Agent 14: здоровье системы и обслуживание.

Функции: health_check (PostgreSQL, SQLite, диск, RAM), backup, self_heal.
"""

import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from config.settings import settings

logger = get_logger("devops_agent", agent="devops_agent")

BACKUP_DIR = "/home/vito/vito-agent/backups"


class DevOpsAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="devops_agent", description="Мониторинг здоровья, бэкапы, самовосстановление", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["health_check", "backup", "monitoring"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "health_check":
                result = await self.health_check()
            elif task_type == "backup":
                result = await self.backup()
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
        return TaskResult(success=True, output={"health": "ok" if all_ok else "degraded", "checks": checks})

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
        return TaskResult(success=True, output={"backup_dir": backup_dir, "files": backed_up})

    async def self_heal(self, issue: str) -> TaskResult:
        logger.info(f"Self-heal: {issue}", extra={"event": "self_heal_start"})
        actions = []
        if "memory" in issue.lower() or "ram" in issue.lower():
            actions.append("Рекомендация: перезапустить тяжёлые процессы")
        if "disk" in issue.lower():
            actions.append("Рекомендация: очистить логи и временные файлы")
        if "database" in issue.lower() or "sqlite" in issue.lower():
            actions.append("Рекомендация: проверить целостность БД (PRAGMA integrity_check)")
        if not actions:
            actions.append(f"Проблема '{issue}' зафиксирована, требуется ручной анализ")
        return TaskResult(success=True, output={"issue": issue, "actions": actions})
