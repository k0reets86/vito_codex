# Root-level conftest: патчим logger ДО импорта модулей проекта,
# чтобы тесты не падали из-за PermissionError на logs/vito.log.
import os
import tempfile

_test_log_dir = tempfile.mkdtemp(prefix="vito_test_logs_")

import config.logger as _logger_mod  # noqa: E402

_logger_mod.LOG_DIR = _test_log_dir
_logger_mod.MAIN_LOG = os.path.join(_test_log_dir, "vito.log")
_logger_mod.ERROR_LOG = os.path.join(_test_log_dir, "errors.log")
