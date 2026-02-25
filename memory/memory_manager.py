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
        self._chroma_doc_count = 0
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._pg_pool: Optional[asyncpg.Pool] = None
        logger.info("MemoryManager инициализирован", extra={"event": "init"})

    # ── ChromaDB (семантический поиск) ──

    def _get_chroma(self):
        if self._chroma_client is None:
            import os
            os.makedirs(settings.CHROMA_PATH, exist_ok=True)
            try:
                self._chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
            except Exception:
                # Fallback to in-memory client (useful for tests / restricted FS)
                self._chroma_client = chromadb.Client()
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name="vito_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            try:
                self._chroma_doc_count = int(self._chroma_collection.count())
            except Exception:
                self._chroma_doc_count = 0
            logger.info(
                f"ChromaDB подключён: {settings.CHROMA_PATH}",
                extra={"event": "chroma_connected"},
            )
        return self._chroma_collection

    def store_knowledge(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Сохраняет знание в ChromaDB для семантического поиска."""
        collection = self._get_chroma()
        meta = self._sanitize_metadata(metadata or {})
        meta["stored_at"] = datetime.now(timezone.utc).isoformat()
        try:
            collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
            self._chroma_doc_count += 1
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

    @staticmethod
    def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
        """Ensure ChromaDB metadata contains only supported scalar/list values."""
        safe: dict[str, Any] = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                safe[k] = v
            elif isinstance(v, (list, tuple)):
                # Allow list of scalars; otherwise JSON-stringify
                if all(isinstance(i, (str, int, float, bool)) or i is None for i in v):
                    safe[k] = list(v)
                else:
                    try:
                        safe[k] = json.dumps(v, ensure_ascii=False)[:1000]
                    except Exception:
                        safe[k] = str(v)[:1000]
            else:
                try:
                    safe[k] = json.dumps(v, ensure_ascii=False)[:1000]
                except Exception:
                    safe[k] = str(v)[:1000]
        return safe

    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict]:
        """Семантический поиск по базе знаний."""
        if self._chroma_doc_count == 0:
            return []
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

    def sync_skill_registry(self, limit: int = 500) -> int:
        """Backfill SkillRegistry from existing skills table."""
        conn = self._get_sqlite()
        try:
            rows = conn.execute(
                "SELECT name, description, agent, task_type FROM skills ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
            if not rows:
                return 0
            try:
                from modules.skill_registry import SkillRegistry
                reg = SkillRegistry()
                for r in rows:
                    reg.register_skill(
                        name=r["name"],
                        category=r["task_type"] or "",
                        source=r["agent"] or "memory",
                        status="learned",
                        security_status="unknown",
                        notes=(r["description"] or "")[:300],
                    )
            except Exception:
                return 0
            return len(rows)
        except Exception:
            return 0

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
                created_at TEXT DEFAULT (datetime('now')),
                agent TEXT DEFAULT '',
                task_type TEXT DEFAULT '',
                method_json TEXT DEFAULT '{}',
                version INTEGER DEFAULT 1,
                last_result TEXT DEFAULT ''
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
        # Миграция: добавить колонки если их нет (для существующих БД)
        try:
            conn.execute("SELECT agent FROM skills LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE skills ADD COLUMN agent TEXT DEFAULT ''")
            conn.execute("ALTER TABLE skills ADD COLUMN task_type TEXT DEFAULT ''")
            conn.execute("ALTER TABLE skills ADD COLUMN method_json TEXT DEFAULT '{}'")
            conn.execute("ALTER TABLE skills ADD COLUMN version INTEGER DEFAULT 1")
            conn.execute("ALTER TABLE skills ADD COLUMN last_result TEXT DEFAULT ''")
            conn.commit()
            logger.info("Миграция skills: добавлены agent, task_type, method_json", extra={"event": "skills_migration"})
        # Ensure new columns exist even if older migrations already ran
        try:
            conn.execute("SELECT version FROM skills LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE skills ADD COLUMN version INTEGER DEFAULT 1")
            conn.commit()
        try:
            conn.execute("SELECT last_result FROM skills LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE skills ADD COLUMN last_result TEXT DEFAULT ''")
            conn.commit()

    def save_skill(self, name: str, description: str, agent: str = "",
                   task_type: str = "", method: dict | None = None) -> None:
        conn = self._get_sqlite()
        method_json = json.dumps(method, ensure_ascii=False) if method else "{}"
        try:
            # Check existing to decide version bump
            existing = conn.execute("SELECT description, method_json, version FROM skills WHERE name = ?", (name,)).fetchone()
            bump_version = False
            if existing:
                if existing["description"] != description or existing["method_json"] != method_json:
                    bump_version = True
            conn.execute(
                """INSERT INTO skills (name, description, last_used, agent, task_type, method_json)
                   VALUES (?, ?, datetime('now'), ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     description = excluded.description,
                     success_count = success_count + 1,
                     last_used = datetime('now'),
                     agent = CASE WHEN excluded.agent != '' THEN excluded.agent ELSE skills.agent END,
                     task_type = CASE WHEN excluded.task_type != '' THEN excluded.task_type ELSE skills.task_type END,
                     method_json = CASE WHEN excluded.method_json != '{}' THEN excluded.method_json ELSE skills.method_json END,
                     version = CASE WHEN ? THEN skills.version + 1 ELSE skills.version END""",
                (name, description, agent, task_type, method_json, 1 if bump_version else 0),
            )
            conn.commit()
            # Дублируем в ChromaDB для семантического поиска
            try:
                collection = self._get_chroma()
                collection.upsert(
                    ids=[f"skill_{name}"],
                    documents=[f"Навык: {name}. {description}"],
                    metadatas=[{"type": "skill", "skill_name": name,
                                "agent": agent,
                                "stored_at": datetime.now(timezone.utc).isoformat()}],
                )
            except Exception as e:
                logger.debug(f"Не удалось сохранить навык в ChromaDB: {e}")
            logger.info(f"Навык сохранён: {name}", extra={"event": "skill_saved", "context": {"agent": agent, "task_type": task_type}})
        except Exception as e:
            logger.error(f"Ошибка сохранения навыка: {e}", extra={"event": "skill_save_failed"}, exc_info=True)
            raise
        # Register in SkillRegistry for global visibility
        try:
            from modules.skill_registry import SkillRegistry
            reg = SkillRegistry(sqlite_path=settings.SQLITE_PATH)
            method_dict = method if isinstance(method, dict) else {}
            tests_passed = bool(method_dict.get("tests_passed", False))
            acceptance_status = "accepted"
            if not tests_passed and (task_type in {"self_improve", "shell", "codegen", "fix"} or name.startswith("self_improve:")):
                acceptance_status = "pending"
            reg.register_skill(
                name=name,
                category=task_type or "",
                source=agent or "memory",
                status="learned",
                security_status="unknown",
                notes=description[:300],
                acceptance_status=acceptance_status,
            )
            if tests_passed:
                reg.accept_skill(
                    name=name,
                    tests_passed=True,
                    evidence=str(method_dict.get("test_report", "") or method_dict.get("evidence", ""))[:500],
                    validator="memory.save_skill",
                    notes="auto-accepted by tests_passed",
                )
        except Exception:
            pass

    def update_skill_last_result(self, name: str, result: str) -> None:
        conn = self._get_sqlite()
        try:
            conn.execute(
                "UPDATE skills SET last_result = ?, last_used = datetime('now') WHERE name = ?",
                (result[:500], name),
            )
            conn.commit()
        except Exception:
            pass

    def get_skill(self, name: str) -> Optional[dict]:
        conn = self._get_sqlite()
        row = conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def search_skills(self, query: str, limit: int = 5) -> list[dict]:
        """Семантический поиск навыков: ChromaDB → обогащение из SQLite."""
        results = []
        seen_names = set()

        # 1. Семантический поиск через ChromaDB
        try:
            collection = self._get_chroma()
            chroma_results = collection.query(
                query_texts=[query],
                n_results=limit,
                where={"type": "skill"},
            )
            if chroma_results and chroma_results["ids"] and chroma_results["ids"][0]:
                conn = self._get_sqlite()
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    meta = chroma_results["metadatas"][0][i] if chroma_results["metadatas"] else {}
                    skill_name = meta.get("skill_name", doc_id.replace("skill_", "", 1))
                    if skill_name in seen_names:
                        continue
                    seen_names.add(skill_name)
                    # Обогащаем данными из SQLite (success_count, fail_count)
                    row = conn.execute(
                        "SELECT * FROM skills WHERE name = ?", (skill_name,)
                    ).fetchone()
                    if row:
                        results.append(dict(row))
                    else:
                        results.append({
                            "name": skill_name,
                            "description": chroma_results["documents"][0][i],
                            "success_count": 0, "fail_count": 0,
                        })
        except Exception as e:
            logger.debug(f"Семантический поиск навыков не удался: {e}")

        # 2. Fallback: LIKE-поиск в SQLite (если ChromaDB не нашёл достаточно)
        if len(results) < limit:
            try:
                conn = self._get_sqlite()
                rows = conn.execute(
                    """SELECT * FROM skills
                       WHERE name LIKE ? OR description LIKE ?
                       ORDER BY success_count DESC, last_used DESC
                       LIMIT ?""",
                    (f"%{query[:50]}%", f"%{query[:50]}%", limit),
                ).fetchall()
                for r in rows:
                    row_dict = dict(r)
                    if row_dict["name"] not in seen_names:
                        seen_names.add(row_dict["name"])
                        results.append(row_dict)
            except Exception:
                pass

        return results[:limit]

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
