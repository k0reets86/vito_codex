import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone

LOG_DIR = "/home/vito/vito-agent/logs"
MAIN_LOG = os.path.join(LOG_DIR, "vito.log")
ERROR_LOG = os.path.join(LOG_DIR, "errors.log")
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5


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
    formatter = JsonFormatter()

    # Главный лог — все события
    main_handler = logging.handlers.RotatingFileHandler(
        MAIN_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(formatter)

    # Лог ошибок — только ERROR и CRITICAL
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # Консоль для разработки
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )

    logger.addHandler(main_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    # Фабрика для добавления agent по умолчанию
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "agent") or record.agent == "system":
            record.agent = agent
        return record

    logging.setLogRecordFactory(record_factory)

    return logger
