# Root-level conftest: патчим logger и SQLite ДО импорта модулей проекта,
# чтобы тесты не писали в production БД и не падали из-за PermissionError.
import os
import tempfile

_test_log_dir = tempfile.mkdtemp(prefix="vito_test_logs_")
_test_db_dir = tempfile.mkdtemp(prefix="vito_test_db_")

import config.logger as _logger_mod  # noqa: E402

_logger_mod.LOG_DIR = _test_log_dir
_logger_mod.MAIN_LOG = os.path.join(_test_log_dir, "vito.log")
_logger_mod.ERROR_LOG = os.path.join(_test_log_dir, "errors.log")

# Защита: тесты НИКОГДА не пишут в production SQLite
import config.settings as _settings_mod  # noqa: E402

_settings_mod.settings.SQLITE_PATH = os.path.join(_test_db_dir, "test_vito.db")
_settings_mod.settings.CHROMA_PATH = os.path.join(_test_db_dir, "test_chroma")
