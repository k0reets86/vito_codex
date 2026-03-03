import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone
from config.paths import root_path

LOG_DIR = root_path("logs")
MAIN_LOG = os.path.join(LOG_DIR, "vito.log")
ERROR_LOG = os.path.join(LOG_DIR, "errors.log")
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

# Ensure log dir exists
os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Структурированный JSON-формат логов по спецификации DevOps Agent."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "agent": getattr(record, "agent", "system"),
            "event": getattr(record, "event", record.funcName),
            "message": record.getMessage(),
            "context": getattr(record, "context", {}),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["traceback"] = self.formatException(record.exc_info)
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            entry["duration_ms"] = duration
        return json.dumps(entry, ensure_ascii=False)


class _AgentFilter(logging.Filter):
    """Per-logger filter that sets default 'agent' field on records.

    Unlike setLogRecordFactory (which is GLOBAL and causes KeyError
    when multiple modules overwrite it), a Filter is scoped to its logger.
    """

    def __init__(self, agent: str):
        super().__init__()
        self._agent = agent

    def filter(self, record: logging.LogRecord) -> bool:
        # Set default agent if not provided via extra={}
        if not hasattr(record, "agent"):
            record.agent = self._agent
        # Ensure optional fields exist so JsonFormatter doesn't fail
        if not hasattr(record, "event"):
            record.event = record.funcName
        if not hasattr(record, "context"):
            record.context = {}
        return True


# Shared handlers — created once, reused across all loggers
_handlers_initialized = False
_main_handler: logging.Handler | None = None
_error_handler: logging.Handler | None = None
_console_handler: logging.Handler | None = None


def _ensure_handlers() -> tuple[logging.Handler, logging.Handler, logging.Handler]:
    global _handlers_initialized, _main_handler, _error_handler, _console_handler
    if _handlers_initialized:
        return _main_handler, _error_handler, _console_handler

    formatter = JsonFormatter()

    _main_handler = logging.handlers.RotatingFileHandler(
        MAIN_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    _main_handler.setLevel(logging.DEBUG)
    _main_handler.setFormatter(formatter)

    _error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    _error_handler.setLevel(logging.ERROR)
    _error_handler.setFormatter(formatter)

    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )

    _handlers_initialized = True
    return _main_handler, _error_handler, _console_handler


def get_logger(name: str = "vito", agent: str = "system") -> logging.Logger:
    """Возвращает настроенный логгер с ротацией.

    Args:
        name: имя логгера (обычно имя модуля)
        agent: идентификатор агента для JSON-лога
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    main_h, error_h, console_h = _ensure_handlers()
    logger.addHandler(main_h)
    logger.addHandler(error_h)
    logger.addHandler(console_h)

    # Per-logger filter instead of global setLogRecordFactory
    logger.addFilter(_AgentFilter(agent))

    return logger
