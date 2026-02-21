"""Financial Controller — Agent 10: контроль финансов VITO.

Контролирует ВСЕ денежные потоки:
  - Расходы: API-вызовы, инструменты, платформы (по агентам и категориям)
  - Доходы: Etsy, Gumroad, KDP, другие платформы
  - 3-уровневый лимит: $10/день авто, $20 уведомление, $50 одобрение
  - Месячный лимит карты: $50
  - ROI на продукт/кампанию
  - P&L отчёты для утреннего брифинга
  - Kleinunternehmer: учёт для немецкого налога (до €22,000/год)
"""

import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("financial_controller", agent="financial_controller")


class TransactionType(Enum):
    EXPENSE = "expense"
    INCOME = "income"


class ExpenseCategory(Enum):
    API = "api"           # LLM-вызовы (Anthropic, OpenAI, Perplexity)
    TOOLS = "tools"       # Платные инструменты и сервисы
    PLATFORM = "platform" # Комиссии площадок (Etsy, Gumroad)
    HOSTING = "hosting"   # Сервер, домены
    CARD = "card"         # Покупки через Revolut/Wise


class IncomeSource(Enum):
    ETSY = "etsy"
    GUMROAD = "gumroad"
    KDP = "kdp"
    CREATIVE_MARKET = "creative_market"
    OTHER = "other"


MONTHLY_CARD_LIMIT_USD = 50.0  # Revolut/Wise карта


