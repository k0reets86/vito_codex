from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from memory.memory_manager import MemoryManager
from modules.skill_registry import SkillRegistry

logger = get_logger("skill_library", agent="skill_library")

SKILL_LIBRARY_DIR = PROJECT_ROOT / ".learnings" / "skills"


class VITOSkillLibrary:
    """Growing library of reusable operational skills.

    The library stores:
    - structured records in SQLite
    - human-readable markdown/json files on disk
    - semantic pointers in MemoryManager / SkillRegistry
    """

    def __init__(self, sqlite_path: Optional[str] = None, memory: MemoryManager | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.memory = memory
        self.registry = SkillRegistry(sqlite_path=self.sqlite_path)
        self._init_db()
        SKILL_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS skill_library (
                    skill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    source_agent TEXT DEFAULT '',
                    trigger_hint TEXT DEFAULT '',
                    code_ref TEXT DEFAULT '',
                    tags_json TEXT DEFAULT '[]',
                    metadata_json TEXT DEFAULT '{}',
                    usage_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_used_at TEXT DEFAULT ''
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS n FROM skill_library").fetchone()
            return int((row["n"] if row else 0) or 0)
        finally:
            conn.close()

    def add_skill(
        self,
        name: str,
        description: str,
        *,
        category: str = "",
        source_agent: str = "",
        trigger_hint: str = "",
        code_ref: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        skill = {
            "name": str(name or "").strip(),
            "description": str(description or "").strip(),
            "category": str(category or "").strip(),
            "source_agent": str(source_agent or "").strip(),
            "trigger_hint": str(trigger_hint or "").strip(),
            "code_ref": str(code_ref or "").strip(),
            "tags": [str(t).strip() for t in (tags or []) if str(t).strip()],
            "metadata": dict(metadata or {}),
        }
        if not skill["name"]:
            raise ValueError("skill_name_required")

        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO skill_library
                (name, description, category, source_agent, trigger_hint, code_ref, tags_json, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    category=excluded.category,
                    source_agent=excluded.source_agent,
                    trigger_hint=excluded.trigger_hint,
                    code_ref=excluded.code_ref,
                    tags_json=excluded.tags_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    skill["name"],
                    skill["description"],
                    skill["category"],
                    skill["source_agent"],
                    skill["trigger_hint"],
                    skill["code_ref"],
                    json.dumps(skill["tags"], ensure_ascii=False),
                    json.dumps(skill["metadata"], ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self._write_human_readable(skill)
        try:
            self.registry.register_skill(
                name=skill["name"],
                category=skill["category"],
                source=skill["source_agent"] or "skill_library",
                status="learned",
                notes=skill["description"][:300],
            )
        except Exception:
            pass
        try:
            mm = self.memory or MemoryManager()
            mm.store_knowledge(
                doc_id=f"skill_lib_{skill['name']}",
                text=(
                    f"Skill {skill['name']}: {skill['description']}\n"
                    f"Tags: {', '.join(skill['tags'])}\n"
                    f"Trigger: {skill['trigger_hint']}\n"
                    f"Source agent: {skill['source_agent']}"
                ),
                metadata={
                    "type": "skill_library",
                    "block_type": "skill",
                    "skill_name": skill["name"],
                    "name": skill["name"],
                    "category": skill["category"],
                    "agent": skill["source_agent"] or "",
                    "importance_score": 0.8,
                },
            )
        except Exception:
            pass

    def record_use(self, name: str, success: bool = True) -> None:
        conn = self._conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """
                UPDATE skill_library
                SET usage_count = usage_count + 1,
                    success_count = success_count + ?,
                    last_used_at = ?,
                    updated_at = ?
                WHERE name = ?
                """,
                (1 if success else 0, now, now, name),
            )
            conn.commit()
        finally:
            conn.close()
        try:
            self.registry.record_use(name)
        except Exception:
            pass

    def retrieve(self, query: str, n: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        query_tokens = {tok for tok in _norm_text(query).split() if tok}
        semantic_names: list[str] = []
        try:
            mm = self.memory or MemoryManager()
            if getattr(mm, "_chroma_doc_count", 0) > 0:
                hits = mm.search_knowledge(f"skill {query}", n_results=max(4, int(n or 5) * 2))
                for hit in hits:
                    meta = hit.get("metadata") or {}
                    name = str(meta.get("name") or meta.get("skill_name") or "").strip()
                    if name and name not in semantic_names:
                        semantic_names.append(name)
        except Exception:
            semantic_names = []
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM skill_library WHERE status = 'active'").fetchall()
        finally:
            conn.close()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            item["tags"] = _loads(item.get("tags_json"), [])
            item["metadata"] = _loads(item.get("metadata_json"), {})
            if category and str(item.get("category") or "").strip().lower() != str(category).strip().lower():
                continue
            hay = " ".join(
                [
                    str(item.get("name") or ""),
                    str(item.get("description") or ""),
                    str(item.get("trigger_hint") or ""),
                    " ".join(item.get("tags") or []),
                ]
            )
            hay_tokens = {tok for tok in _norm_text(hay).split() if tok}
            overlap = len(query_tokens & hay_tokens)
            usage_bonus = min(5.0, float(item.get("usage_count") or 0) * 0.1)
            success_rate = 0.0
            usage = float(item.get("usage_count") or 0)
            if usage > 0:
                success_rate = float(item.get("success_count") or 0) / usage
            score = float(overlap) + usage_bonus + success_rate
            name = str(item.get("name") or "").strip()
            if name in semantic_names:
                score += max(2.0, float(len(semantic_names) - semantic_names.index(name)))
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: (-x[0], str(x[1].get("name") or "")))
        return [item for _, item in scored[: max(1, int(n or 5))]]

    def list_all(self, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM skill_library ORDER BY updated_at DESC LIMIT ?",
                (int(limit or 200),),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["tags"] = _loads(item.get("tags_json"), [])
                item["metadata"] = _loads(item.get("metadata_json"), {})
                result.append(item)
            return result
        finally:
            conn.close()

    def _write_human_readable(self, skill: dict[str, Any]) -> None:
        path = SKILL_LIBRARY_DIR / f"{skill['name']}.json"
        path.write_text(json.dumps(skill, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_initial_skills(sqlite_path: Optional[str] = None) -> int:
    lib = VITOSkillLibrary(sqlite_path=sqlite_path)
    seeds = [
        {
            "name": "create_gumroad_listing",
            "description": "Create and fully verify a Gumroad listing with file, cover, preview, tags and category.",
            "category": "commerce_execution",
            "source_agent": "ecommerce_agent",
            "trigger_hint": "gumroad listing create publish",
            "code_ref": "platforms/gumroad.py",
            "tags": ["gumroad", "listing", "publish"],
        },
        {
            "name": "write_marketplace_seo_title",
            "description": "Write a marketplace SEO title with demand terms, buyer intent and category relevance.",
            "category": "content_growth",
            "source_agent": "seo_agent",
            "trigger_hint": "seo title marketplace",
            "code_ref": "agents/seo_agent.py",
            "tags": ["seo", "title", "marketplace"],
        },
        {
            "name": "printful_to_etsy_sync",
            "description": "Create a Printful merch item and sync it to an Etsy draft with linked editor verification.",
            "category": "commerce_execution",
            "source_agent": "publisher_agent",
            "trigger_hint": "printful etsy linked flow",
            "code_ref": "platforms/printful.py",
            "tags": ["printful", "etsy", "pod"],
        },
    ]
    for seed in seeds:
        lib.add_skill(**seed)
    return lib.count()


def _loads(value: Any, default):
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _norm_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().replace("-", " ").replace("_", " ").split())
