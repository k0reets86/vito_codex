"""Resource Guard — контроль нагрузки на сервер.

Жёсткие правила:
- Обычный лимит: 2GB RAM для процессов VITO
- Критичный лимит: 4-5GB (только для важных операций)
- Никогда не запускать параллельные тяжёлые процессы
- Всё логируется для видимости другим процессам и сессиям

Использование:
    from config.resource_guard import resource_guard

    # Перед запуском тяжёлой операции:
    if resource_guard.can_proceed(estimated_mb=500):
        do_heavy_work()
    else:
        logger.warning("Нагрузка слишком высока, откладываю операцию")

    # Или через context manager:
    async with resource_guard.acquire("browser_session", estimated_mb=300):
        await browser.navigate(url)
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional

from config.logger import get_logger

logger = get_logger("resource_guard", agent="resource_guard")

# --- Лимиты ---
NORMAL_LIMIT_MB = 2048       # 2GB — обычный лимит
CRITICAL_LIMIT_MB = 4096     # 4GB — только для критичных операций
WARNING_THRESHOLD_MB = 1024  # 1GB free — предупреждение
MAX_CONCURRENT_HEAVY = 1     # Макс 1 тяжёлый процесс одновременно


@dataclass
class ActiveTask:
    name: str
    estimated_mb: int
    started_at: float
    pid: int = 0


class ResourceGuard:
    """Централизованный контроль ресурсов."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._active_tasks: dict[str, ActiveTask] = {}
        self._total_reserved_mb = 0

    def get_system_memory(self) -> dict:
        """Читает /proc/meminfo — реальное состояние RAM."""
        info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        val_kb = int(parts[1])
                        info[key] = val_kb
        except (OSError, ValueError):
            return {"MemTotal": 0, "MemAvailable": 0, "MemFree": 0}

        return {
            "total_mb": info.get("MemTotal", 0) // 1024,
            "available_mb": info.get("MemAvailable", 0) // 1024,
            "free_mb": info.get("MemFree", 0) // 1024,
            "buffers_mb": info.get("Buffers", 0) // 1024,
            "cached_mb": info.get("Cached", 0) // 1024,
        }

    def get_process_memory_mb(self) -> int:
        """RSS текущего процесса в MB."""
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) // 1024
        except (OSError, ValueError):
            pass
        return 0

    def can_proceed(self, estimated_mb: int = 0, critical: bool = False) -> bool:
        """Проверяет можно ли запустить операцию.

        Args:
            estimated_mb: Ожидаемое потребление RAM операцией
            critical: Если True — используется повышенный лимит (4GB)

        Returns:
            True если можно запускать
        """
        mem = self.get_system_memory()
        limit = CRITICAL_LIMIT_MB if critical else NORMAL_LIMIT_MB
        available = mem["available_mb"]
        process_rss = self.get_process_memory_mb()
        projected = process_rss + self._total_reserved_mb + estimated_mb

        # Проверка 1: достаточно ли свободной RAM в системе
        if available < WARNING_THRESHOLD_MB:
            logger.warning(
                f"LOW RAM: {available}MB available (threshold {WARNING_THRESHOLD_MB}MB). "
                f"Blocking operation ({estimated_mb}MB requested).",
                extra={"event": "resource_guard_block_low_ram",
                       "context": {"available_mb": available, "requested_mb": estimated_mb}},
            )
            return False

        # Проверка 2: не превысим ли лимит VITO
        if projected > limit:
            logger.warning(
                f"LIMIT EXCEEDED: process={process_rss}MB + reserved={self._total_reserved_mb}MB "
                f"+ requested={estimated_mb}MB = {projected}MB > limit={limit}MB. Blocking.",
                extra={"event": "resource_guard_block_limit",
                       "context": {"projected_mb": projected, "limit_mb": limit}},
            )
            return False

        # Проверка 3: слишком много тяжёлых операций
        heavy_count = sum(1 for t in self._active_tasks.values() if t.estimated_mb > 100)
        if estimated_mb > 100 and heavy_count >= MAX_CONCURRENT_HEAVY:
            active_names = [t.name for t in self._active_tasks.values() if t.estimated_mb > 100]
            logger.warning(
                f"TOO MANY HEAVY TASKS: {heavy_count} active ({active_names}). "
                f"Max {MAX_CONCURRENT_HEAVY}. Blocking new heavy task ({estimated_mb}MB).",
                extra={"event": "resource_guard_block_concurrent",
                       "context": {"active": active_names, "requested_mb": estimated_mb}},
            )
            return False

        logger.info(
            f"Resource check OK: available={available}MB, process={process_rss}MB, "
            f"reserved={self._total_reserved_mb}MB, requested={estimated_mb}MB, "
            f"projected={projected}MB, limit={limit}MB",
            extra={"event": "resource_guard_ok",
                   "context": {"available_mb": available, "projected_mb": projected}},
        )
        return True

    @asynccontextmanager
    async def acquire(self, task_name: str, estimated_mb: int = 0, critical: bool = False):
        """Context manager для тяжёлых операций.

        Резервирует ресурсы, логирует начало/конец, автоматически освобождает.

        Raises:
            MemoryError: Если ресурсов недостаточно
        """
        async with self._lock:
            if not self.can_proceed(estimated_mb, critical):
                raise MemoryError(
                    f"Недостаточно ресурсов для '{task_name}' "
                    f"(нужно ~{estimated_mb}MB). "
                    f"Активные задачи: {list(self._active_tasks.keys())}. "
                    f"Выполните последовательно."
                )
            task = ActiveTask(
                name=task_name,
                estimated_mb=estimated_mb,
                started_at=time.time(),
                pid=os.getpid(),
            )
            self._active_tasks[task_name] = task
            self._total_reserved_mb += estimated_mb
            logger.info(
                f"ACQUIRED: '{task_name}' reserved {estimated_mb}MB. "
                f"Total reserved: {self._total_reserved_mb}MB. "
                f"Active: {list(self._active_tasks.keys())}",
                extra={"event": "resource_acquired",
                       "context": {"task": task_name, "reserved_mb": estimated_mb}},
            )

        try:
            yield
        finally:
            async with self._lock:
                if task_name in self._active_tasks:
                    del self._active_tasks[task_name]
                    self._total_reserved_mb = max(0, self._total_reserved_mb - estimated_mb)
                    duration = time.time() - task.started_at
                    logger.info(
                        f"RELEASED: '{task_name}' freed {estimated_mb}MB after {duration:.1f}s. "
                        f"Total reserved: {self._total_reserved_mb}MB. "
                        f"Active: {list(self._active_tasks.keys())}",
                        extra={"event": "resource_released",
                               "context": {"task": task_name, "duration_s": round(duration, 1)}},
                    )

    def status(self) -> dict:
        """Текущий статус для логов и мониторинга."""
        mem = self.get_system_memory()
        return {
            "system_available_mb": mem["available_mb"],
            "system_total_mb": mem["total_mb"],
            "process_rss_mb": self.get_process_memory_mb(),
            "reserved_mb": self._total_reserved_mb,
            "active_tasks": {
                name: {
                    "estimated_mb": t.estimated_mb,
                    "running_sec": round(time.time() - t.started_at, 1),
                }
                for name, t in self._active_tasks.items()
            },
            "can_heavy": self.can_proceed(estimated_mb=100),
        }


# Singleton — все модули используют один инстанс
resource_guard = ResourceGuard()