class FinancialController:
    def __init__(self, sqlite_path: str = ""):
        self._sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._pg_pool = None  # устанавливается через set_pg_pool()
        logger.info("FinancialController инициализирован", extra={"event": "init"})

    def _get_db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._sqlite_path)
            self._conn.row_factory = sqlite3.Row
            self._init_tables()
        return self._conn

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_type TEXT NOT NULL,       -- expense / income
                category TEXT NOT NULL,      -- api, tools, platform, etsy, gumroad...
                agent TEXT DEFAULT '',       -- какой агент потратил/заработал
                amount_usd REAL NOT NULL,
                description TEXT DEFAULT '',
                goal_id TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_budgets (
                date TEXT PRIMARY KEY,
                spent_usd REAL DEFAULT 0,
                earned_usd REAL DEFAULT 0,
                api_calls INTEGER DEFAULT 0,
                limit_usd REAL DEFAULT 10
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                total_cost_usd REAL DEFAULT 0,
                total_revenue_usd REAL DEFAULT 0,
                units_sold INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(created_at);
            CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(tx_type, category);
            CREATE INDEX IF NOT EXISTS idx_tx_agent ON transactions(agent);
        """)
        self._conn.commit()

    def set_pg_pool(self, pool) -> None:
        self._pg_pool = pool

    # ── Запись транзакций ──

    def record_expense(
        self,
        amount_usd: float,
        category: ExpenseCategory,
        agent: str = "",
        description: str = "",
        goal_id: str = "",
        metadata: dict | None = None,
    ) -> int:
        """Записывает расход. Возвращает ID транзакции."""
        conn = self._get_db()
        cursor = conn.execute(
            """INSERT INTO transactions (tx_type, category, agent, amount_usd, description, goal_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                TransactionType.EXPENSE.value,
                category.value,
                agent,
                amount_usd,
                description,
                goal_id,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        tx_id = cursor.lastrowid

        self._update_daily_budget(amount_usd, is_expense=True)

        logger.info(
            f"Расход: ${amount_usd:.4f} [{category.value}] {agent}",
            extra={
                "event": "expense_recorded",
                "context": {
                    "tx_id": tx_id,
                    "amount": amount_usd,
                    "category": category.value,
                    "agent": agent,
                },
            },
        )
        return tx_id

    def record_income(
        self,
        amount_usd: float,
        source: IncomeSource,
        description: str = "",
        product_name: str = "",
        metadata: dict | None = None,
    ) -> int:
        """Записывает доход."""
        conn = self._get_db()
        cursor = conn.execute(
            """INSERT INTO transactions (tx_type, category, agent, amount_usd, description, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                TransactionType.INCOME.value,
                source.value,
                "income",
                amount_usd,
                description,
                json.dumps(metadata or {"product": product_name}),
            ),
        )
        conn.commit()
        tx_id = cursor.lastrowid

        self._update_daily_budget(amount_usd, is_expense=False)

        if product_name:
            self._update_product_revenue(product_name, source.value, amount_usd)

        logger.info(
            f"Доход: ${amount_usd:.2f} [{source.value}] {product_name}",
            extra={
                "event": "income_recorded",
                "context": {
                    "tx_id": tx_id,
                    "amount": amount_usd,
                    "source": source.value,
                    "product": product_name,
                },
            },
        )
        return tx_id

    def _update_daily_budget(self, amount_usd: float, is_expense: bool) -> None:
        conn = self._get_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO daily_budgets (date, spent_usd, earned_usd, api_calls, limit_usd)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                 spent_usd = spent_usd + ?,
                 earned_usd = earned_usd + ?,
                 api_calls = api_calls + ?""",
            (
                today,
                amount_usd if is_expense else 0,
                amount_usd if not is_expense else 0,
                1 if is_expense else 0,
                settings.DAILY_LIMIT_USD,
                amount_usd if is_expense else 0,
                amount_usd if not is_expense else 0,
                1 if is_expense else 0,
            ),
        )
        conn.commit()

    def _update_product_revenue(self, name: str, platform: str, revenue: float) -> None:
        conn = self._get_db()
        conn.execute(
            """INSERT INTO products (name, platform, total_revenue_usd, units_sold)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(name) DO UPDATE SET
                 total_revenue_usd = total_revenue_usd + ?,
                 units_sold = units_sold + 1""",
            (name, platform, revenue, revenue),
        )
        conn.commit()

    # ── Проверка лимитов (3 уровня) ──

    def check_expense(self, amount_usd: float) -> dict[str, Any]:
        """Проверяет, можно ли потратить amount_usd.

        Возвращает:
          allowed: True/False
          action: 'auto' / 'notify' / 'approve' / 'blocked'
          reason: текстовое объяснение
        """
        daily_spent = self.get_daily_spent()
        new_total = daily_spent + amount_usd

        # Дневной лимит
        if new_total > settings.DAILY_LIMIT_USD:
            logger.warning(
                f"Расход ${amount_usd:.2f} превысит дневной лимит "
                f"(${daily_spent:.2f} + ${amount_usd:.2f} > ${settings.DAILY_LIMIT_USD:.2f})",
                extra={"event": "budget_exceeded"},
            )
            return {
                "allowed": False,
                "action": "blocked",
                "reason": f"Дневной лимит ${settings.DAILY_LIMIT_USD:.2f} будет превышен",
                "daily_spent": daily_spent,
                "remaining": max(settings.DAILY_LIMIT_USD - daily_spent, 0),
            }

        # $50+ → требуется одобрение владельца
        if amount_usd >= settings.OPERATION_APPROVE_USD:
            return {
                "allowed": False,
                "action": "approve",
                "reason": f"Операция ${amount_usd:.2f} требует одобрения владельца (>= ${settings.OPERATION_APPROVE_USD:.2f})",
                "daily_spent": daily_spent,
                "remaining": settings.DAILY_LIMIT_USD - daily_spent,
            }

        # $20+ → уведомить владельца
        if amount_usd >= settings.OPERATION_NOTIFY_USD:
            return {
                "allowed": True,
                "action": "notify",
                "reason": f"Операция ${amount_usd:.2f} — владелец будет уведомлён",
                "daily_spent": daily_spent,
                "remaining": settings.DAILY_LIMIT_USD - new_total,
            }

        # <$20 → автоматически
        return {
            "allowed": True,
            "action": "auto",
            "reason": f"Операция ${amount_usd:.2f} — в пределах автолимита",
            "daily_spent": daily_spent,
            "remaining": settings.DAILY_LIMIT_USD - new_total,
        }

    def check_monthly_card(self, amount_usd: float) -> dict[str, Any]:
        """Проверяет месячный лимит карты Revolut/Wise ($50)."""
        monthly_card = self.get_monthly_card_spent()
        new_total = monthly_card + amount_usd

        if new_total > MONTHLY_CARD_LIMIT_USD:
            return {
                "allowed": False,
                "reason": f"Месячный лимит карты ${MONTHLY_CARD_LIMIT_USD:.2f} будет превышен",
                "monthly_spent": monthly_card,
                "remaining": max(MONTHLY_CARD_LIMIT_USD - monthly_card, 0),
            }

        return {
            "allowed": True,
            "reason": f"Карта: ${monthly_card:.2f} + ${amount_usd:.2f} = ${new_total:.2f} / ${MONTHLY_CARD_LIMIT_USD:.2f}",
            "monthly_spent": monthly_card,
            "remaining": MONTHLY_CARD_LIMIT_USD - new_total,
        }

    # ── Запросы данных ──

    def get_daily_spent(self) -> float:
        conn = self._get_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COALESCE(spent_usd, 0) as spent FROM daily_budgets WHERE date = ?",
            (today,),
        ).fetchone()
        return row["spent"] if row else 0.0

    def get_daily_earned(self) -> float:
        conn = self._get_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COALESCE(earned_usd, 0) as earned FROM daily_budgets WHERE date = ?",
            (today,),
        ).fetchone()
        return row["earned"] if row else 0.0

    def get_monthly_card_spent(self) -> float:
        conn = self._get_db()
        month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        row = conn.execute(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM transactions
               WHERE tx_type = 'expense' AND category = 'card'
               AND created_at >= ?""",
            (month_start,),
        ).fetchone()
        return row["total"] if row else 0.0

    def get_spend_by_agent(self, days: int = 1) -> list[dict]:
        conn = self._get_db()
        rows = conn.execute(
            """SELECT agent, SUM(amount_usd) as total, COUNT(*) as calls
               FROM transactions
               WHERE tx_type = 'expense'
               AND created_at >= datetime('now', ?)
               GROUP BY agent ORDER BY total DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_spend_by_category(self, days: int = 1) -> list[dict]:
        conn = self._get_db()
        rows = conn.execute(
            """SELECT category, SUM(amount_usd) as total, COUNT(*) as calls
               FROM transactions
               WHERE tx_type = 'expense'
               AND created_at >= datetime('now', ?)
               GROUP BY category ORDER BY total DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── ROI на продукт ──

    def get_product_roi(self, product_name: str = "") -> list[dict]:
        """ROI = (revenue - cost) / cost * 100%."""
        conn = self._get_db()
        if product_name:
            rows = conn.execute(
                "SELECT * FROM products WHERE name = ?", (product_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY total_revenue_usd DESC"
            ).fetchall()

        result = []
        for r in rows:
            cost = r["total_cost_usd"]
            revenue = r["total_revenue_usd"]
            roi = ((revenue - cost) / cost * 100) if cost > 0 else 0.0
            result.append({
                "name": r["name"],
                "platform": r["platform"],
                "cost": cost,
                "revenue": revenue,
                "profit": revenue - cost,
                "roi_pct": roi,
                "units_sold": r["units_sold"],
            })
        return result

    def add_product_cost(self, product_name: str, platform: str, cost_usd: float) -> None:
        """Добавляет затрату на продукт (для ROI)."""
        conn = self._get_db()
        conn.execute(
            """INSERT INTO products (name, platform, total_cost_usd)
               VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 total_cost_usd = total_cost_usd + ?""",
            (product_name, platform, cost_usd, cost_usd),
        )
        conn.commit()

    # ── P&L отчёт ──

    def get_pnl(self, days: int = 1) -> dict[str, Any]:
        """Profit & Loss за указанный период."""
        conn = self._get_db()
        period = f"-{days} days"

        expense_row = conn.execute(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM transactions
               WHERE tx_type = 'expense' AND created_at >= datetime('now', ?)""",
            (period,),
        ).fetchone()

        income_row = conn.execute(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM transactions
               WHERE tx_type = 'income' AND created_at >= datetime('now', ?)""",
            (period,),
        ).fetchone()

        expenses = expense_row["total"]
        income = income_row["total"]
        profit = income - expenses

        return {
            "period_days": days,
            "total_expenses": expenses,
            "total_income": income,
            "net_profit": profit,
            "profitable": profit > 0,
            "expense_breakdown": self.get_spend_by_category(days),
        }

    def format_morning_finance(self) -> str:
        """Формирует финансовую часть утреннего отчёта."""
        daily_spent = self.get_daily_spent()
        daily_earned = self.get_daily_earned()
        limit = settings.DAILY_LIMIT_USD
        remaining = max(limit - daily_spent, 0)

        by_agent = self.get_spend_by_agent(days=1)
        agent_lines = [f"  {a['agent']}: ${a['total']:.3f} ({a['calls']} вызовов)" for a in by_agent[:5]]

        pnl_30 = self.get_pnl(days=30)
        products = self.get_product_roi()
        product_lines = [
            f"  {p['name']}: ${p['revenue']:.2f} доход, ROI {p['roi_pct']:.0f}%"
            for p in products[:5]
        ]

        parts = [
            f"Расходы: ${daily_spent:.2f} / ${limit:.2f} (осталось ${remaining:.2f})",
            f"Доход сегодня: ${daily_earned:.2f}",
        ]
        if agent_lines:
            parts.append("По агентам:\n" + "\n".join(agent_lines))
        parts.append(
            f"За 30 дней: расход ${pnl_30['total_expenses']:.2f}, "
            f"доход ${pnl_30['total_income']:.2f}, "
            f"{'прибыль' if pnl_30['profitable'] else 'убыток'} ${abs(pnl_30['net_profit']):.2f}"
        )
        if product_lines:
            parts.append("Продукты:\n" + "\n".join(product_lines))

        return "\n".join(parts)

    # ── Kleinunternehmer учёт (Германия, до €22,000/год) ──

    def get_annual_revenue_eur(self, eur_rate: float = 0.92) -> dict[str, Any]:
        """Годовой доход для Kleinunternehmer (упрощённая конвертация USD→EUR)."""
        conn = self._get_db()
        year_start = datetime.now(timezone.utc).strftime("%Y-01-01")
        row = conn.execute(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM transactions
               WHERE tx_type = 'income' AND created_at >= ?""",
            (year_start,),
        ).fetchone()

        total_usd = row["total"]
        total_eur = total_usd * eur_rate
        limit_eur = 22000.0

        return {
            "total_usd": total_usd,
            "total_eur": total_eur,
            "limit_eur": limit_eur,
            "remaining_eur": limit_eur - total_eur,
            "usage_pct": (total_eur / limit_eur * 100) if limit_eur > 0 else 0,
        }

    # ── Долгосрочное хранение в PostgreSQL ──

    async def sync_to_pg(self) -> int:
        """Синхронизирует транзакции в PostgreSQL для долгосрочного хранения."""
        if not self._pg_pool:
            return 0

        conn_sqlite = self._get_db()
        rows = conn_sqlite.execute(
            """SELECT * FROM transactions
               WHERE id NOT IN (SELECT tx_id FROM pg_synced)
               ORDER BY id LIMIT 100"""
        ).fetchall()

        if not rows:
            return 0

        # Создаём таблицу синхронизации если нет
        conn_sqlite.execute(
            "CREATE TABLE IF NOT EXISTS pg_synced (tx_id INTEGER PRIMARY KEY)"
        )

        synced = 0
        async with self._pg_pool.acquire() as pg_conn:
            for r in rows:
                try:
                    await pg_conn.execute(
                        """INSERT INTO data_lake (action_type, agent, input_data, output_data, result, cost_usd)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        f"financial_{r['tx_type']}",
                        r["agent"],
                        json.dumps({"category": r["category"], "description": r["description"]}),
                        json.dumps({"goal_id": r["goal_id"]}),
                        r["tx_type"],
                        r["amount_usd"],
                    )
                    conn_sqlite.execute("INSERT INTO pg_synced (tx_id) VALUES (?)", (r["id"],))
                    synced += 1
                except Exception as e:
                    logger.warning(
                        f"Ошибка синхронизации tx #{r['id']}: {e}",
                        extra={"event": "pg_sync_failed"},
                    )

        conn_sqlite.commit()
        if synced:
            logger.info(
                f"Синхронизировано в PostgreSQL: {synced} транзакций",
                extra={"event": "pg_synced", "context": {"count": synced}},
            )
        return synced

    # ── Аналитика для агентов ──

    def get_daily_spend(self) -> float:
        """Alias для get_daily_spent() — совместимость с агентами."""
        return self.get_daily_spent()

    def get_daily_revenue(self) -> float:
        """Alias для get_daily_earned() — совместимость с агентами."""
        return self.get_daily_earned()

    def get_agent_roi(self, agent_name: str) -> dict[str, Any]:
        """ROI конкретного агента: (доход от его задач - расходы) / расходы."""
        conn = self._get_db()
        expense_row = conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) as total FROM transactions WHERE tx_type = 'expense' AND agent = ?",
            (agent_name,),
        ).fetchone()
        expenses = expense_row["total"] if expense_row else 0.0
        return {
            "agent": agent_name,
            "total_expenses": expenses,
            "roi_pct": 0.0,
        }

    def get_revenue_trend(self, days: int = 7) -> list[dict]:
        """Дневной тренд выручки за N дней."""
        conn = self._get_db()
        rows = conn.execute(
            """SELECT date, earned_usd, spent_usd
               FROM daily_budgets
               WHERE date >= date('now', ?)
               ORDER BY date""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_product_analytics(self) -> list[dict]:
        """Аналитика по всем продуктам."""
        return self.get_product_roi()

    # ── Очистка ──

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
