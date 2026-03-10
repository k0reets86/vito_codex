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
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
import chromadb

from config.logger import get_logger
from config.settings import settings
from modules.agent_contracts import get_agent_contract
from modules.execution_facts import ExecutionFacts
from modules.failure_memory import FailureMemory
from modules.failure_substrate import build_failure_substrate
from modules.mem0_bridge import Mem0Bridge
from modules.memory_blocks import MemoryBlocks
from modules.knowledge_consolidator import KnowledgeConsolidator
from modules.memory_policy import decide_save, retention_classes
from modules.knowledge_graph import KnowledgeGraph
from modules.platform_knowledge import search_entries as search_platform_knowledge
from modules.playbook_registry import PlaybookRegistry
from modules.platform_runbook_packs import build_runbook_packs_for_services
from modules.prompt_guard import has_prompt_injection_signals, sanitize_untrusted_text

logger = get_logger("memory_manager", agent="memory_manager")

from config.paths import PROJECT_ROOT

_PROTECTED_TARGETS_PATH = PROJECT_ROOT / "runtime" / "protected_platform_targets.json"


class MemoryManager:
    def __init__(self):
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._chroma_collection = None
        self._chroma_doc_count = 0
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._pg_pool: Optional[asyncpg.Pool] = None
        self._memory_blocks = MemoryBlocks()
        self._knowledge_graph = KnowledgeGraph()
        self._mem0 = Mem0Bridge()
        self._gemini_embed_client = None
        self._gemini_embed_lock = threading.Lock()
        self._embed_query_fallback_only = False
        logger.info("MemoryManager инициализирован", extra={"event": "init"})

    @property
    def memory_blocks(self) -> MemoryBlocks:
        return self._memory_blocks

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

    def _get_gemini_embed_client(self):
        if not bool(getattr(settings, "GEMINI_EMBEDDINGS_ENABLED", True)):
            return None
        api_key = str(getattr(settings, "GEMINI_API_KEY", "") or getattr(settings, "GOOGLE_API_KEY", "")).strip()
        if not api_key:
            return None
        if self._gemini_embed_client is not None:
            return self._gemini_embed_client
        with self._gemini_embed_lock:
            if self._gemini_embed_client is not None:
                return self._gemini_embed_client
            try:
                from google import genai
            except Exception:
                logger.debug("google-genai недоступен для embeddings")
                return None
            try:
                self._gemini_embed_client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.debug(f"Не удалось создать Gemini embed client: {e}")
                self._gemini_embed_client = None
        return self._gemini_embed_client

    def _embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        if self._embed_query_fallback_only:
            return None
        client = self._get_gemini_embed_client()
        if client is None:
            return None
        model = str(getattr(settings, "GEMINI_EMBED_MODEL", "text-embedding-004") or "text-embedding-004")
        try:
            # google-genai generally supports embed_content with list[str] via contents.
            resp = client.models.embed_content(model=model, contents=texts)
            vectors: list[list[float]] = []
            for item in getattr(resp, "embeddings", []) or []:
                vals = list(getattr(item, "values", []) or [])
                if vals:
                    vectors.append([float(x) for x in vals])
            if len(vectors) == len(texts):
                return vectors
        except Exception:
            try:
                vectors = []
                for t in texts:
                    resp = client.models.embed_content(model=model, contents=t)
                    emb = getattr(resp, "embedding", None)
                    vals = list(getattr(emb, "values", []) or [])
                    if not vals:
                        return None
                    vectors.append([float(x) for x in vals])
                return vectors if len(vectors) == len(texts) else None
            except Exception as e:
                logger.debug(f"Gemini embeddings fallback error: {e}")
                return None
        return None

    @staticmethod
    def _is_dimension_mismatch_error(err: Exception) -> bool:
        msg = str(err).lower()
        return ("dimension" in msg and "expecting embedding" in msg) or ("got 3072" in msg and "384" in msg)

    def _upsert_chroma_safe(
        self,
        collection,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        if embeddings:
            try:
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
                return
            except Exception as e:
                if self._is_dimension_mismatch_error(e):
                    self._embed_query_fallback_only = True
                    logger.warning(
                        "Chroma embedding dimension mismatch detected; switching to text-only mode",
                        extra={"event": "chroma_dim_fallback"},
                    )
                else:
                    raise
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def store_knowledge(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        skip_block_tracking: bool = False,
    ) -> bool:
        """Сохраняет знание в ChromaDB для семантического поиска."""
        raw_meta = metadata or {}
        normalized_text = self._prepare_knowledge_text(text, raw_meta)
        decision = decide_save(doc_id=doc_id, text=normalized_text, metadata=raw_meta)
        self._audit_memory_policy(
            doc_id=doc_id,
            text=normalized_text,
            metadata=raw_meta,
            action=decision.action,
            reason=decision.reason,
            importance=decision.importance,
            ttl_days=decision.ttl_days,
            retention_class=decision.retention_class,
        )
        if decision.action != "save":
            logger.info(
                f"Знание отклонено policy: {doc_id} ({decision.reason})",
                extra={"event": "knowledge_forget_policy", "context": {"doc_id": doc_id, "reason": decision.reason}},
            )
            return False
        collection = self._get_chroma()
        meta = self._sanitize_metadata(raw_meta)
        meta["stored_at"] = datetime.now(timezone.utc).isoformat()
        meta["importance_score"] = float(meta.get("importance_score", decision.importance))
        meta["ttl_days"] = int(meta.get("ttl_days", decision.ttl_days))
        meta["retention_class"] = str(meta.get("retention_class", decision.retention_class))
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(days=max(0, int(meta["ttl_days"])))
            meta["expires_at"] = expires_at.isoformat()
        except Exception:
            pass
        meta["policy_reason"] = decision.reason
        try:
            embed = self._embed_texts([normalized_text])
            self._upsert_chroma_safe(
                collection,
                ids=[doc_id],
                documents=[normalized_text],
                metadatas=[meta],
                embeddings=embed,
            )
            self._chroma_doc_count += 1
            logger.info(
                f"Знание сохранено: {doc_id}",
                extra={"event": "knowledge_stored", "context": {"doc_id": doc_id}},
            )
            if not skip_block_tracking:
                block_type = str(raw_meta.get("block_type") or raw_meta.get("type") or "knowledge").lower()
                importance = float(meta.get("importance_score", decision.importance))
                priority = float(meta.get("priority", 1.0))
                stage = self._retention_stage(meta.get("retention_class", ""))
                self._memory_blocks.record_block(
                    doc_id=doc_id,
                    block_type=block_type,
                    summary=normalized_text[:2048],
                    metadata=meta,
                    retention_class=meta.get("retention_class", ""),
                    stage=stage,
                    importance=importance,
                    priority=priority,
                )
            try:
                self._knowledge_graph.record_knowledge(doc_id=doc_id, metadata=meta)
            except Exception:
                pass
            try:
                self._mem0.add(normalized_text, metadata={"doc_id": doc_id, **meta})
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(
                f"Ошибка сохранения знания: {e}",
                extra={"event": "knowledge_store_failed"},
                exc_info=True,
            )
            raise

    @staticmethod
    def _is_untrusted_external_knowledge(meta: dict[str, Any]) -> bool:
        source = str((meta or {}).get("source", "") or "").strip().lower()
        typ = str((meta or {}).get("type", "") or "").strip().lower()
        if bool((meta or {}).get("untrusted_external")):
            return True
        risky_sources = {"web", "rss", "reddit", "browser", "scrape", "search", "external", "url_context"}
        risky_types = {"research", "trend", "competitor", "document_extract", "web_page", "external_content"}
        return source in risky_sources or typ in risky_types

    def _prepare_knowledge_text(self, text: str, meta: dict[str, Any] | None = None) -> str:
        raw = str(text or "")
        metadata = meta or {}
        if not raw:
            return ""
        if self._is_untrusted_external_knowledge(metadata):
            cleaned = sanitize_untrusted_text(raw, max_chars=12000)
            if has_prompt_injection_signals(raw):
                metadata["guardrail_signal"] = "prompt_injection_suspected"
                metadata["guardrail_sanitized"] = True
            return cleaned
        return raw

    def forget_knowledge(self, doc_id: str, reason: str = "manual_forget", metadata: dict[str, Any] | None = None) -> bool:
        """Удаляет знание из ChromaDB и пишет аудит forget-события."""
        meta = metadata or {}
        self._audit_memory_policy(
            doc_id=doc_id,
            text="",
            metadata=meta,
            action="forget",
            reason=reason or "manual_forget",
            importance=float(meta.get("importance_score", 0.0) or 0.0),
            ttl_days=int(meta.get("ttl_days", 0) or 0),
            retention_class=str(meta.get("retention_class", "")),
        )
        try:
            collection = self._get_chroma()
            collection.delete(ids=[doc_id])
            logger.info(
                f"Знание удалено: {doc_id}",
                extra={"event": "knowledge_deleted", "context": {"doc_id": doc_id, "reason": reason}},
            )
            return True
        except Exception as e:
            logger.warning(
                f"Не удалось удалить знание: {e}",
                extra={"event": "knowledge_delete_failed", "context": {"doc_id": doc_id}},
            )
            return False

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
                    cleaned = [i for i in list(v) if i is not None and str(i).strip() != ""]
                    if cleaned:
                        safe[k] = cleaned
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
        if "priority" in safe:
            safe["priority"] = MemoryManager._coerce_priority_value(safe.get("priority"))
        if "importance_score" in safe:
            safe["importance_score"] = MemoryManager._coerce_score_value(safe.get("importance_score"), default=0.5)
        return safe

    @staticmethod
    def _coerce_score_value(value: Any, default: float = 0.5) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _coerce_priority_value(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        norm = str(value or "").strip().lower()
        if not norm:
            return 0.5
        mapped = {
            "critical": 1.0,
            "high": 0.85,
            "medium": 0.6,
            "low": 0.35,
            "background": 0.15,
        }
        if norm in mapped:
            return mapped[norm]
        try:
            return float(norm)
        except Exception:
            return 0.5

    @staticmethod
    def _retention_stage(retention_class: str | None) -> str:
        rc = (retention_class or "").lower()
        if "owner" in rc:
            return "long"
        if "strategic" in rc:
            return "long"
        if "project" in rc or "research" in rc:
            return "mid"
        return "short"

    @staticmethod
    def _safe_parse_metadata(payload: str) -> dict[str, Any]:
        try:
            return json.loads(payload) if payload else {}
        except Exception:
            return {}

    def _record_skill_memory_block(
        self,
        name: str,
        agent: str,
        task_type: str,
        description: str,
        success_rate: float,
    ) -> None:
        summary = (description or "").strip()[:1024]
        doc_id = f"skill_block_{name}"
        stage = "long" if success_rate >= 0.6 else "mid"
        metadata = {
            "skill_name": name,
            "agent": agent,
            "task_type": task_type,
            "success_rate": success_rate,
            "source": "skill_memory",
        }
        self._memory_blocks.record_block(
            doc_id=doc_id,
            block_type="skill",
            summary=summary or f"Навык {name}",
            metadata=metadata,
            retention_class="project_mid",
            stage=stage,
            importance=max(0.3, success_rate),
            priority=max(0.1, success_rate),
        )

    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict]:
        """Семантический поиск по базе знаний."""
        if self._chroma_doc_count == 0:
            return []
        collection = self._get_chroma()
        start = time.monotonic()
        try:
            # Ask more candidates from vector DB, then re-rank with recency+importance.
            raw_limit = max(n_results * 3, n_results + 5)
            embed = self._embed_texts([query])
            if embed:
                try:
                    results = collection.query(query_embeddings=embed, n_results=raw_limit)
                except Exception as e:
                    if self._is_dimension_mismatch_error(e):
                        self._embed_query_fallback_only = True
                        logger.warning(
                            "Chroma query embedding mismatch; fallback to query_texts",
                            extra={"event": "chroma_query_dim_fallback"},
                        )
                        results = collection.query(query_texts=[query], n_results=raw_limit)
                    else:
                        raise
            else:
                results = collection.query(query_texts=[query], n_results=raw_limit)
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
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                similarity = 1.0 - float(distance) if distance is not None else 0.5
                similarity = max(0.0, min(1.0, similarity))
                created_at = self._metadata_timestamp(metadata)
                importance = float(metadata.get("importance_score", 0.5) or 0.5)
                importance = max(0.0, min(1.0, importance))
                relevance = self.calculate_relevance(
                    semantic_similarity=similarity,
                    created_at=created_at,
                    importance=importance,
                )
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": metadata,
                    "distance": distance,
                    "relevance": round(relevance, 6),
                })
            docs.sort(key=lambda x: float(x.get("relevance", 0.0)), reverse=True)
            try:
                mem0_rows = self._mem0.search(query, limit=max(2, n_results))
            except Exception:
                mem0_rows = []
            for idx, row in enumerate(mem0_rows):
                docs.append(
                    {
                        "id": str(row.get("id") or row.get("memory_id") or f"mem0:{idx}"),
                        "text": str(row.get("text") or row.get("memory") or ""),
                        "metadata": {"source": "mem0", **dict(row.get("metadata") or {})},
                        "distance": None,
                        "relevance": round(0.55 - (idx * 0.01), 6),
                    }
                )
            docs.sort(key=lambda x: float(x.get("relevance", 0.0)), reverse=True)
            return docs[:n_results]
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}", extra={"event": "knowledge_search_failed"}, exc_info=True)
            return []

    @staticmethod
    def _metadata_timestamp(metadata: dict[str, Any] | None) -> datetime:
        md = metadata or {}
        for key in ("stored_at", "created_at", "updated_at"):
            value = md.get(key)
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(str(value))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
        return datetime.now(timezone.utc)

    def consolidate_short_term_memory(self, min_age_days: int = 5, limit: int = 25) -> int:
        """Периодически переводит short-тренировочные блоки в long-term."""
        candidates = self._memory_blocks.candidates_for_consolidation(min_age_days=min_age_days, stage="short", limit=limit)
        promoted = self._promote_memory_blocks(candidates, source="scheduled")
        if promoted:
            logger.info(
                f"Консолидация памяти: {promoted} блоков переведено в long-term",
                extra={"event": "memory_consolidation", "promoted": promoted},
            )
        return promoted

    def preview_memory_consolidation(self, doc_ids: list[str]) -> dict[str, Any]:
        items = [str(x).strip() for x in (doc_ids or []) if str(x).strip()]
        blocks = self._memory_blocks.get_blocks(items)
        by_id = {str(b.get("doc_id") or ""): b for b in blocks}
        selected: list[dict[str, Any]] = []
        missing: list[str] = []
        for doc_id in items:
            block = by_id.get(doc_id)
            if not block:
                missing.append(doc_id)
                continue
            metadata = self._safe_parse_metadata(block.get("metadata_json", "{}"))
            retention_class = (
                "strategic_long"
                if block.get("block_type") == "owner_preference"
                else str(metadata.get("retention_class") or "project_mid")
            )
            selected.append(
                {
                    "doc_id": doc_id,
                    "block_type": str(block.get("block_type") or ""),
                    "stage": str(block.get("stage") or ""),
                    "current_retention_class": str(metadata.get("retention_class") or ""),
                    "target_retention_class": retention_class,
                    "summary": str(block.get("summary") or "")[:240],
                    "importance": float(metadata.get("importance_score", block.get("importance", 0.5)) or 0.5),
                }
            )
        return {
            "requested": len(items),
            "selected": len(selected),
            "missing": missing,
            "items": selected,
        }

    def consolidate_memory_on_demand(self, doc_ids: list[str]) -> dict[str, Any]:
        items = [str(x).strip() for x in (doc_ids or []) if str(x).strip()]
        blocks = self._memory_blocks.get_blocks(items)
        by_id = {str(b.get("doc_id") or ""): b for b in blocks}
        selected = [by_id[doc_id] for doc_id in items if doc_id in by_id]
        promoted = self._promote_memory_blocks(selected, source="on_demand")
        return {
            "requested": len(items),
            "found": len(selected),
            "promoted": promoted,
            "missing": [doc_id for doc_id in items if doc_id not in by_id],
        }

    def build_runtime_knowledge_pack(
        self,
        *,
        query: str,
        services: list[str] | None = None,
        task_root_id: str = "",
        limit: int = 5,
        reflector: Any | None = None,
        evolution_archive: Any | None = None,
    ) -> dict[str, Any]:
        consolidator = KnowledgeConsolidator(
            memory_manager=self,
            reflector=reflector,
            evolution_archive=evolution_archive,
        )
        return consolidator.consolidate(
            query=query,
            services=services or [],
            task_root_id=task_root_id,
            limit=limit,
        )

    def _promote_memory_blocks(self, blocks: list[dict[str, Any]], *, source: str) -> int:
        promoted = 0
        for block in blocks:
            doc_id = str(block.get("doc_id") or "").strip()
            if not doc_id:
                continue
            metadata = self._safe_parse_metadata(block.get("metadata_json", "{}"))
            metadata["retention_class"] = (
                "strategic_long"
                if block.get("block_type") == "owner_preference"
                else str(metadata.get("retention_class") or "project_mid")
            )
            metadata["importance_score"] = max(0.6, float(metadata.get("importance_score", block.get("importance", 0.5)) or 0.5))
            metadata["memory_promotion_source"] = source
            text = str(block.get("summary") or "consolidated memory").strip() or "consolidated memory"
            try:
                self.store_knowledge(doc_id=doc_id, text=text, metadata=metadata, skip_block_tracking=True)
                stage = "long" if metadata["retention_class"] in {"owner_long", "strategic_long"} else "mid"
                self._memory_blocks.mark_promoted(doc_id, new_stage=stage)
                promoted += 1
            except Exception as exc:
                logger.warning(
                    f"Не удалось консолидировать память {doc_id}: {exc}",
                    extra={
                        "event": "memory_consolidation_failed",
                        "context": {"doc_id": doc_id, "source": source},
                    },
                )
        return promoted


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
            CREATE TABLE IF NOT EXISTS memory_policy_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT DEFAULT '',
                memory_type TEXT DEFAULT '',
                source TEXT DEFAULT '',
                text_size INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.0,
                ttl_days INTEGER DEFAULT 0,
                retention_class TEXT DEFAULT '',
                expires_at TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_memory_policy_doc ON memory_policy_audit (doc_id, created_at DESC);
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
        try:
            conn.execute("SELECT retention_class FROM memory_policy_audit LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE memory_policy_audit ADD COLUMN retention_class TEXT DEFAULT ''")
            conn.commit()
        try:
            conn.execute("SELECT expires_at FROM memory_policy_audit LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE memory_policy_audit ADD COLUMN expires_at TEXT DEFAULT ''")
            conn.commit()

    def _audit_memory_policy(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
        action: str,
        reason: str,
        importance: float,
        ttl_days: int,
        retention_class: str = "",
    ) -> None:
        try:
            conn = self._get_sqlite()
            expires_at = ""
            if int(ttl_days or 0) > 0 and action == "save":
                try:
                    expires_at = (datetime.now(timezone.utc) + timedelta(days=int(ttl_days or 0))).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    expires_at = ""
            conn.execute(
                """
                INSERT INTO memory_policy_audit
                (doc_id, action, reason, memory_type, source, text_size, importance, ttl_days, retention_class, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id[:200],
                    (action or "")[:30],
                    (reason or "")[:200],
                    str(metadata.get("type", ""))[:80],
                    str(metadata.get("source", ""))[:80],
                    len((text or "").strip()),
                    float(importance or 0.0),
                    int(ttl_days or 0),
                    str(retention_class or metadata.get("retention_class", ""))[:40],
                    expires_at[:40],
                ),
            )
            conn.commit()
        except Exception:
            pass

    def get_memory_policy_audit(self, limit: int = 100, action: str = "") -> list[dict]:
        conn = self._get_sqlite()
        if action:
            rows = conn.execute(
                """SELECT * FROM memory_policy_audit
                   WHERE action = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (action, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM memory_policy_audit
                   ORDER BY id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_memory_policy_summary(self, days: int = 30) -> dict:
        conn = self._get_sqlite()
        window_days = max(1, int(days or 30))
        base_where = "created_at >= datetime('now', ?)"
        param = (f"-{window_days} day",)
        total = int(
            (
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM memory_policy_audit WHERE {base_where}",
                    param,
                ).fetchone()
                or {"n": 0}
            )["n"]
            or 0
        )
        saves = int(
            (
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM memory_policy_audit WHERE {base_where} AND action='save'",
                    param,
                ).fetchone()
                or {"n": 0}
            )["n"]
            or 0
        )
        forgets = int(
            (
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM memory_policy_audit WHERE {base_where} AND action='forget'",
                    param,
                ).fetchone()
                or {"n": 0}
            )["n"]
            or 0
        )
        avg_importance = float(
            (
                conn.execute(
                    f"SELECT AVG(importance) AS v FROM memory_policy_audit WHERE {base_where} AND action='save'",
                    param,
                ).fetchone()
                or {"v": 0.0}
            )["v"]
            or 0.0
        )
        by_retention_rows = conn.execute(
            f"""
            SELECT COALESCE(retention_class, '') AS retention_class, COUNT(*) AS n
            FROM memory_policy_audit
            WHERE {base_where} AND action='save'
            GROUP BY retention_class
            ORDER BY n DESC
            """,
            param,
        ).fetchall()
        by_reason_rows = conn.execute(
            f"""
            SELECT reason, COUNT(*) AS n
            FROM memory_policy_audit
            WHERE {base_where} AND action='forget'
            GROUP BY reason
            ORDER BY n DESC
            LIMIT 8
            """,
            param,
        ).fetchall()
        expiring_soon = int(
            (
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM memory_policy_audit
                    WHERE action='save'
                      AND expires_at != ''
                      AND expires_at <= datetime('now', '+7 day')
                      AND expires_at >= datetime('now')
                    """
                ).fetchone()
                or {"n": 0}
            )["n"]
            or 0
        )
        quality_score = 0.0
        if total > 0:
            save_ratio = saves / total
            quality_score = (0.55 * save_ratio) + (0.35 * min(1.0, avg_importance)) + (0.10 * (1.0 - min(1.0, expiring_soon / max(1, saves))))
        return {
            "window_days": window_days,
            "total_events": total,
            "saved": saves,
            "forgotten": forgets,
            "save_ratio": round((saves / total) if total else 0.0, 4),
            "avg_saved_importance": round(avg_importance, 4),
            "expiring_7d": expiring_soon,
            "quality_score": round(quality_score, 4),
            "retention_classes": retention_classes(),
            "saved_by_retention": [{str(r["retention_class"] or "unknown"): int(r["n"] or 0)} for r in by_retention_rows],
            "top_forget_reasons": [{str(r["reason"] or ""): int(r["n"] or 0)} for r in by_reason_rows],
        }

    def list_expired_memory_docs(self, limit: int = 200) -> list[dict]:
        """Return docs where latest memory audit action is save and TTL is expired."""
        conn = self._get_sqlite()
        rows = conn.execute(
            """
            SELECT m.doc_id, m.memory_type, m.retention_class, m.expires_at, m.importance
            FROM memory_policy_audit m
            JOIN (
                SELECT doc_id, MAX(id) AS max_id
                FROM memory_policy_audit
                GROUP BY doc_id
            ) x ON x.max_id = m.id
            WHERE m.action = 'save'
              AND m.expires_at != ''
              AND m.expires_at <= datetime('now')
            ORDER BY m.id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_expired_memory(self, limit: int = 200, dry_run: bool = True) -> dict:
        expired = self.list_expired_memory_docs(limit=limit)
        if dry_run:
            return {"ok": True, "dry_run": True, "expired_found": len(expired), "deleted": 0, "docs": expired[:30]}
        deleted = 0
        failed = 0
        for row in expired:
            ok = self.forget_knowledge(
                doc_id=str(row.get("doc_id", "")),
                reason="ttl_expired_cleanup",
                metadata={
                    "type": str(row.get("memory_type", "")),
                    "retention_class": str(row.get("retention_class", "")),
                    "source": "memory_retention_cleanup",
                },
            )
            if ok:
                deleted += 1
            else:
                failed += 1
        return {
            "ok": True,
            "dry_run": False,
            "expired_found": len(expired),
            "deleted": deleted,
            "failed": failed,
            "docs": expired[:30],
        }

    def retention_drift_alerts(self, days: int = 30) -> dict:
        summary = self.get_memory_policy_summary(days=days)
        total = int(summary.get("total_events", 0) or 0)
        saved = int(summary.get("saved", 0) or 0)
        forgotten = int(summary.get("forgotten", 0) or 0)
        alerts: list[dict] = []

        counts: dict[str, int] = {}
        for row in summary.get("saved_by_retention", []) or []:
            if not isinstance(row, dict) or not row:
                continue
            k = next(iter(row.keys()))
            counts[str(k)] = int(row[k] or 0)
        if saved >= 20:
            working_short = counts.get("working_short", 0)
            noise_short = counts.get("noise_short", 0)
            if (working_short / max(1, saved)) > 0.75:
                alerts.append({
                    "severity": "medium",
                    "code": "retention_skew_working_short",
                    "message": "Most saved memories are short-lived; consider more strategic captures.",
                })
            if noise_short > 0:
                alerts.append({
                    "severity": "low",
                    "code": "noise_saved_present",
                    "message": "Noise-class memories are being saved; review save policy routing.",
                })
        if total >= 20 and (forgotten / max(1, total)) > 0.7:
            alerts.append({
                "severity": "medium",
                "code": "high_forget_ratio",
                "message": "Forget ratio is high; memory extraction may be producing low-value artifacts.",
            })
        if counts.get("owner_long", 0) == 0:
            alerts.append({
                "severity": "low",
                "code": "owner_profile_gap",
                "message": "No owner-long memory captures in window; confirm preference sync is active.",
            })
        if int(summary.get("expiring_7d", 0) or 0) > 150:
            alerts.append({
                "severity": "high",
                "code": "high_expiring_backlog",
                "message": "Large memory expiry backlog is approaching; run retention cleanup.",
            })
        score = float(summary.get("quality_score", 0.0) or 0.0)
        if score < 0.45:
            alerts.append({
                "severity": "high",
                "code": "quality_score_low",
                "message": "Memory quality score is low; tune extraction quality and retention routing.",
            })
        return {"window_days": int(days or 30), "summary": summary, "alerts": alerts}

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
            stats = conn.execute("SELECT success_count, fail_count FROM skills WHERE name = ?", (name,)).fetchone()
            success_count = int(stats["success_count"] or 0)
            fail_count = int(stats["fail_count"] or 0)
            total_runs = success_count + fail_count
            success_rate = float(success_count) / total_runs if total_runs > 0 else 0.0
            try:
                self._record_skill_memory_block(name, agent, task_type, description, success_rate)
            except Exception:
                pass
            # Дублируем в ChromaDB для семантического поиска
            try:
                collection = self._get_chroma()
                skill_doc = f"Навык: {name}. {description}"
                skill_meta = {
                    "type": "skill",
                    "skill_name": name,
                    "agent": agent,
                    "stored_at": datetime.now(timezone.utc).isoformat(),
                }
                skill_embed = self._embed_texts([skill_doc])
                self._upsert_chroma_safe(
                    collection,
                    ids=[f"skill_{name}"],
                    documents=[skill_doc],
                    metadatas=[skill_meta],
                    embeddings=skill_embed,
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

    def get_agent_memory_context(self, agent_name: str, task_type: str = "", limit: int = 5) -> dict[str, Any]:
        agent = str(agent_name or "").strip().lower()
        task = str(task_type or "").strip().lower()
        contract = get_agent_contract(agent)
        query_parts = [agent]
        if task:
            query_parts.append(task)
        query_parts.extend(list(contract.get("owned_outcomes", [])[:2]))
        query = " ".join([x for x in query_parts if x]).strip() or agent

        skills = []
        try:
            skill_rows = self.search_skills(query, limit=max(limit * 2, 6))
            for row in skill_rows:
                if str(row.get("agent", "")).strip().lower() == agent or f"{agent}:" in str(row.get("name", "")).lower():
                    skills.append(row)
            if len(skills) < limit:
                for row in skill_rows:
                    if row not in skills:
                        skills.append(row)
                    if len(skills) >= limit:
                        break
        except Exception:
            skills = []

        failures = []
        try:
            failures = [
                row for row in FailureMemory().recent(limit=max(limit * 3, 10))
                if str(row.get("agent", "")).strip().lower() == agent and (not task or str(row.get("task_type", "")).strip().lower() == task)
            ][:limit]
        except Exception:
            failures = []

        failure_substrate = {}
        try:
            failure_substrate = build_failure_substrate(
                agent=agent,
                task_type=task,
                limit=max(limit * 2, 8),
                sqlite_path=self._sqlite_path_value(),
            )
        except Exception:
            failure_substrate = {"agent": agent, "task_type": task, "entries": [], "avoid_actions": [], "blocked_patterns": [], "signals": {"entry_count": 0, "has_high_risk": False}}

        facts = []
        try:
            for fact in ExecutionFacts().recent_facts(limit=max(limit * 6, 20)):
                action = str(getattr(fact, "action", "") or "")
                if not action.startswith(f"{agent}:"):
                    continue
                if task and f":{task}" not in action:
                    continue
                facts.append(
                    {
                        "action": action,
                        "status": str(getattr(fact, "status", "") or ""),
                        "detail": str(getattr(fact, "detail", "") or ""),
                        "evidence": str(getattr(fact, "evidence", "") or ""),
                        "created_at": str(getattr(fact, "created_at", "") or ""),
                    }
                )
                if len(facts) >= limit:
                    break
        except Exception:
            facts = []
        facts = self._rerank_runtime_rows(
            facts,
            query=query,
            text_builder=lambda row: " ".join(
                [
                    str(row.get("action") or ""),
                    str(row.get("status") or ""),
                    str(row.get("detail") or ""),
                    str(row.get("evidence") or ""),
                ]
            ),
            time_builder=lambda row: str(row.get("created_at") or ""),
            importance_builder=lambda row: 0.72 if str(row.get("evidence") or "").strip() else 0.55,
            limit=limit,
        )

        blocks = []
        try:
            blocks = self.memory_blocks.find_blocks(
                agent=agent,
                block_types=["skill", "playbook", "owner_preference", "knowledge", "failure"],
                limit=limit,
            )
        except Exception:
            blocks = []
        blocks = self._rerank_runtime_rows(
            blocks,
            query=query,
            text_builder=lambda row: " ".join(
                [
                    str(row.get("summary") or ""),
                    str(row.get("block_type") or ""),
                    str(row.get("metadata_json") or ""),
                ]
            ),
            time_builder=lambda row: str(row.get("updated_at") or ""),
            importance_builder=lambda row: float(row.get("importance") or 0.5),
            limit=limit,
        )

        playbooks = []
        try:
            playbooks = PlaybookRegistry().find(agent=agent, task_type=task, limit=limit)
            for row in playbooks:
                succ = int(row.get("success_count") or 0)
                fail = int(row.get("fail_count") or 0)
                total = succ + fail
                row["success_rate"] = round((succ / total), 3) if total > 0 else 0.0
        except Exception:
            playbooks = []
        playbooks = self._rerank_runtime_rows(
            playbooks,
            query=query,
            text_builder=lambda row: " ".join(
                [
                    str(row.get("action") or ""),
                    str(row.get("task_type") or ""),
                    str(row.get("strategy_json") or ""),
                ]
            ),
            time_builder=lambda row: str(row.get("updated_at") or ""),
            importance_builder=lambda row: float(row.get("success_rate") or 0.0),
            limit=limit,
        )

        platform_memory = []
        try:
            platform_terms = [task]
            platform_terms.extend([x for x in contract.get("owned_outcomes", []) if "platform" in x or "listing" in x or "publish" in x])
            query_text = " ".join([x for x in platform_terms if x]).strip() or agent
            platform_memory = search_platform_knowledge(query_text, limit=limit)
        except Exception:
            platform_memory = []
        platform_memory = self._rerank_runtime_rows(
            platform_memory,
            query=query,
            text_builder=lambda row: " ".join(
                [
                    str(row.get("service") or ""),
                    str(row.get("content") or ""),
                ]
            ),
            time_builder=lambda row: "",
            importance_builder=lambda row: 0.7,
            limit=limit,
        )

        runbook_packs = []
        try:
            services: list[str] = []
            for item in platform_memory:
                svc = str(item.get("service") or "").strip().lower()
                if svc:
                    services.append(svc.split()[0])
            task_low = str(task or "").strip().lower()
            outcome_low = " ".join([str(x or "").lower() for x in contract.get("owned_outcomes", [])])
            service_hints = {
                "etsy": ("etsy", "этси", "етси"),
                "gumroad": ("gumroad", "гумроад", "гумр"),
                "amazon_kdp": ("amazon", "амаз", "kdp", "кдп"),
                "printful": ("printful", "принтфул"),
                "kofi": ("kofi", "ko-fi", "кофи", "ко фи"),
                "twitter": ("twitter", "твит", "x.com"),
                "pinterest": ("pinterest", "пинтерест", "пинтрест"),
                "reddit": ("reddit", "реддит"),
            }
            for service, hints in service_hints.items():
                if any(h in task_low for h in hints) or any(h in outcome_low for h in hints):
                    services.append(service)
            runbook_packs = build_runbook_packs_for_services(services)
        except Exception:
            runbook_packs = []
        runbook_packs = self._rerank_runtime_rows(
            runbook_packs,
            query=query,
            text_builder=lambda row: " ".join(
                [
                    str(row.get("service") or ""),
                    json.dumps(row, ensure_ascii=False)[:2500],
                ]
            ),
            time_builder=lambda row: "",
            importance_builder=lambda row: 0.82,
            limit=limit,
        )

        memory_layers = self._build_memory_layers_map(
            agent=agent,
            task=task,
            contract=contract,
            skills=skills[:limit],
            playbooks=playbooks[:limit],
            failures=failures[:limit],
            facts=facts[:limit],
            blocks=blocks[:limit],
            platform_memory=platform_memory[:limit],
            runbook_packs=runbook_packs[:limit],
            failure_substrate=failure_substrate,
        )

        return {
            "agent": agent,
            "task_type": task,
            "contract": contract,
            "skills": skills[:limit],
            "playbooks": playbooks[:limit],
            "recent_failures": failures[:limit],
            "recent_facts": facts[:limit],
            "failure_substrate": failure_substrate,
            "memory_blocks": blocks[:limit],
            "platform_memory": platform_memory[:limit],
            "runbook_packs": runbook_packs[:limit],
            "memory_layers": memory_layers,
        }

    def _sqlite_path_value(self) -> str:
        return str(getattr(self, "_sqlite_path", "") or settings.SQLITE_PATH)

    @staticmethod
    def _simple_semantic_overlap(query: str, text: str) -> float:
        q = {x for x in str(query or "").lower().split() if len(x) >= 3}
        t = {x for x in str(text or "").lower().split() if len(x) >= 3}
        if not q or not t:
            return 0.0
        common = len(q.intersection(t))
        return min(1.0, common / max(1, len(q)))

    def _rerank_runtime_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        query: str,
        text_builder,
        time_builder,
        importance_builder,
        limit: int,
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for row in rows or []:
            try:
                text = str(text_builder(row) or "")
                ts = time_builder(row)
                importance = float(importance_builder(row) or 0.4)
                semantic = self._simple_semantic_overlap(query, text)
                recency_dt = self._parse_runtime_dt(ts)
                relevance = self.calculate_relevance(semantic, recency_dt, importance=importance)
                item = dict(row)
                item["runtime_relevance"] = round(relevance, 6)
                scored.append(item)
            except Exception:
                scored.append(dict(row))
        scored.sort(key=lambda x: float(x.get("runtime_relevance") or 0.0), reverse=True)
        return scored[:limit]

    @staticmethod
    def _parse_runtime_dt(value: str) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.now(timezone.utc)
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _load_protected_registry_summary(self) -> dict[str, Any]:
        if not _PROTECTED_TARGETS_PATH.exists():
            return {"total": 0, "services": {}}
        try:
            data = json.loads(_PROTECTED_TARGETS_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"total": 0, "services": {}}
            services: dict[str, int] = {}
            total = 0
            for key, rows in data.items():
                count = len(rows or []) if isinstance(rows, list) else 0
                services[str(key)] = count
                total += count
            return {"total": total, "services": services}
        except Exception:
            return {"total": 0, "services": {}}

    def _build_memory_layers_map(
        self,
        *,
        agent: str,
        task: str,
        contract: dict[str, Any],
        skills: list[dict[str, Any]],
        playbooks: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
        platform_memory: list[dict[str, Any]],
        runbook_packs: list[dict[str, Any]],
        failure_substrate: dict[str, Any],
    ) -> dict[str, Any]:
        owner_blocks = [x for x in blocks if str(x.get("block_type") or "").strip().lower() == "owner_preference"]
        task_blocks = [x for x in blocks if str(x.get("block_type") or "").strip().lower() in {"knowledge", "skill", "playbook"}]
        return {
            "agent": agent,
            "task_type": task,
            "owner_memory": {
                "count": len(owner_blocks),
                "active": bool(owner_blocks),
            },
            "task_memory": {
                "facts": len(facts),
                "blocks": len(task_blocks),
                "active": bool(facts or task_blocks),
            },
            "platform_runbooks": {
                "knowledge_entries": len(platform_memory),
                "runbook_packs": len(runbook_packs),
                "active": bool(platform_memory or runbook_packs),
            },
            "anti_pattern_memory": {
                "recent_failures": len(failures),
                "failure_substrate_entries": len(list((failure_substrate or {}).get("entries") or [])),
                "avoid_actions": len(list((failure_substrate or {}).get("avoid_actions") or [])),
                "active": bool(failures or (failure_substrate or {}).get("entries")),
            },
            "self_learning_memory": {
                "skills": len(skills),
                "playbooks": len(playbooks),
                "active": bool(skills or playbooks),
            },
            "protected_object_registry": self._load_protected_registry_summary(),
            "contract_outcomes": list((contract or {}).get("owned_outcomes") or []),
        }

    def search_skills(self, query: str, limit: int = 5) -> list[dict]:
        """Семантический поиск навыков: ChromaDB → обогащение из SQLite."""
        results = []
        seen_names = set()

        # 1. Семантический поиск через ChromaDB
        try:
            collection = self._get_chroma()
            embed = self._embed_texts([query])
            if embed:
                try:
                    chroma_results = collection.query(
                        query_embeddings=embed,
                        n_results=limit,
                        where={"type": "skill"},
                    )
                except Exception as e:
                    if self._is_dimension_mismatch_error(e):
                        self._embed_query_fallback_only = True
                        logger.warning(
                            "Skill query embedding mismatch; fallback to query_texts",
                            extra={"event": "chroma_skill_query_dim_fallback"},
                        )
                        chroma_results = collection.query(
                            query_texts=[query],
                            n_results=limit,
                            where={"type": "skill"},
                        )
                    else:
                        raise
            else:
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

    def get_patterns(self, category: str = "", query: str = "", limit: int = 20) -> list[dict]:
        """Return patterns with optional category/query filters (newest/high-confidence first)."""
        conn = self._get_sqlite()
        lim = max(1, int(limit or 20))
        q = str(query or "").strip().lower()
        cat = str(category or "").strip()
        if cat and q:
            rows = conn.execute(
                """
                SELECT *
                FROM patterns
                WHERE category = ?
                  AND (LOWER(pattern_key) LIKE ? OR LOWER(pattern_value) LIKE ?)
                ORDER BY confidence DESC, id DESC
                LIMIT ?
                """,
                (cat, f"%{q}%", f"%{q}%", lim),
            ).fetchall()
        elif cat:
            rows = conn.execute(
                """
                SELECT *
                FROM patterns
                WHERE category = ?
                ORDER BY confidence DESC, id DESC
                LIMIT ?
                """,
                (cat, lim),
            ).fetchall()
        elif q:
            rows = conn.execute(
                """
                SELECT *
                FROM patterns
                WHERE LOWER(pattern_key) LIKE ? OR LOWER(pattern_value) LIKE ?
                ORDER BY confidence DESC, id DESC
                LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM patterns
                ORDER BY confidence DESC, id DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_errors(self, limit: int = 20, module: str = "", unresolved_only: bool = False) -> list[dict]:
        """Return recent errors for quick operational context in runtime decisions."""
        conn = self._get_sqlite()
        lim = max(1, int(limit or 20))
        mod = str(module or "").strip()
        where = []
        params: list[Any] = []
        if mod:
            where.append("module = ?")
            params.append(mod)
        if unresolved_only:
            where.append("resolved = 0")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""
            SELECT *
            FROM errors
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, lim),
        ).fetchall()
        return [dict(r) for r in rows]

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
                CREATE INDEX IF NOT EXISTS idx_episodic_embedding_ivfflat
                ON episodic_memory USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 50);
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
            try:
                embed = self._embed_texts([summary])
                if embed and row and row["id"]:
                    await conn.execute(
                        "UPDATE episodic_memory SET embedding=$1::vector WHERE id=$2",
                        embed[0],
                        row["id"],
                    )
            except Exception:
                pass
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
        """Поиск в эпизодической памяти по тексту с relevance reranking."""
        pool = await self._get_pg()
        async with pool.acquire() as conn:
            rows = []
            try:
                embed = self._embed_texts([query])
                if embed:
                    rows = await conn.fetch(
                        """SELECT id, event_type, summary, details, importance, created_at
                           FROM episodic_memory
                           WHERE embedding IS NOT NULL
                           ORDER BY embedding <=> $1::vector
                           LIMIT $2""",
                        embed[0], max(limit * 5, 20),
                    )
            except Exception:
                rows = []
            if not rows:
                rows = await conn.fetch(
                    """SELECT id, event_type, summary, details, importance, created_at
                       FROM episodic_memory
                       WHERE summary ILIKE $1
                       ORDER BY created_at DESC
                       LIMIT $2""",
                    f"%{query}%", max(limit * 5, 20),
                )
            query_terms = {t for t in str(query or "").lower().split() if t}
            ranked: list[dict] = []
            for row in rows:
                item = dict(row)
                summary = str(item.get("summary") or "")
                summary_terms = {t for t in summary.lower().split() if t}
                overlap = (
                    len(query_terms & summary_terms) / max(1, len(query_terms))
                    if query_terms else 0.0
                )
                created_at = item.get("created_at") or datetime.now(timezone.utc)
                if getattr(created_at, "tzinfo", None) is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                item["_relevance"] = self.calculate_relevance(
                    semantic_similarity=float(overlap),
                    created_at=created_at,
                    importance=float(item.get("importance") or 0.5),
                )
                ranked.append(item)
            ranked.sort(key=lambda x: float(x.get("_relevance") or 0.0), reverse=True)
            for item in ranked:
                item.pop("_relevance", None)
            return ranked[:limit]

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
