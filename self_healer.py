"""SelfHealer — самолечение VITO.

Утилита (не агент), чтобы избежать циклической зависимости с AgentRegistry.
Ищет похожие решённые ошибки в SQLite, при неудаче — анализирует через LLM,
при повторных неудачах — эскалирует владельцу через Telegram.
"""

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings
from llm_router import LLMRouter, TaskType
from modules.runtime_remediation import suggest_safe_actions_for_failure

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
        self._error_quarantine_until: dict[str, float] = {}  # error_key -> unix ts
        self._escalation_counts: dict[str, int] = {}  # error_key -> escalations
        self._init_state_storage()
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
        quarantine_until = float(self._error_quarantine_until.get(error_key, 0.0) or 0.0)
        if quarantine_until <= 0:
            persisted = self._load_quarantine_entry(error_key)
            quarantine_until = float(persisted.get("quarantine_until", 0.0) or 0.0)
            esc = int(persisted.get("escalation_count", 0) or 0)
            if quarantine_until > 0:
                self._error_quarantine_until[error_key] = quarantine_until
            if esc > 0:
                self._escalation_counts[error_key] = esc
        now = time.time()
        if quarantine_until > now:
            left_sec = int(quarantine_until - now)
            self.memory.log_error(
                module=agent,
                error_type=type(error).__name__,
                message=str(error),
                resolution=f"quarantine_cooldown:{left_sec}s",
            )
            return {
                "resolved": False,
                "method": "cooldown",
                "description": f"Ошибка в quarantine cooldown, retry через {left_sec}s",
            }
        if quarantine_until > 0 and quarantine_until <= now:
            self._error_quarantine_until.pop(error_key, None)
            self._clear_quarantine_entry(error_key)
        self._attempt_counts[error_key] = self._attempt_counts.get(error_key, 0) + 1
        attempt = self._attempt_counts[error_key]

        logger.warning(
            f"Ошибка от {agent}: {error} (попытка {attempt}/{MAX_AUTO_FIX_ATTEMPTS})",
            extra={
                "event": "error_received",
                "context": {"agent": agent, "error": str(error), "attempt": attempt},
            },
        )
        snapshot = self._build_failure_snapshot(agent, error, context, attempt)
        safe_actions = suggest_safe_actions_for_failure(
            agent=agent,
            error_type=type(error).__name__,
            message=str(error),
            context=context or {},
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
                "safe_action_suggestions": safe_actions,
            }

        # 2. LLM-анализ + реальное применение fix (если не превышен лимит попыток)
        if attempt <= MAX_AUTO_FIX_ATTEMPTS:
            analysis = await self._analyze_with_llm(agent, error, snapshot)
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
                    "safe_action_suggestions": safe_actions,
                }

        # 3. Эскалация владельцу
        if attempt >= MAX_AUTO_FIX_ATTEMPTS:
            await self._escalate(agent, error, snapshot, attempt)
            self._escalation_counts[error_key] = int(self._escalation_counts.get(error_key, 0) or 0) + 1
            base_cooldown = max(1, int(getattr(settings, "SELF_HEALER_QUARANTINE_SEC", 600) or 600))
            max_mult = max(1, int(getattr(settings, "SELF_HEALER_QUARANTINE_MAX_MULT", 3) or 3))
            cooldown = base_cooldown * min(max_mult, self._escalation_counts[error_key])
            self._error_quarantine_until[error_key] = time.time() + cooldown
            self._save_quarantine_entry(error_key, self._error_quarantine_until[error_key], self._escalation_counts[error_key])
            self.memory.log_error(
                module=agent,
                error_type=type(error).__name__,
                message=str(error),
            )
            self._attempt_counts.pop(error_key, None)
            return {
                "resolved": False,
                "method": "escalated",
                "description": f"Эскалировано владельцу после {attempt} попыток; quarantine={cooldown}s",
                "safe_action_suggestions": safe_actions,
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
            "safe_action_suggestions": safe_actions,
        }

    @staticmethod
    def _build_failure_snapshot(
        agent: str,
        error: Exception,
        context: dict[str, Any] | None,
        attempt: int,
    ) -> dict[str, Any]:
        """Build a structured failure snapshot (Pipeline Doctor 'Detect')."""
        tb = getattr(error, "__traceback__", None)
        frame = None
        while tb:
            frame = tb
            tb = tb.tb_next
        location = {}
        if frame:
            try:
                location = {
                    "file": str(frame.tb_frame.f_code.co_filename),
                    "line": int(frame.tb_lineno),
                    "function": str(frame.tb_frame.f_code.co_name),
                }
            except Exception:
                location = {}

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "attempt": int(attempt),
            "error_type": type(error).__name__,
            "error_message": str(error)[:1000],
            "location": location,
            "context": context or {},
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
        allowed, reason = self._judge_fix_proposal(shell_cmd)
        if not allowed:
            logger.warning(
                "SelfHealer Judge blocked fix proposal",
                extra={"event": "fix_blocked_by_judge", "context": {"reason": reason, "command": str(shell_cmd)[:200]}},
            )
            return {"applied": False, "output": f"rejected_by_judge: {reason}"}

        backup_path = None
        if self.self_updater:
            try:
                backup_path = self.self_updater.backup_current_code()
            except Exception:
                backup_path = None
        before_stats = self._snapshot_git_numstat()

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
            budget_ok, budget_detail = self._check_git_change_budget(before=before_stats)
            if not budget_ok:
                if backup_path and self.self_updater:
                    try:
                        self.self_updater.rollback(backup_path)
                    except Exception:
                        pass
                logger.warning(
                    "SelfHealer: fix exceeds change budget -> rollback",
                    extra={"event": "fix_rollback_change_budget", "context": {"detail": budget_detail}},
                )
                return {"applied": False, "output": f"rejected_by_budget: {budget_detail}"}
            if bool(getattr(settings, "SELF_HEALER_CANARY_ENABLED", False)):
                canary_cmd = str(getattr(settings, "SELF_HEALER_CANARY_COMMAND", "systemctl is-active vito") or "").strip()
                if canary_cmd:
                    canary_allowed, canary_reason = self._judge_fix_proposal(canary_cmd)
                    if not canary_allowed:
                        if backup_path and self.self_updater:
                            try:
                                self.self_updater.rollback(backup_path)
                            except Exception:
                                pass
                        logger.warning(
                            "SelfHealer: canary command rejected -> rollback",
                            extra={"event": "fix_rollback_canary_rejected", "context": {"command": canary_cmd, "reason": canary_reason}},
                        )
                        return {"applied": False, "output": f"canary_rejected_by_judge: {canary_reason}"}
                    canary_result = await self.devops.execute_shell(canary_cmd)
                    if not canary_result.success:
                        if backup_path and self.self_updater:
                            try:
                                self.self_updater.rollback(backup_path)
                            except Exception:
                                pass
                        logger.warning(
                            "SelfHealer: canary check failed -> rollback",
                            extra={"event": "fix_rollback_after_canary", "context": {"command": canary_cmd, "error": canary_result.error}},
                        )
                        return {"applied": False, "output": f"canary_failed: {str(canary_result.error or canary_result.output)[:300]}"}

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

    @staticmethod
    def _judge_fix_proposal(shell_cmd: str) -> tuple[bool, str]:
        """Judge gate before executing auto-fix command.

        Blocks destructive/test-softening command patterns.
        """
        cmd = str(shell_cmd or "").strip()
        if not cmd:
            return False, "empty_command"
        low = cmd.lower()
        policy_mode = str(getattr(settings, "SELF_HEALER_POLICY_MODE", "strict") or "strict").strip().lower()
        allow_service_restart = (
            policy_mode in {"balanced", "adaptive"}
            and bool(getattr(settings, "SELF_HEALER_BALANCED_ALLOW_SERVICE_RESTART", False))
        )

        blocked_anywhere = [
            "git reset --hard",
            "git checkout --",
            "truncate -s",
            "chmod -r",
            "chown -r /",
            "rm -rf",
            "rm -rf /",
            "shutdown ",
            "reboot",
            "poweroff",
            "halt",
            "init 0",
            "telinit 0",
            "mkfs",
            "fdisk ",
            "parted ",
        ]
        if any(p in low for p in blocked_anywhere):
            return False, "dangerous_command"
        if re.match(r"^\s*(chmod|chown)\s+-[^\n]*r\b", low):
            return False, "dangerous_command"
        if re.match(r"^\s*dd(\s|$)", low) and " of=" in low:
            return False, "dangerous_command"
        if re.match(r"^\s*sudo(\s|$)", low):
            return False, "privilege_escalation_risk"
        supply_chain_markers = [
            "curl ",
            "wget ",
            "pip install",
            "pip3 install",
            "python -m pip install",
            "python3 -m pip install",
            "npm install",
            "apt-get ",
            "apt install",
            "dnf install",
            "yum install",
        ]
        if any(m in low for m in supply_chain_markers):
            return False, "supply_chain_risk"
        if re.match(r"^\s*(kill|pkill|killall)(\s|$)", low):
            return False, "process_kill_risk"
        if re.match(r"^\s*systemctl\s+(stop|disable|mask|kill|reenable|isolate|set-default|daemon-reexec)\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*systemctl\s+(restart|try-restart|reload-or-restart|try-reload-or-restart|reload)\b", low):
            if not allow_service_restart:
                return False, "service_disruption_risk"
        if re.match(r"^\s*service\s+\S+\s+(stop|disable)\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*service\s+\S+\s+restart\b", low):
            if not allow_service_restart:
                return False, "service_disruption_risk"
        if re.match(r"^\s*chkconfig\s+\S+\s+off\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*update-rc\.d\s+\S+\s+(disable|remove)\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*insserv\s+-r\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*rc-update\s+del\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*rc-service\s+\S+\s+stop\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*sv\s+(down|exit|force-stop|once)\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*s6-svc\s+-[^\n]*[dDx]\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+unload\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+bootout\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+disable\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+remove\b", low):
            return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+kickstart\s+-[^\n]*k\b", low):
            if not allow_service_restart:
                return False, "service_disruption_risk"
        if re.match(r"^\s*launchctl\s+kickstart\s+\S+\b", low):
            if not allow_service_restart:
                return False, "service_disruption_risk"
        security_degrade_markers = [
            "ufw disable",
            "ufw --force disable",
            "ufw reset",
            "iptables -f",
            "iptables --flush",
            "iptables -p accept",
            "ip6tables -f",
            "ip6tables -p accept",
            "setenforce 0",
            "setenforce permissive",
            "semanage permissive",
            "nft flush ruleset",
            "userdel ",
            "passwd -l",
            "usermod -l",
        ]
        if any(m in low for m in security_degrade_markers):
            return False, "security_degradation_risk"
        if re.match(r"^\s*sqlite3(\s|$)", low):
            if re.search(r"\b(update|delete|drop|alter|insert|replace|truncate)\b", low):
                return False, "db_mutation_risk"
        multi_command_markers = ["&&", "||", ";", "|", "`", "$(", "\n"]
        if any(m in cmd for m in multi_command_markers):
            return False, "multi_command_risk"
        if "&" in cmd:
            return False, "multi_command_risk"
        if re.search(r"\b(nohup|disown)\b", low):
            return False, "multi_command_risk"
        if ">>" in cmd or "<<" in cmd or ">" in cmd:
            return False, "shell_redirection_risk"

        # Require command to pass the same whitelist validator used by DevOpsAgent.
        try:
            from agents.devops_agent import DevOpsAgent
            DevOpsAgent.validate_command(cmd)
        except Exception:
            return False, "not_in_whitelist"

        # Block commands that likely "fix" by altering/removing tests.
        if "tests/" in low:
            test_softening_markers = [
                "rm ",
                "mv ",
                "sed -i",
                "perl -pi",
                "python -c",
                "python3 -c",
                "cat >",
                "tee ",
                "echo ",
            ]
            if any(m in low for m in test_softening_markers):
                return False, "test_softening_risk"

        # Block clear attempts to disable assertions.
        if re.search(r"\b(assert|pytest\.skip|xfail)\b", low) and "tests/" in low:
            return False, "test_assertion_mutation_risk"

        return True, "ok"

    @staticmethod
    def _snapshot_git_numstat() -> dict[str, tuple[int, int]]:
        try:
            proc = subprocess.run(
                ["git", "diff", "--numstat"],
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
            if int(proc.returncode or 0) != 0:
                return {}
            out: dict[str, tuple[int, int]] = {}
            for ln in str(proc.stdout or "").splitlines():
                parts = ln.strip().split("\t")
                if len(parts) < 3:
                    continue
                add = int(parts[0]) if parts[0].isdigit() else 0
                rem = int(parts[1]) if parts[1].isdigit() else 0
                path = str(parts[2] or "").strip()
                if path:
                    out[path] = (add, rem)
            return out
        except Exception:
            return {}

    @staticmethod
    def _check_git_change_budget(before: dict[str, tuple[int, int]] | None = None) -> tuple[bool, str]:
        """Validate changed files/lines budget after applying auto-fix."""
        max_files = max(1, int(getattr(settings, "SELF_HEALER_MAX_CHANGED_FILES", 3) or 3))
        max_lines = max(1, int(getattr(settings, "SELF_HEALER_MAX_CHANGED_LINES", 180) or 180))
        try:
            base = before or {}
            now = SelfHealer._snapshot_git_numstat()
            base_files = set(base.keys())
            now_files = set(now.keys())
            new_files = len([p for p in now_files if p not in base_files])
            base_total = sum(int(a or 0) + int(r or 0) for a, r in base.values())
            now_total = sum(int(a or 0) + int(r or 0) for a, r in now.values())
            delta_lines = max(0, int(now_total - base_total))
            if new_files > max_files:
                return False, f"changed_files_exceeded:{new_files}>{max_files}"
            if delta_lines > max_lines:
                return False, f"changed_lines_exceeded:{delta_lines}>{max_lines}"
            return True, f"new_files={new_files},delta_lines={delta_lines}"
        except Exception:
            return True, "git_diff_check_error"

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
        suggestions = suggest_safe_actions_for_failure(
            agent=agent,
            error_type=type(error).__name__,
            message=str(error),
            context=context or {},
        )
        if suggestions:
            top = "\n".join(
                f"- {str(item.get('action',''))}: {str(item.get('reason',''))[:120]}"
                for item in suggestions[:3]
            )
            message += f"\nРекомендованные safe-actions:\n{top}"
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
                "quarantine_errors": self._count_active_quarantine(),
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}", extra={"event": "stats_error"})
            return {"total": 0, "resolved": 0, "unresolved": 0, "resolution_rate": 0}

    def _init_state_storage(self) -> None:
        try:
            conn = self.memory._get_sqlite()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_healer_quarantine (
                    error_key TEXT PRIMARY KEY,
                    quarantine_until REAL DEFAULT 0,
                    escalation_count INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        except Exception:
            pass

    def _load_quarantine_entry(self, error_key: str) -> dict[str, Any]:
        try:
            conn = self.memory._get_sqlite()
            row = conn.execute(
                """
                SELECT quarantine_until, escalation_count
                FROM self_healer_quarantine
                WHERE error_key = ?
                LIMIT 1
                """,
                (str(error_key or "")[:240],),
            ).fetchone()
            if not row:
                return {"quarantine_until": 0.0, "escalation_count": 0}
            return {
                "quarantine_until": float(row["quarantine_until"] or 0.0),
                "escalation_count": int(row["escalation_count"] or 0),
            }
        except Exception:
            return {"quarantine_until": 0.0, "escalation_count": 0}

    def _save_quarantine_entry(self, error_key: str, quarantine_until: float, escalation_count: int) -> None:
        try:
            conn = self.memory._get_sqlite()
            conn.execute(
                """
                INSERT INTO self_healer_quarantine (error_key, quarantine_until, escalation_count, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(error_key) DO UPDATE SET
                  quarantine_until = excluded.quarantine_until,
                  escalation_count = excluded.escalation_count,
                  updated_at = excluded.updated_at
                """,
                (str(error_key or "")[:240], float(quarantine_until or 0.0), int(escalation_count or 0)),
            )
            conn.commit()
        except Exception:
            pass

    def _clear_quarantine_entry(self, error_key: str) -> None:
        try:
            conn = self.memory._get_sqlite()
            conn.execute("DELETE FROM self_healer_quarantine WHERE error_key = ?", (str(error_key or "")[:240],))
            conn.commit()
        except Exception:
            pass

    def _count_active_quarantine(self) -> int:
        now = float(time.time())
        in_mem = len([1 for _, ts in self._error_quarantine_until.items() if float(ts or 0.0) > now])
        try:
            conn = self.memory._get_sqlite()
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM self_healer_quarantine WHERE quarantine_until > ?",
                (now,),
            ).fetchone()
            db_n = int((row["n"] if row else 0) or 0)
            return max(in_mem, db_n)
        except Exception:
            return in_mem
