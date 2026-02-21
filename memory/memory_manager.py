"""Memory Manager — три слоя памяти VITO.

ChromaDB  — семантический поиск по нишам и рынкам (векторный)
SQLite   — быстрые локальные операции: навыки, ошибки, паттерны
pgvector — долгосрочная эпизодическая память + Data Lake

Формула релевантности:
  score = 0.60 × semantic_similarity + 0.25 × recency_factor + 0.15 × importance_score
  recency_factor: exp(-age_days / 30)
"""

import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
import chromadb

from config.logger import get_logger
from config.settings import settings

logger = get_logger("memory_manager", agent="memory_manager")


class MemoryManager:
    def __init__(self):
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._chroma_collection = None
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._pg_pool: Optional[asyncpg.Pool] = None
        logger.info("MemoryManager инициализирован", extra={"event": "init"})

    # ── ChromaDB (семантический поиск) ──

    def _get_chroma(self):
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name="vito_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ChromaDB подключён: {settings.CHROMA_PATH}",
                extra={"event": "chroma_connected"},
            )
        return self._chroma_collection

    def store_knowledge(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Сохраняет знание в ChromaDB для семантического поиска."""
        collection = self._get_chroma()
        meta = metadata or {}
        meta["stored_at"] = datetime.now(timezone.utc).isoformat()
        try:
            collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
            logger.info(
                f"Знание сохранено: {doc_id}",
                extra={"event": "knowledge_stored", "context": {"doc_id": doc_id}},
            )
        except Exception as e:
            logger.error(
                f"Ошибка сохранения знания: {e}",
                extra={"event": "knowledge_store_failed"},
                exc_info=True,
            )
            raise

    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict]:
        """Семантический поиск по базе знаний."""
        collection = self._get_chroma()
        start = time.monotonic()
        try:
            results = collection.query(query_texts=[query], n_results=n_results)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                f"Поиск знаний: '{query[:50]}...' → {len(results['ids'][0])} результатов",
                extra={
                    "event": "knowledge_search",
                    "duration_ms": duration_ms,
                    "context": {"query": query[:100], "results_count": len(results["ids"][0])},
                },
            )
            docs = []
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })
            return docs
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}", extra={"event": "knowledge_search_failed"}, exc_info=True)
            return []

    # ── SQLite (быстрые локальные операции) ──

    def _get_sqlite(self) -> sqlite3.Connection:
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(settings.SQLITE_PATH)
            self._sqlite_conn.row_factory = sqlite3.Row
            self._init_sqlite_tables()
            logger.info(
                f"SQLite подключён: {settings.SQLITE_PATH}",
                extra={"event": "sqlite_connected"},
            )
        return self._sqlite_conn

    def _init_sqlite_tables(self) -> None:
        conn = self._sqlite_conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                error_type TEXT,
                message TEXT,
                resolution TEXT,
                resolved INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                pattern_value TEXT,
                confidence REAL DEFAULT 0.5,
                times_applied INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(category, pattern_key)
            );
        """)
        conn.commit()

    def save_skill(self, name: str, description: str) -> None:
        conn = self._get_sqlite()
        try:
            conn.execute(
                """INSERT INTO skills (name, description, last_used)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(name) DO UPDATE SET
                     description = excluded.description,
                     success_count = success_count + 1,
                     last_used = datetime('now')""",
                (name, description),
            )
            conn.commit()
            logger.info(f"Навык сохранён: {name}", extra={"event": "skill_saved"})
        except Exception as e:
            logger.error(f"Ошибка сохранения навыка: {e}", extra={"event": "skill_save_failed"}, exc_info=True)
            raise

    def get_skill(self, name: str) -> Optional[dict]:
        conn = self._get_sqlite()
        row = conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def search_skills(self, query: str, limit: int = 5) -> list[dict]:
        """Поиск навыков по ключевым словам."""
        conn = self._get_sqlite()
        rows = conn.execute(
            """SELECT * FROM skills
               WHERE name LIKE ? OR description LIKE ?
               ORDER BY success_count DESC, last_used DESC
               LIMIT ?""",
            (f"%{query[:50]}%", f"%{query[:50]}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_skill_success(self, name: str, success: bool) -> None:
        """Обновляет счётчик успешности навыка."""
        conn = self._get_sqlite()
        field = "success_count" if success else "fail_count"
        conn.execute(
            f"UPDATE skills SET {field} = {field} + 1, last_used = datetime('now') WHERE name = ?",
            (name,),
        )
        conn.commit()

    def get_top_skills(self, limit: int = 10) -> list[dict]:
        """Возвращает топ навыков по успешности."""
        conn = self._get_sqlite()
        rows = conn.execute(
            """SELECT *, CAST(success_count AS REAL) / MAX(success_count + fail_count, 1) as success_rate
               FROM skills
               ORDER BY success_rate DESC, success_count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_error(self, module: str, error_type: str, message: str, resolution: str = "") -> int:
        conn = self._get_sqlite()
        cursor = conn.execute(
            "INSERT INTO errors (module, error_type, message, resolution, resolved) VALUES (?, ?, ?, ?, ?)",
            (module, error_type, message, resolution, 1 if resolution else 0),
        )
        conn.commit()
        return cursor.lastrowid

    def save_pattern(self, category: str, key: str, value: str, confidence: float = 0.5) -> None:
        conn = self._get_sqlite()
        conn.execute(
            """INSERT INTO patterns (category, pattern_key, pattern_value, confidence)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(category, pattern_key) DO UPDATE SET
                 pattern_value = excluded.pattern_value,
                 confidence = excluded.confidence,
                 times_applied = times_applied + 1""",
            (category, key, value, confidence),
        )
        conn.commit()
        logger.info(f"Паттерн сохранён: {category}/{key}", extra={"event": "pattern_saved"})

    # ── pgvector / PostgreSQL (долгосрочная эпизодическая память + Data Lake) ──

    async def _get_pg(self) -> asyncpg.Pool:
        if self._pg_pool is None:
            try:
                self._pg_pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
                await self._init_pg_tables()
                logger.info("PostgreSQL pool создан", extra={"event": "pg_connected"})
            except Exception as e:
                logger.error(f"Ошибка подключения к PostgreSQL: {e}", extra={"event": "pg_connect_failed"}, exc_info=True)
                raise
        return self._pg_pool

    async def _init_pg_tables(self) -> None:
        pool = self._pg_pool
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;

                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id SERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details JSONB DEFAULT '{}',
                    importance REAL DEFAULT 0.5,
                    embedding vector(1536),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS data_lake (
                    id SERIAL PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    input_data JSONB DEFAULT '{}',
                    output_data JSONB DEFAULT '{}',
                    result TEXT,
                    duration_ms INTEGER,
                    cost_usd REAL DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic_memory (created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_datalake_agent ON data_lake (agent, created_at DESC);
            """)

    async def store_episode(
        self, event_type: str, summary: str, details: dict | None = None, importance: float = 0.5
    ) -> int:
        """Сохраняет эпизод в долгосрочную память."""
        pool = await self._get_pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO episodic_memory (event_type, summary, details, importance)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                event_type, summary, json.dumps(details or {}), importance,
            )
            logger.info(
                f"Эпизод сохранён: {event_type}",
                extra={"event": "episode_stored", "context": {"episode_id": row["id"]}},
            )
            return row["id"]

    async def store_to_datalake(
        self,
        action_type: str,
        agent: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        result: str = "",
        duration_ms: int = 0,
        cost_usd: float = 0.0,
    ) -> int:
        """Записывает действие в Data Lake (сырьё для обучения LLM)."""
        pool = await self._get_pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO data_lake (action_type, agent, input_data, output_data, result, duration_ms, cost_usd)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                action_type, agent,
                json.dumps(input_data or {}), json.dumps(output_data or {}),
                result, duration_ms, cost_usd,
            )
            return row["id"]

    async def search_episodes(self, query: str, limit: int = 10) -> list[dict]:
        """Поиск в эпизодической памяти по тексту (полнотекстовый, без embedding пока)."""
        pool = await self._get_pg()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, event_type, summary, details, importance, created_at
                   FROM episodic_memory
                   WHERE summary ILIKE $1
                   ORDER BY created_at DESC
                   LIMIT $2""",
                f"%{query}%", limit,
            )
            return [dict(r) for r in rows]

    # ── Формула релевантности ──

    @staticmethod
    def calculate_relevance(
        semantic_similarity: float, created_at: datetime, importance: float = 0.5
    ) -> float:
        """score = 0.60 × similarity + 0.25 × recency + 0.15 × importance"""
        age_days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
        recency = math.exp(-age_days / 30)  # период полураспада 30 дней
        return 0.60 * semantic_similarity + 0.25 * recency + 0.15 * importance

    # ── Очистка ──

    async def close(self) -> None:
        if self._pg_pool:
            await self._pg_pool.close()
            logger.info("PostgreSQL pool закрыт", extra={"event": "pg_closed"})
        if self._sqlite_conn:
            self._sqlite_conn.close()
            logger.info("SQLite закрыт", extra={"event": "sqlite_closed"})
