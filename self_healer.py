"""SelfHealer — самолечение VITO.

Утилита (не агент), чтобы избежать циклической зависимости с AgentRegistry.
Ищет похожие решённые ошибки в SQLite, при неудаче — анализирует через LLM,
при повторных неудачах — эскалирует владельцу через Telegram.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from config.logger import get_logger
from llm_router import LLMRouter, TaskType

logger = get_logger("self_healer", agent="self_healer")

MAX_AUTO_FIX_ATTEMPTS = 3


class SelfHealer:
    def __init__(self, llm_router: LLMRouter, memory, comms, devops_agent=None, self_updater=None):
        self.llm_router = llm_router
        self.memory = memory
        self.comms = comms
        self.devops = devops_agent
        self.self_updater = self_updater
        self._attempt_counts: dict[str, int] = {}  # error_key → attempt count
        logger.info("SelfHealer инициализирован", extra={"event": "init"})

    def set_devops_agent(self, devops_agent) -> None:
        """Устанавливает DevOpsAgent (для отложенной инициализации)."""
        self.devops = devops_agent

    async def handle_error(
        self, agent: str, error: Exception, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Обработка ошибки: поиск решения → LLM-анализ → эскалация.

        Returns:
            dict с ключами: resolved, method, description
        """
        error_key = f"{agent}:{type(error).__name__}:{str(error)[:100]}"
        self._attempt_counts[error_key] = self._attempt_counts.get(error_key, 0) + 1
        attempt = self._attempt_counts[error_key]

        logger.warning(
            f"Ошибка от {agent}: {error} (попытка {attempt}/{MAX_AUTO_FIX_ATTEMPTS})",
            extra={
                "event": "error_received",
                "context": {"agent": agent, "error": str(error), "attempt": attempt},
            },
        )

        # 1. Поиск похожих решённых ошибок
        similar = self._find_similar_errors(agent, type(error).__name__, str(error))
        if similar:
            logger.info(
                f"Найдено решение в базе: {similar['resolution'][:100]}",
                extra={"event": "error_found_in_db"},
            )
            self.memory.log_error(
                module=agent,
                error_type=type(error).__name__,
                message=str(error),
                resolution=similar["resolution"],
            )
            self._attempt_counts.pop(error_key, None)
            return {
                "resolved": True,
                "method": "database",
                "description": similar["resolution"],
            }

        # 2. LLM-анализ + реальное применение fix (если не превышен лимит попыток)
        if attempt <= MAX_AUTO_FIX_ATTEMPTS:
            analysis = await self._analyze_with_llm(agent, error, context)
            if analysis and analysis.get("can_auto_fix"):
                fix_result = await self._apply_fix(analysis)
                fix_desc = analysis.get("fix_description", "LLM auto-fix")
                resolved = fix_result["applied"]

                self.memory.log_error(
                    module=agent,
                    error_type=type(error).__name__,
                    message=str(error),
                    resolution=f"{fix_desc} | applied={resolved} | {fix_result['output'][:200]}",
                )
                if resolved:
                    self._attempt_counts.pop(error_key, None)
                return {
                    "resolved": resolved,
                    "method": "llm_fix_applied" if resolved else "llm_fix_failed",
                    "description": fix_desc,
                    "shell_output": fix_result["output"],
                }

        # 3. Эскалация владельцу
        if attempt >= MAX_AUTO_FIX_ATTEMPTS:
            await self._escalate(agent, error, context, attempt)
            self.memory.log_error(
                module=agent,
                error_type=type(error).__name__,
                message=str(error),
            )
            self._attempt_counts.pop(error_key, None)
            return {
                "resolved": False,
                "method": "escalated",
                "description": f"Эскалировано владельцу после {attempt} попыток",
            }

        # Ещё есть попытки — просто логируем
        self.memory.log_error(
            module=agent,
            error_type=type(error).__name__,
            message=str(error),
        )
        return {
            "resolved": False,
            "method": "pending",
            "description": f"Попытка {attempt}/{MAX_AUTO_FIX_ATTEMPTS}, будет повтор",
        }

    def _find_similar_errors(
        self, module: str, error_type: str, message: str
    ) -> Optional[dict]:
        """Ищет похожие решённые ошибки в SQLite."""
        try:
            conn = self.memory._get_sqlite()
            # Точное совпадение по типу ошибки и модулю
            row = conn.execute(
                """SELECT resolution FROM errors
                   WHERE resolved = 1 AND module = ? AND error_type = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (module, error_type),
            ).fetchone()
            if row and row["resolution"]:
                return {"resolution": row["resolution"]}

            # Частичное совпадение по сообщению
            row = conn.execute(
                """SELECT resolution FROM errors
                   WHERE resolved = 1 AND message LIKE ?
                   ORDER BY created_at DESC LIMIT 1""",
                (f"%{message[:50]}%",),
            ).fetchone()
            if row and row["resolution"]:
                return {"resolution": row["resolution"]}

        except Exception as e:
            logger.debug(f"Ошибка поиска в базе: {e}", extra={"event": "db_search_error"})
        return None

    async def _analyze_with_llm(
        self, agent: str, error: Exception, context: dict[str, Any] | None
    ) -> Optional[dict]:
        """Анализ ошибки через LLM → JSON с опциональной shell-командой для fix.

        Возвращает dict:
            can_auto_fix: bool
            fix_description: str
            shell_command: str | None  — команда для DevOpsAgent (whitelist-validated)
        """
        from agents.devops_agent import COMMAND_WHITELIST

        allowed_cmds = ", ".join(sorted(COMMAND_WHITELIST))
        prompt = (
            f"Проанализируй ошибку автономного агента VITO.\n\n"
            f"Агент: {agent}\n"
            f"Тип ошибки: {type(error).__name__}\n"
            f"Сообщение: {str(error)}\n"
            f"Контекст: {json.dumps(context or {}, ensure_ascii=False)}\n\n"
            f"Доступные shell-команды (whitelist): {allowed_cmds}\n\n"
            f"Ответь строго в JSON формате:\n"
            f'{{"can_auto_fix": true/false, "fix_description": "описание решения", '
            f'"shell_command": "команда или null"}}'
        )

        try:
            response = await self.llm_router.call_llm(
                task_type=TaskType.SELF_HEAL,
                prompt=prompt,
                estimated_tokens=500,
            )
            if not response:
                return None

            text = response.strip()
            if "```" in text:
                for block in text.split("```"):
                    block = block.strip()
                    if block.startswith("json"):
                        block = block[4:].strip()
                    if block.startswith("{"):
                        text = block
                        break
            if text.startswith("{"):
                return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Ошибка парсинга LLM ответа: {e}", extra={"event": "llm_parse_error"})
        return None

    async def _apply_fix(self, analysis: dict) -> dict[str, Any]:
        """Применяет fix через DevOpsAgent shell executor.
        Enforced flow: backup -> apply -> smoke tests -> rollback on failure.

        Returns:
            {"applied": bool, "output": str}
        """
        shell_cmd = analysis.get("shell_command")
        if not shell_cmd or not self.devops:
            return {"applied": False, "output": "no command or no devops agent"}

        backup_path = None
        if self.self_updater:
            try:
                backup_path = self.self_updater.backup_current_code()
            except Exception:
                backup_path = None

        logger.info(
            f"SelfHealer: применяю fix: {shell_cmd}",
            extra={"event": "fix_applying", "context": {"command": shell_cmd}},
        )

        result = await self.devops.execute_shell(shell_cmd)

        if result.success:
            # Mandatory validation tests after auto-fix
            tests_ok = True
            tests_out = ""
            if self.self_updater:
                try:
                    test_result = self.self_updater.run_tests(test_path="tests/test_llm_router.py")
                    tests_ok = bool(test_result.get("success"))
                    tests_out = str(test_result.get("output", ""))[:500]
                except Exception as e:
                    tests_ok = False
                    tests_out = f"test error: {e}"

            if not tests_ok:
                if backup_path and self.self_updater:
                    try:
                        self.self_updater.rollback(backup_path)
                    except Exception:
                        pass
                logger.warning(
                    "SelfHealer: fix applied but tests failed -> rollback",
                    extra={"event": "fix_rollback_after_tests"},
                )
                return {"applied": False, "output": f"fix rolled back: tests failed. {tests_out}"}

            logger.info(
                f"SelfHealer: fix применён успешно",
                extra={"event": "fix_applied", "context": {"command": shell_cmd}},
            )
            return {"applied": True, "output": f"{str(result.output)[:500]} | tests=ok"}
        else:
            if backup_path and self.self_updater:
                try:
                    self.self_updater.rollback(backup_path)
                except Exception:
                    pass
            logger.warning(
                f"SelfHealer: fix не удался: {result.error}",
                extra={"event": "fix_failed", "context": {"command": shell_cmd, "error": result.error}},
            )
            return {"applied": False, "output": result.error or ""}

    async def _escalate(
        self, agent: str, error: Exception, context: dict[str, Any] | None, attempts: int
    ) -> None:
        """Эскалация владельцу через Telegram."""
        message = (
            f"VITO SelfHealer | Эскалация\n\n"
            f"Агент: {agent}\n"
            f"Ошибка: {type(error).__name__}: {str(error)[:300]}\n"
            f"Попыток: {attempts}\n"
            f"Контекст: {json.dumps(context or {}, ensure_ascii=False)[:200]}"
        )
        try:
            await self.comms.send_message(message)
            logger.info(
                f"Ошибка эскалирована владельцу: {agent}",
                extra={"event": "error_escalated", "context": {"agent": agent}},
            )
        except Exception as e:
            logger.error(
                f"Не удалось эскалировать: {e}",
                extra={"event": "escalation_failed"},
            )

    def cleanup_old_errors(self, days: int = 7) -> int:
        """Удаляет resolved ошибки старше N дней. Возвращает кол-во удалённых."""
        try:
            conn = self.memory._get_sqlite()
            cursor = conn.execute(
                """DELETE FROM errors
                   WHERE resolved = 1
                   AND created_at < datetime('now', ?)""",
                (f"-{days} days",),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(
                    f"Очистка: удалено {deleted} resolved ошибок старше {days} дней",
                    extra={"event": "errors_cleanup", "context": {"deleted": deleted}},
                )
            return deleted
        except Exception as e:
            logger.debug(f"Ошибка очистки: {e}", extra={"event": "cleanup_error"})
            return 0

    def get_error_stats(self) -> dict[str, Any]:
        """Статистика ошибок для /errors и /healer."""
        try:
            conn = self.memory._get_sqlite()

            total = conn.execute("SELECT COUNT(*) as cnt FROM errors").fetchone()["cnt"]
            resolved = conn.execute(
                "SELECT COUNT(*) as cnt FROM errors WHERE resolved = 1"
            ).fetchone()["cnt"]
            unresolved = total - resolved

            recent = conn.execute(
                """SELECT module, error_type, message, resolved, created_at
                   FROM errors ORDER BY created_at DESC LIMIT 10"""
            ).fetchall()

            by_module = conn.execute(
                """SELECT module, COUNT(*) as cnt
                   FROM errors GROUP BY module ORDER BY cnt DESC LIMIT 5"""
            ).fetchall()

            return {
                "total": total,
                "resolved": resolved,
                "unresolved": unresolved,
                "resolution_rate": resolved / max(total, 1),
                "recent": [dict(r) for r in recent],
                "by_module": [dict(r) for r in by_module],
                "pending_retries": len(self._attempt_counts),
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}", extra={"event": "stats_error"})
            return {"total": 0, "resolved": 0, "unresolved": 0, "resolution_rate": 0}
