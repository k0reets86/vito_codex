"""Tests for captcha_solver module."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.captcha_solver import CaptchaSolver, DB_PATH


def test_balance():
    """Check anti-captcha account balance."""
    solver = CaptchaSolver.get_instance()
    balance = solver.get_balance()
    print(f"Anti-Captcha balance: ${balance:.4f}")
    assert balance >= 0, "Balance should be non-negative"


def test_singleton():
    """Verify singleton pattern."""
    a = CaptchaSolver.get_instance()
    b = CaptchaSolver.get_instance()
    assert a is b, "Should be same instance"
    print("Singleton: OK")


def test_db_table_exists():
    """Verify captcha_logs table was created."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='captcha_logs'")
    tables = cursor.fetchall()
    conn.close()
    assert len(tables) == 1, "captcha_logs table should exist"
    print("DB table: OK")


if __name__ == "__main__":
    test_singleton()
    test_db_table_exists()
    balance = test_balance()
    print(f"\nAll tests passed. Balance: ${balance:.4f}")
