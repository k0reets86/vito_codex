"""Тесты config/logger.py."""

import json
import logging

from config.logger import JsonFormatter, get_logger


def test_json_formatter_output():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="test message", args=(), exc_info=None,
    )
    record.agent = "test_agent"
    record.event = "test_event"
    record.context = {"key": "value"}

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["agent"] == "test_agent"
    assert data["event"] == "test_event"
    assert data["message"] == "test message"
    assert data["context"]["key"] == "value"
    assert "timestamp" in data


def test_json_formatter_with_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error", args=(), exc_info=sys.exc_info(),
        )
    record.agent = "test"
    record.event = "err"
    record.context = {}

    output = formatter.format(record)
    data = json.loads(output)
    assert "traceback" in data
    assert "ValueError" in data["traceback"]


def test_json_formatter_duration():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="msg", args=(), exc_info=None,
    )
    record.agent = "test"
    record.event = "test"
    record.context = {}
    record.duration_ms = 42

    data = json.loads(formatter.format(record))
    assert data["duration_ms"] == 42


def test_get_logger_returns_logger():
    logger = get_logger("test_unit", agent="unit")
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.DEBUG


def test_get_logger_idempotent():
    l1 = get_logger("test_idem", agent="x")
    l2 = get_logger("test_idem", agent="x")
    assert l1 is l2
