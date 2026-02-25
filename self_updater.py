"""SelfUpdater — самообновление VITO.

Поддерживает: git pull с тестированием, применение патчей,
бэкапы и откаты кода.
"""

import shutil
import subprocess
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("self_updater", agent="self_updater")

PROJECT_ROOT = Path(__file__).parent


class SelfUpdater:
    def __init__(self, memory, comms, backup_dir: str = "backups"):
        self.memory = memory
        self.comms = comms
        self.backup_dir = PROJECT_ROOT / backup_dir
        self.backup_dir.mkdir(exist_ok=True)
        self._init_db()
        logger.info("SelfUpdater инициализирован", extra={"event": "init"})

    def _init_db(self) -> None:
        """Создаёт таблицу update_history в SQLite."""
        try:
            conn = self.memory._get_sqlite()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS update_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_type TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    backup_path TEXT DEFAULT '',
                    test_passed INTEGER DEFAULT 0,
                    test_failed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    details TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        except Exception as e:
            logger.warning(f"Ошибка создания таблицы update_history: {e}", extra={"event": "db_init_error"})

    async def update_from_git(self, branch: str = "main") -> dict[str, Any]:
        """Обновление из git: backup → git pull → pytest → keep/rollback."""
        logger.info(f"Начало обновления из git branch={branch}", extra={"event": "git_update_start"})

        # 1. Backup
        backup_path = self.backup_current_code()
        if not backup_path:
            return {"success": False, "error": "Не удалось создать бэкап"}

        # 2. Git pull
        try:
            pull_result = subprocess.run(
                ["git", "pull", "origin", branch],
                capture_output=True, text=True, timeout=60,
                cwd=str(PROJECT_ROOT),
            )
            if pull_result.returncode != 0:
                self.rollback(backup_path)
                self._record_update("git_pull", branch, backup_path, 0, 0, "failed", pull_result.stderr)
                return {"success": False, "error": f"git pull failed: {pull_result.stderr}"}
        except subprocess.TimeoutExpired:
            self.rollback(backup_path)
            return {"success": False, "error": "git pull timeout"}

        # 3. Tests
        test_result = self.run_tests()

        if test_result["success"]:
            self._record_update("git_pull", branch, backup_path, test_result["passed"], test_result["failed"], "applied")
            await self._notify_update("git_pull", branch, test_result)
            logger.info(
                f"Обновление из git успешно: {test_result['passed']} тестов пройдено",
                extra={"event": "git_update_success"},
            )
            return {"success": True, "tests": test_result, "backup": backup_path}

        # 4. Rollback
        logger.warning("Тесты не прошли — откат", extra={"event": "git_update_rollback"})
        self.rollback(backup_path)
        self._record_update("git_pull", branch, backup_path, test_result["passed"], test_result["failed"], "rolled_back")
        return {"success": False, "error": "Tests failed after update", "tests": test_result, "rolled_back": True}

    async def apply_patch(self, patch_content: str, source: str = "manual") -> dict[str, Any]:
        """Применяет патч: проверка protected → backup → apply → test → keep/rollback."""
        logger.info(f"Применение патча из {source}", extra={"event": "patch_start"})

        # Проверка PROTECTED_FILES
        from code_generator import PROTECTED_FILES
        for line in patch_content.split("\n"):
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                filepath = line.split("/", 1)[-1] if "/" in line else ""
                filepath = filepath.strip()
                if filepath in PROTECTED_FILES:
                    logger.warning(
                        f"Патч затрагивает защищённый файл: {filepath}",
                        extra={"event": "protected_file_in_patch", "context": {"file": filepath}},
                    )
                    return {"success": False, "error": f"Protected file: {filepath}"}

        backup_path = self.backup_current_code()
        if not backup_path:
            return {"success": False, "error": "Не удалось создать бэкап"}

        # Apply patch
        try:
            proc = subprocess.run(
                ["git", "apply", "--check", "-"],
                input=patch_content, capture_output=True, text=True, timeout=30,
                cwd=str(PROJECT_ROOT),
            )
            if proc.returncode != 0:
                self._record_update("patch", source, backup_path, 0, 0, "failed", proc.stderr)
                return {"success": False, "error": f"Patch check failed: {proc.stderr}"}

            subprocess.run(
                ["git", "apply", "-"],
                input=patch_content, capture_output=True, text=True, timeout=30,
                cwd=str(PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Patch apply timeout"}

        # Test
        test_result = self.run_tests()

        if test_result["success"]:
            self._record_update("patch", source, backup_path, test_result["passed"], test_result["failed"], "applied")
            await self._notify_update("patch", source, test_result)
            return {"success": True, "tests": test_result, "backup": backup_path}

        # Rollback
        self.rollback(backup_path)
        self._record_update("patch", source, backup_path, test_result["passed"], test_result["failed"], "rolled_back")
        return {"success": False, "error": "Tests failed after patch", "tests": test_result, "rolled_back": True}

    def backup_current_code(self) -> Optional[str]:
        """Создаёт timestamped бэкап текущего кода."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        try:
            # Копируем только .py файлы и конфиги, не venv/node_modules/chroma_db
            ignore = shutil.ignore_patterns(
                "*.pyc", "__pycache__", ".git", "venv", "node_modules",
                "backups", "chroma_db", "*.db", "logs",
            )
            shutil.copytree(PROJECT_ROOT, backup_path, ignore=ignore)
            logger.info(
                f"Бэкап создан: {backup_path}",
                extra={"event": "backup_created", "context": {"path": str(backup_path)}},
            )
            return str(backup_path)
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}", extra={"event": "backup_failed"}, exc_info=True)
            return None

    def rollback(self, backup_path: str) -> bool:
        """Откатывает код из бэкапа."""
        bp = Path(backup_path)
        if not bp.exists():
            logger.error(f"Бэкап не найден: {backup_path}", extra={"event": "rollback_no_backup"})
            return False

        try:
            # Удаляем текущие .py файлы
            for py_file in PROJECT_ROOT.glob("*.py"):
                py_file.unlink()

            # Копируем из бэкапа
            for item in bp.iterdir():
                dest = PROJECT_ROOT / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            logger.info(
                f"Откат выполнен из {backup_path}",
                extra={"event": "rollback_success"},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отката: {e}", extra={"event": "rollback_failed"}, exc_info=True)
            return False

    def run_tests(self, test_path: str = "tests/") -> dict[str, Any]:
        """Запускает pytest и возвращает результат."""
        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest", test_path, "-n", "1", "-v", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=300,
                cwd=str(PROJECT_ROOT),
            )
            output = proc.stdout + proc.stderr

            # Парсим результат pytest
            passed = 0
            failed = 0
            for line in output.split("\n"):
                if "passed" in line:
                    import re
                    m = re.search(r"(\d+) passed", line)
                    if m:
                        passed = int(m.group(1))
                if "failed" in line:
                    import re
                    m = re.search(r"(\d+) failed", line)
                    if m:
                        failed = int(m.group(1))

            result = {
                "success": proc.returncode == 0,
                "passed": passed,
                "failed": failed,
                "output": output[-2000:],  # Последние 2000 символов
            }
            # Skill acceptance gate: finalize pending skills based on this test run.
            try:
                from modules.skill_registry import SkillRegistry
                SkillRegistry().auto_accept_pending(
                    tests_passed=bool(result["success"]),
                    evidence=f"pytest:{test_path}",
                    validator="self_updater.run_tests",
                    notes=f"passed={passed} failed={failed}",
                )
            except Exception:
                pass
            return result
        except subprocess.TimeoutExpired:
            return {"success": False, "passed": 0, "failed": 0, "output": "Test timeout (300s)"}
        except Exception as e:
            return {"success": False, "passed": 0, "failed": 0, "output": str(e)}

    def get_update_history(self, limit: int = 10) -> list[dict]:
        """История обновлений."""
        try:
            conn = self.memory._get_sqlite()
            rows = conn.execute(
                """SELECT * FROM update_history ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _record_update(
        self, update_type: str, source: str, backup_path: str,
        passed: int, failed: int, status: str, details: str = ""
    ) -> None:
        """Записывает обновление в историю."""
        try:
            conn = self.memory._get_sqlite()
            conn.execute(
                """INSERT INTO update_history
                   (update_type, source, backup_path, test_passed, test_failed, status, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (update_type, source, backup_path, passed, failed, status, details[:500]),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Ошибка записи update_history: {e}", extra={"event": "update_record_error"})

    async def _notify_update(self, update_type: str, source: str, test_result: dict) -> None:
        """Уведомляет владельца об обновлении."""
        try:
            await self.comms.send_message(
                f"VITO SelfUpdater | Обновление применено\n\n"
                f"Тип: {update_type}\n"
                f"Источник: {source}\n"
                f"Тесты: {test_result['passed']} passed, {test_result['failed']} failed"
            )
        except Exception as e:
            logger.warning(f"Ошибка уведомления: {e}", extra={"event": "notify_error"})
