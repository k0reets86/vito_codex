"""Durable parallel orchestration runtime for dependency-aware node execution."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from config.settings import settings


AsyncHandler = Callable[[], Awaitable[Any]]


@dataclass(slots=True)
class ParallelNode:
    name: str
    handler: AsyncHandler
    deps: list[str] = field(default_factory=list)
    description: str = ""


class ParallelOrchestrationRuntime:
    RUN_TABLE = "parallel_workflow_runs"
    NODE_TABLE = "parallel_workflow_nodes"

    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.RUN_TABLE} (
                run_id TEXT PRIMARY KEY,
                workflow_key TEXT NOT NULL,
                state TEXT DEFAULT 'created',
                summary_json TEXT DEFAULT '{{}}',
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.NODE_TABLE} (
                run_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                deps_json TEXT DEFAULT '[]',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                detail TEXT DEFAULT '',
                output_json TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (run_id, node_name)
            )
            """
        )
        conn.commit()
        conn.close()

    def _create_run(self, run_id: str, workflow_key: str, nodes: Iterable[ParallelNode]) -> None:
        conn = self._conn()
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {self.RUN_TABLE}(run_id, workflow_key, state, summary_json, updated_at)
            VALUES (?, ?, 'executing', '{{}}', datetime('now'))
            """,
            (run_id, workflow_key),
        )
        for node in nodes:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.NODE_TABLE}(
                    run_id, node_name, deps_json, description, status, detail, output_json, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', '', '', datetime('now'))
                """,
                (run_id, node.name, json.dumps(list(node.deps), ensure_ascii=False), node.description),
            )
        conn.commit()
        conn.close()

    def _set_node_status(self, run_id: str, node_name: str, status: str, detail: str = "", output: Any = None) -> None:
        payload = ""
        if output is not None:
            try:
                payload = json.dumps(output, ensure_ascii=False, default=str)
            except Exception:
                payload = json.dumps(str(output), ensure_ascii=False)
        conn = self._conn()
        conn.execute(
            f"""
            UPDATE {self.NODE_TABLE}
            SET status = ?, detail = ?, output_json = ?, updated_at = datetime('now')
            WHERE run_id = ? AND node_name = ?
            """,
            (status, detail, payload, run_id, node_name),
        )
        conn.commit()
        conn.close()

    def _set_run_state(self, run_id: str, state: str, summary: dict[str, Any]) -> None:
        conn = self._conn()
        conn.execute(
            f"""
            UPDATE {self.RUN_TABLE}
            SET state = ?, summary_json = ?, updated_at = datetime('now')
            WHERE run_id = ?
            """,
            (state, json.dumps(summary, ensure_ascii=False, default=str), run_id),
        )
        conn.commit()
        conn.close()

    def list_nodes(self, run_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            f"""
            SELECT run_id, node_name, deps_json, description, status, detail, output_json, updated_at
            FROM {self.NODE_TABLE}
            WHERE run_id = ?
            ORDER BY node_name ASC
            """,
            (run_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def run(self, workflow_key: str, nodes: Iterable[ParallelNode], run_id: str | None = None) -> dict[str, Any]:
        node_list = list(nodes)
        node_map = {node.name: node for node in node_list}
        run_id = (run_id or workflow_key).strip()
        self._create_run(run_id, workflow_key, node_list)

        completed: dict[str, Any] = {}
        failed: dict[str, str] = {}
        pending = set(node_map.keys())

        while pending:
            frontier = [
                node_map[name]
                for name in sorted(pending)
                if all(dep in completed for dep in node_map[name].deps)
            ]
            if not frontier:
                # Remaining nodes depend on failed nodes or cyclic deps.
                for name in sorted(pending):
                    dep_failures = [dep for dep in node_map[name].deps if dep in failed]
                    detail = f"blocked_by={','.join(dep_failures)}" if dep_failures else "unresolved_dependencies"
                    self._set_node_status(run_id, name, "blocked", detail=detail)
                    failed[name] = detail
                break

            for node in frontier:
                self._set_node_status(run_id, node.name, "executing")

            async def _run_node(node: ParallelNode) -> tuple[str, bool, Any]:
                try:
                    result = await node.handler()
                    return node.name, True, result
                except Exception as exc:  # pragma: no cover - exercised in tests indirectly
                    return node.name, False, exc

            results = await asyncio.gather(*(_run_node(node) for node in frontier))
            for name, ok, result in results:
                pending.discard(name)
                if ok:
                    completed[name] = result
                    self._set_node_status(run_id, name, "completed", output=result)
                else:
                    failed[name] = str(result)
                    self._set_node_status(run_id, name, "failed", detail=str(result))

        state = "completed" if not failed else "degraded"
        summary = {
            "completed": sorted(completed.keys()),
            "failed": failed,
            "total": len(node_list),
            "completed_count": len(completed),
            "failed_count": len(failed),
        }
        self._set_run_state(run_id, state, summary)
        return {"run_id": run_id, "workflow_key": workflow_key, "state": state, **summary}
