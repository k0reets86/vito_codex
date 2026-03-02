"""Тесты financial_controller.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from financial_controller import (
    FinancialController,
    ExpenseCategory,
    IncomeSource,
    TransactionType,
    MONTHLY_CARD_LIMIT_USD,
)


@pytest.fixture
def fc(tmp_path):
    """FinancialController с временной БД."""
    return FinancialController(sqlite_path=str(tmp_path / "finance_test.db"))


# ── Запись транзакций ──

def test_record_expense(fc):
    tx_id = fc.record_expense(0.015, ExpenseCategory.API, agent="llm_router", description="test call")
    assert tx_id > 0


def test_record_expense_updates_daily(fc):
    fc.record_expense(1.50, ExpenseCategory.API, agent="test")
    fc.record_expense(0.50, ExpenseCategory.TOOLS, agent="test")
    assert fc.get_daily_spent() == 2.0


def test_record_income(fc):
    tx_id = fc.record_income(4.99, IncomeSource.ETSY, product_name="Template v1")
    assert tx_id > 0


def test_record_income_updates_daily(fc):
    fc.record_income(4.99, IncomeSource.ETSY)
    fc.record_income(9.99, IncomeSource.GUMROAD)
    assert fc.get_daily_earned() == 14.98


def test_record_income_creates_product(fc):
    fc.record_income(4.99, IncomeSource.ETSY, product_name="Resume Pro")
    products = fc.get_product_roi()
    assert len(products) == 1
    assert products[0]["name"] == "Resume Pro"
    assert products[0]["revenue"] == 4.99


def test_record_multiple_sales_same_product(fc):
    fc.record_income(4.99, IncomeSource.ETSY, product_name="Template A")
    fc.record_income(4.99, IncomeSource.ETSY, product_name="Template A")
    products = fc.get_product_roi()
    assert products[0]["revenue"] == 9.98
    assert products[0]["units_sold"] == 2


# ── Лимиты ──

def test_check_expense_auto(fc):
    result = fc.check_expense(1.50)
    assert result["allowed"] is True
    assert result["action"] == "auto"


def test_check_expense_blocked_over_daily(fc):
    fc.record_expense(9.0, ExpenseCategory.API)
    result = fc.check_expense(2.0)
    assert result["allowed"] is False
    assert result["action"] == "blocked"


def test_check_expense_approve_threshold(fc):
    with patch("financial_controller.settings") as s:
        s.DAILY_LIMIT_USD = 1000.0
        s.OPERATION_MAX_USD = 100.0
        s.OPERATION_NOTIFY_USD = 20.0
        s.OPERATION_APPROVE_USD = 50.0
        result = fc.check_expense(55.0)
    assert result["allowed"] is False
    assert result["action"] == "approve"


def test_check_expense_notify_threshold(fc):
    with patch("financial_controller.settings") as s:
        s.DAILY_LIMIT_USD = 1000.0
        s.OPERATION_MAX_USD = 100.0
        s.OPERATION_NOTIFY_USD = 20.0
        s.OPERATION_APPROVE_USD = 50.0
        result = fc.check_expense(25.0)
    assert result["allowed"] is True
    assert result["action"] == "notify"


def test_check_expense_remaining(fc):
    from config.settings import settings
    fc.record_expense(3.0, ExpenseCategory.API)
    result = fc.check_expense(2.0)
    expected_remaining = max(settings.DAILY_LIMIT_USD - 3.0 - 2.0, 0)
    assert result["remaining"] == expected_remaining


def test_check_monthly_card_ok(fc):
    result = fc.check_monthly_card(10.0)
    assert result["allowed"] is True


def test_check_monthly_card_exceeded(fc):
    fc.record_expense(45.0, ExpenseCategory.CARD)
    result = fc.check_monthly_card(10.0)
    assert result["allowed"] is False


# ── Аналитика ──

def test_get_spend_by_agent(fc):
    fc.record_expense(0.01, ExpenseCategory.API, agent="agent_a")
    fc.record_expense(0.02, ExpenseCategory.API, agent="agent_a")
    fc.record_expense(0.05, ExpenseCategory.API, agent="agent_b")
    by_agent = fc.get_spend_by_agent()
    assert len(by_agent) == 2
    assert by_agent[0]["agent"] == "agent_b"  # highest first
    assert by_agent[0]["total"] == 0.05


def test_get_spend_by_category(fc):
    fc.record_expense(1.0, ExpenseCategory.API)
    fc.record_expense(2.0, ExpenseCategory.TOOLS)
    by_cat = fc.get_spend_by_category()
    assert len(by_cat) == 2
    assert by_cat[0]["category"] == "tools"


# ── ROI ──

def test_product_roi_calculation(fc):
    fc.add_product_cost("Template X", "etsy", 0.50)
    fc.record_income(4.99, IncomeSource.ETSY, product_name="Template X")
    products = fc.get_product_roi("Template X")
    assert len(products) == 1
    p = products[0]
    assert p["cost"] == 0.50
    assert p["revenue"] == 4.99
    assert p["profit"] == pytest.approx(4.49)
    assert p["roi_pct"] == pytest.approx(898.0)


def test_product_roi_zero_cost(fc):
    fc.record_income(9.99, IncomeSource.GUMROAD, product_name="Free Product")
    products = fc.get_product_roi("Free Product")
    assert products[0]["roi_pct"] == 0.0


def test_add_product_cost_accumulates(fc):
    fc.add_product_cost("P", "etsy", 1.0)
    fc.add_product_cost("P", "etsy", 0.5)
    products = fc.get_product_roi("P")
    assert products[0]["cost"] == 1.5


# ── P&L ──

def test_pnl_report(fc):
    fc.record_expense(2.0, ExpenseCategory.API)
    fc.record_income(10.0, IncomeSource.ETSY)
    pnl = fc.get_pnl(days=1)
    assert pnl["total_expenses"] == 2.0
    assert pnl["total_income"] == 10.0
    assert pnl["net_profit"] == 8.0
    assert pnl["profitable"] is True


def test_pnl_unprofitable(fc):
    fc.record_expense(5.0, ExpenseCategory.API)
    fc.record_income(1.0, IncomeSource.ETSY)
    pnl = fc.get_pnl(days=1)
    assert pnl["net_profit"] == -4.0
    assert pnl["profitable"] is False


def test_pnl_empty(fc):
    pnl = fc.get_pnl(days=1)
    assert pnl["total_expenses"] == 0
    assert pnl["total_income"] == 0
    assert pnl["net_profit"] == 0


def test_is_spend_anomaly_detects_spike(fc):
    conn = fc._get_db()
    conn.execute("INSERT INTO daily_budgets(date, spent_usd, earned_usd, api_calls, limit_usd) VALUES ('2026-02-20', 2.0, 0, 1, 10)")
    conn.execute("INSERT INTO daily_budgets(date, spent_usd, earned_usd, api_calls, limit_usd) VALUES ('2026-02-21', 2.0, 0, 1, 10)")
    conn.execute("INSERT INTO daily_budgets(date, spent_usd, earned_usd, api_calls, limit_usd) VALUES ('2026-02-22', 2.0, 0, 1, 10)")
    conn.commit()
    fc.record_expense(8.0, ExpenseCategory.API)
    out = fc.is_spend_anomaly(window_days=30, multiplier=2.0)
    assert out["anomaly"] is True
    assert out["today_spent"] == 8.0


def test_daily_guardrail_snapshot_warning_on_negative_pnl(fc):
    fc.record_expense(4.0, ExpenseCategory.API)
    fc.record_income(1.0, IncomeSource.ETSY)
    out = fc.daily_guardrail_snapshot(daily_limit_usd=10.0, anomaly_window_days=30, anomaly_multiplier=3.0)
    assert out["status"] == "warning"
    assert out["net_profit_usd"] == -3.0
    assert out["spend_ratio"] == 0.4


def test_daily_guardrail_snapshot_critical_on_limit_overrun(fc):
    fc.record_expense(12.0, ExpenseCategory.API)
    out = fc.daily_guardrail_snapshot(daily_limit_usd=10.0)
    assert out["status"] == "critical"
    assert out["spend_ratio"] == 1.2


# ── Утренний отчёт ──

def test_format_morning_finance(fc):
    fc.record_expense(1.5, ExpenseCategory.API, agent="llm_router")
    fc.record_income(4.99, IncomeSource.ETSY, product_name="Template")
    report = fc.format_morning_finance()
    assert "Расходы:" in report
    assert "Доход сегодня:" in report
    assert "llm_router" in report


def test_format_morning_finance_empty(fc):
    report = fc.format_morning_finance()
    assert "Расходы: $0.00" in report


# ── Kleinunternehmer ──

def test_annual_revenue_eur(fc):
    fc.record_income(100.0, IncomeSource.ETSY)
    result = fc.get_annual_revenue_eur(eur_rate=0.92)
    assert result["total_usd"] == 100.0
    assert result["total_eur"] == pytest.approx(92.0)
    assert result["limit_eur"] == 22000.0
    assert result["remaining_eur"] == pytest.approx(22000.0 - 92.0)


def test_annual_revenue_eur_empty(fc):
    result = fc.get_annual_revenue_eur()
    assert result["total_usd"] == 0.0
    assert result["usage_pct"] == 0.0


# ── PostgreSQL sync ──

@pytest.mark.asyncio
async def test_sync_to_pg_no_pool(fc):
    result = await fc.sync_to_pg()
    assert result == 0


# ── Cleanup ──

def test_close(fc):
    fc._get_db()  # инициализируем соединение
    fc.close()
    assert fc._conn is None


def test_close_idempotent(fc):
    fc.close()
    fc.close()  # не должен падать
