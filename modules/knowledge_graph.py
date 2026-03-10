"""Persistent lightweight knowledge graph for runtime memory relationships."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT


class KnowledgeGraph:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or str(PROJECT_ROOT / "runtime" / "knowledge_graph.db")
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    label TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS kg_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src_id TEXT NOT NULL,
                    dst_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_kg_edges_src_rel ON kg_edges(src_id, relation);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_dst_rel ON kg_edges(dst_id, relation);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_node(self, node_id: str, node_type: str, label: str = "", metadata: dict[str, Any] | None = None) -> None:
        if not node_id or not node_type:
            return
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO kg_nodes(node_id, node_type, label, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(node_id) DO UPDATE SET
                  node_type=excluded.node_type,
                  label=CASE WHEN excluded.label != '' THEN excluded.label ELSE kg_nodes.label END,
                  metadata_json=CASE WHEN excluded.metadata_json != '{}' THEN excluded.metadata_json ELSE kg_nodes.metadata_json END,
                  updated_at=datetime('now')
                """,
                (node_id[:200], node_type[:80], label[:240], json.dumps(metadata or {}, ensure_ascii=False)[:4000]),
            )
            conn.commit()
        finally:
            conn.close()

    def add_edge(
        self,
        src_id: str,
        dst_id: str,
        relation: str,
        *,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not src_id or not dst_id or not relation:
            return
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO kg_edges(src_id, dst_id, relation, weight, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    src_id[:200],
                    dst_id[:200],
                    relation[:80],
                    float(weight or 1.0),
                    json.dumps(metadata or {}, ensure_ascii=False)[:4000],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_knowledge(self, doc_id: str, metadata: dict[str, Any] | None = None) -> None:
        meta = metadata or {}
        self.upsert_node(doc_id, "knowledge", label=str(meta.get("title") or doc_id), metadata=meta)
        self._link_metadata(doc_id, meta, relation_prefix="mentions")

    def record_lesson(
        self,
        lesson_id: str,
        *,
        goal_id: str = "",
        task_family: str = "",
        source_agent: str = "",
        candidate_skill: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta = metadata or {}
        self.upsert_node(lesson_id, "lesson", label=lesson_id, metadata=meta)
        if goal_id:
            goal_node = f"goal:{goal_id}"
            self.upsert_node(goal_node, "goal", label=goal_id)
            self.add_edge(lesson_id, goal_node, "belongs_to_goal")
        if task_family:
            family_node = f"task_family:{task_family}"
            self.upsert_node(family_node, "task_family", label=task_family)
            self.add_edge(lesson_id, family_node, "for_task_family")
        if source_agent:
            agent_node = f"agent:{source_agent}"
            self.upsert_node(agent_node, "agent", label=source_agent)
            self.add_edge(lesson_id, agent_node, "from_agent")
        if candidate_skill:
            skill_node = f"skill:{candidate_skill}"
            self.upsert_node(skill_node, "skill", label=candidate_skill)
            self.add_edge(lesson_id, skill_node, "improves_skill")
        self._link_metadata(lesson_id, meta, relation_prefix="lesson")

    def neighbors(self, node_id: str, relation: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._get_conn()
        try:
            if relation:
                rows = conn.execute(
                    """
                    SELECT src_id, dst_id, relation, weight, metadata_json, created_at
                    FROM kg_edges
                    WHERE src_id = ? AND relation = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (node_id, relation, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT src_id, dst_id, relation, weight, metadata_json, created_at
                    FROM kg_edges
                    WHERE src_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (node_id, int(limit)),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _link_metadata(self, src_id: str, meta: dict[str, Any], *, relation_prefix: str) -> None:
        agent = str(meta.get("agent") or meta.get("source_agent") or "").strip()
        platform = str(meta.get("platform") or meta.get("service") or "").strip()
        task_family = str(meta.get("task_family") or meta.get("type") or "").strip()
        skill = str(meta.get("skill_name") or meta.get("candidate_skill") or "").strip()
        goal = str(meta.get("task_root_id") or meta.get("goal_id") or "").strip()

        if agent:
            agent_node = f"agent:{agent}"
            self.upsert_node(agent_node, "agent", label=agent)
            self.add_edge(src_id, agent_node, f"{relation_prefix}_agent")
        if platform:
            platform_node = f"platform:{platform}"
            self.upsert_node(platform_node, "platform", label=platform)
            self.add_edge(src_id, platform_node, f"{relation_prefix}_platform")
        if task_family:
            family_node = f"task_family:{task_family}"
            self.upsert_node(family_node, "task_family", label=task_family)
            self.add_edge(src_id, family_node, f"{relation_prefix}_task_family")
        if skill:
            skill_node = f"skill:{skill}"
            self.upsert_node(skill_node, "skill", label=skill)
            self.add_edge(src_id, skill_node, f"{relation_prefix}_skill")
        if goal:
            goal_node = f"goal:{goal}"
            self.upsert_node(goal_node, "goal", label=goal)
            self.add_edge(src_id, goal_node, f"{relation_prefix}_goal")
