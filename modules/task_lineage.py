from __future__ import annotations

from datetime import datetime, timezone
import random
import re
from typing import Any

_KIND_CODES = {
    "project": "PRJ",
    "listing": "LST",
    "product_file": "FIL",
    "cover": "CVR",
    "thumbnail": "THM",
    "preview": "PRV",
    "social_image": "SOC",
    "seo": "SEO",
    "content": "CNT",
    "research": "RSH",
    "publish": "PUB",
    "agent_work": "WRK",
    "metadata": "MET",
}


def _compact_topic(text: str, limit: int = 8) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "", str(text or "").upper())
    return (s[:limit] or "TASK")[:limit]


def generate_task_root_id(text: str = "", *, now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%y%m%d%H%M%S")
    suffix = f"{random.randint(0, 0xFFF):03X}"
    return f"VT{ts}{suffix}{_compact_topic(text, 6)}"


def derive_child_id(task_root_id: str, kind: str, seq: int = 1, agent: str = "") -> str:
    root = re.sub(r"[^A-Za-z0-9]+", "", str(task_root_id or "").upper()) or generate_task_root_id("task")
    code = _KIND_CODES.get(str(kind or "").strip().lower(), "GEN")
    agent_code = _compact_topic(agent, 4) if str(agent or "").strip() else "CORE"
    return f"{root}-{code}{int(seq):03d}-{agent_code}"


def derive_artifact_map(task_root_id: str) -> dict[str, str]:
    return {
        "project_id": derive_child_id(task_root_id, "project", 1, "orchestrator"),
        "listing_id": derive_child_id(task_root_id, "listing", 1, "publisher"),
        "research_id": derive_child_id(task_root_id, "research", 1, "research"),
        "content_id": derive_child_id(task_root_id, "content", 1, "copywriter"),
        "seo_id": derive_child_id(task_root_id, "seo", 1, "seo"),
        "product_file_id": derive_child_id(task_root_id, "product_file", 1, "creator"),
        "cover_id": derive_child_id(task_root_id, "cover", 1, "designer"),
        "thumbnail_id": derive_child_id(task_root_id, "thumbnail", 1, "designer"),
        "preview_id": derive_child_id(task_root_id, "preview", 1, "designer"),
        "social_image_id": derive_child_id(task_root_id, "social_image", 1, "smm"),
        "publish_id": derive_child_id(task_root_id, "publish", 1, "publisher"),
        "metadata_id": derive_child_id(task_root_id, "metadata", 1, "ops"),
    }


def ensure_task_lineage(active: dict[str, Any] | None, text: str = "") -> tuple[str, dict[str, str]]:
    cur = dict(active or {})
    task_root_id = str(cur.get("task_root_id") or "").strip()
    if not task_root_id:
        task_root_id = generate_task_root_id(text or str(cur.get("text") or ""))
    return task_root_id, derive_artifact_map(task_root_id)
