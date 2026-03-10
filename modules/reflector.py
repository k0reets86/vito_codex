from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("reflector", agent="reflector")

LEARNINGS_DIR = Path("/home/vito/vito-agent/.learnings")
LEARNINGS_FILE = LEARNINGS_DIR / "LEARNINGS.md"
ATTRIBUTION_FILE = LEARNINGS_DIR / "attribution_map.json"


class VITOReflector:
    """Verbal reflection + attribution layer."""

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()
        LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
        if not LEARNINGS_FILE.exists():
            LEARNINGS_FILE.write_text("# VITO Learnings\n\n", encoding="utf-8")
        if not ATTRIBUTION_FILE.exists():
            ATTRIBUTION_FILE.write_text("{}", encoding="utf-8")

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT DEFAULT 'general',
                    action_type TEXT DEFAULT '',
                    success INTEGER DEFAULT 0,
                    input_summary TEXT DEFAULT '',
                    outcome_summary TEXT DEFAULT '',
                    reflection_text TEXT DEFAULT '',
                    attribution_json TEXT DEFAULT '{}',
                    task_root_id TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def reflect(
        self,
        *,
        category: str,
        action_type: str,
        input_summary: str,
        outcome_summary: str,
        success: bool,
        task_root_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reflection = self._build_reflection(
            category=category,
            action_type=action_type,
            input_summary=input_summary,
            outcome_summary=outcome_summary,
            success=success,
            context=context or {},
        )
        attribution = self._build_attribution(action_type, success, context or {})
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO reflections
                (category, action_type, success, input_summary, outcome_summary, reflection_text, attribution_json, task_root_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    action_type,
                    1 if success else 0,
                    input_summary[:500],
                    outcome_summary[:1000],
                    reflection[:2000],
                    json.dumps(attribution, ensure_ascii=False),
                    str(task_root_id or "")[:120],
                ),
            )
            conn.commit()
        finally:
            conn.close()
        self._append_learning_markdown(category, action_type, reflection, success)
        self._merge_attribution(attribution)
        return {"reflection": reflection, "attribution": attribution}

    def get_recent(self, n: int = 10, category: str | None = None) -> list[str]:
        conn = self._conn()
        try:
            if category:
                rows = conn.execute(
                    "SELECT reflection_text FROM reflections WHERE category = ? ORDER BY id DESC LIMIT ?",
                    (category, int(n or 10)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT reflection_text FROM reflections ORDER BY id DESC LIMIT ?",
                    (int(n or 10),),
                ).fetchall()
            return [str(r[0] or "") for r in rows if str(r[0] or "").strip()]
        finally:
            conn.close()

    def top_relevant(self, query: str, n: int = 5) -> list[dict[str, Any]]:
        tokens = set(_norm(query).split())
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT category, action_type, success, reflection_text, attribution_json, created_at FROM reflections ORDER BY id DESC LIMIT 200"
            ).fetchall()
        finally:
            conn.close()
        scored = []
        for row in rows:
            item = dict(row)
            text = f"{item.get('category','')} {item.get('action_type','')} {item.get('reflection_text','')}"
            overlap = len(tokens & set(_norm(text).split()))
            if overlap <= 0:
                continue
            item["attribution"] = _loads(item.get("attribution_json"), {})
            scored.append((overlap + (1 if item.get("success") else 0), item))
        scored.sort(key=lambda x: -x[0])
        return [it for _, it in scored[: max(1, int(n or 5))]]

    def attribution_map(self) -> dict[str, Any]:
        return _loads(ATTRIBUTION_FILE.read_text(encoding="utf-8"), {})

    def _build_reflection(
        self,
        *,
        category: str,
        action_type: str,
        input_summary: str,
        outcome_summary: str,
        success: bool,
        context: dict[str, Any],
    ) -> str:
        if success:
            return (
                f"[{category}] Action '{action_type}' succeeded. "
                f"What worked: {outcome_summary[:300]}. "
                f"Next time reuse this path when input resembles: {input_summary[:180]}."
            )
        reason = str(context.get("error") or context.get("reason") or outcome_summary or "failure").strip()
        return (
            f"[{category}] Action '{action_type}' failed because: {reason[:300]}. "
            f"Do not repeat the same path blindly. Prefer a safer alternative and verify after each critical step."
        )

    def _build_attribution(self, action_type: str, success: bool, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": action_type,
            "success": bool(success),
            "factors": list(context.get("factors") or []),
            "platform": str(context.get("platform") or ""),
            "source": str(context.get("source") or ""),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def _append_learning_markdown(self, category: str, action_type: str, reflection: str, success: bool) -> None:
        status = "SUCCESS" if success else "FAIL"
        with LEARNINGS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(
                f"## {datetime.now(timezone.utc).isoformat()} [{status}] {category} / {action_type}\n"
                f"{reflection}\n\n"
            )

    def _merge_attribution(self, attribution: dict[str, Any]) -> None:
        current = self.attribution_map()
        action = str(attribution.get("action_type") or "").strip()
        if not action:
            return
        bucket = current.setdefault(action, {"success": 0, "fail": 0, "platforms": []})
        if attribution.get("success"):
            bucket["success"] = int(bucket.get("success", 0) or 0) + 1
        else:
            bucket["fail"] = int(bucket.get("fail", 0) or 0) + 1
        platform = str(attribution.get("platform") or "").strip()
        if platform and platform not in bucket["platforms"]:
            bucket["platforms"].append(platform)
        ATTRIBUTION_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _loads(value: Any, default):
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())
