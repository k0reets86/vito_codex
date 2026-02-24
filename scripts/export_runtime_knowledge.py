#!/usr/bin/env python3
"""
Export runtime knowledge from SQLite into git-tracked markdown files.

Purpose:
- Preserve useful "memory/skills" snapshots in repository text files.
- Avoid committing raw databases with sensitive or noisy data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "memory" / "vito_local.db"
OUT_DIR = ROOT / "docs" / "runtime_exports"


def _rows(conn: sqlite3.Connection, query: str, args: Iterable = ()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(query, tuple(args))
    return list(cur.fetchall())


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        safe = [str(x).replace("\n", " ").replace("|", "\\|") for x in row]
        out.append("| " + " | ".join(safe) + " |")
    return "\n".join(out)


def export_skill_registry(conn: sqlite3.Connection) -> str:
    rows = _rows(
        conn,
        """
        SELECT name, category, source, status, security_status, version, updated_at, last_used
        FROM skill_registry
        ORDER BY updated_at DESC
        LIMIT 200
        """,
    )
    body = _md_table(
        ["name", "category", "source", "status", "security", "version", "updated_at", "last_used"],
        [[r["name"], r["category"], r["source"], r["status"], r["security_status"], r["version"], r["updated_at"], r["last_used"]] for r in rows],
    )
    return "\n".join(
        [
            "# Runtime Skill Registry Snapshot",
            "",
            f"Source DB: `{DB_PATH}`",
            f"Rows exported: {len(rows)} (latest by `updated_at`)",
            "",
            body,
            "",
        ]
    )


def export_gumroad_knowledge(conn: sqlite3.Connection) -> str:
    skill_rows = _rows(
        conn,
        """
        SELECT name, agent, task_type, success_count, fail_count, created_at, last_used, description
        FROM skills
        WHERE lower(name) LIKE '%gumroad%'
           OR lower(COALESCE(description, '')) LIKE '%gumroad%'
           OR lower(COALESCE(last_result, '')) LIKE '%gumroad%'
        ORDER BY created_at DESC
        LIMIT 80
        """,
    )
    fact_rows = _rows(
        conn,
        """
        SELECT id, action, status, detail, evidence, created_at
        FROM execution_facts
        WHERE lower(action) LIKE '%gumroad%'
           OR lower(COALESCE(detail, '')) LIKE '%gumroad%'
           OR lower(COALESCE(evidence, '')) LIKE '%gumroad%'
        ORDER BY created_at DESC
        LIMIT 120
        """,
    )

    skill_table = _md_table(
        ["name", "agent", "task_type", "ok", "fail", "created_at", "last_used", "description"],
        [
            [
                r["name"],
                r["agent"],
                r["task_type"],
                r["success_count"],
                r["fail_count"],
                r["created_at"],
                r["last_used"],
                (r["description"] or "")[:220],
            ]
            for r in skill_rows
        ],
    )
    fact_table = _md_table(
        ["id", "action", "status", "detail", "evidence", "created_at"],
        [
            [
                r["id"],
                r["action"],
                r["status"],
                (r["detail"] or "")[:180],
                (r["evidence"] or "")[:220],
                r["created_at"],
            ]
            for r in fact_rows
        ],
    )

    return "\n".join(
        [
            "# Runtime Gumroad Knowledge Snapshot",
            "",
            "This file captures practical Gumroad-related knowledge from runtime DB tables.",
            f"Source DB: `{DB_PATH}`",
            "",
            "## Skills (gumroad-related)",
            f"Rows: {len(skill_rows)}",
            "",
            skill_table,
            "",
            "## Execution Facts (gumroad-related)",
            f"Rows: {len(fact_rows)}",
            "",
            fact_table,
            "",
        ]
    )


def export_registry_stats(conn: sqlite3.Connection) -> str:
    rows = _rows(
        conn,
        """
        SELECT 'skills' AS metric, COUNT(*) AS value FROM skills
        UNION ALL SELECT 'skill_registry', COUNT(*) FROM skill_registry
        UNION ALL SELECT 'patterns', COUNT(*) FROM patterns
        UNION ALL SELECT 'execution_facts', COUNT(*) FROM execution_facts
        UNION ALL SELECT 'failure_memory', COUNT(*) FROM failure_memory
        UNION ALL SELECT 'agent_feedback', COUNT(*) FROM agent_feedback
        UNION ALL SELECT 'platform_registry', COUNT(*) FROM platform_registry
        """,
    )
    table = _md_table(["metric", "value"], [[r["metric"], r["value"]] for r in rows])
    return "\n".join(
        [
            "# Runtime Memory Stats",
            "",
            f"Source DB: `{DB_PATH}`",
            "",
            table,
            "",
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        (OUT_DIR / "runtime_skill_registry.md").write_text(export_skill_registry(conn))
        (OUT_DIR / "runtime_gumroad_knowledge.md").write_text(export_gumroad_knowledge(conn))
        (OUT_DIR / "runtime_memory_stats.md").write_text(export_registry_stats(conn))
    finally:
        conn.close()

    print(f"Exported to: {OUT_DIR}")


if __name__ == "__main__":
    main()
