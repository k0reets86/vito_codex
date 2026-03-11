"""Platform knowledge manager for VITO."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.logger import get_logger
from config.paths import PROJECT_ROOT

logger = get_logger("platform_knowledge", agent="platform_knowledge")

KB_PATH = PROJECT_ROOT / "docs" / "platform_knowledge.md"
RUNTIME_KB_PATH = PROJECT_ROOT / "runtime" / "platform_knowledge.md"
JSON_DB_PATH = PROJECT_ROOT / "runtime" / "platform_knowledge.json"


def _ensure_header(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Platform Knowledge Base (VITO)\n\n"
            "Updated: N/A\n\n",
            encoding="utf-8",
        )


def append_entry(service: str, content: str) -> None:
    """Append a new service entry with timestamp."""
    _ensure_header(RUNTIME_KB_PATH)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n## {service}\n\n{content.strip()}\n"
    text = RUNTIME_KB_PATH.read_text(encoding="utf-8")
    if text.startswith("Updated: "):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[1].startswith("Updated:"):
            lines[1] = f"Updated: {ts}"
            text = "\n".join(lines) + "\n"
    RUNTIME_KB_PATH.write_text(text + entry, encoding="utf-8")
    logger.info(
        "Platform knowledge appended",
        extra={"event": "platform_kb_append", "context": {"service": service}},
    )


def _read_json_db() -> dict[str, Any]:
    if not JSON_DB_PATH.exists():
        return {"services": {}, "updated_at": ""}
    try:
        data = json.loads(JSON_DB_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"services": {}, "updated_at": ""}
    except Exception:
        return {"services": {}, "updated_at": ""}


def _write_json_db(data: dict[str, Any]) -> None:
    JSON_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    JSON_DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_platform_lesson(
    service: str,
    *,
    status: str,
    summary: str,
    details: str = "",
    url: str = "",
    lessons: list[str] | None = None,
    anti_patterns: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    source: str = "",
) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    st = str(status or "unknown").strip().lower()
    ls = [str(x).strip() for x in (lessons or []) if str(x).strip()]
    anti = [str(x).strip() for x in (anti_patterns or []) if str(x).strip()]
    ev = dict(evidence or {})
    db = _read_json_db()
    services = db.setdefault("services", {})
    bucket = services.setdefault(
        svc,
        {
            "success_runbooks": [],
            "failure_runbooks": [],
            "rules_notes": [],
            "updated_at": "",
        },
    )
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "status": st,
        "summary": str(summary or "").strip()[:500],
        "details": str(details or "").strip()[:4000],
        "url": str(url or "").strip(),
        "lessons": ls[:20],
        "anti_patterns": anti[:20],
        "evidence": ev,
        "source": str(source or "").strip()[:120],
    }
    target_key = "success_runbooks" if st in {"draft", "created", "published", "prepared", "ok", "success"} else "failure_runbooks"
    bucket.setdefault(target_key, []).append(row)
    bucket[target_key] = bucket[target_key][-50:]
    bucket["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_db(db)

    md_lines = [
        f"Status: {st}",
        f"Source: {source or 'n/a'}",
    ]
    if url:
        md_lines.append(f"URL: {url}")
    if summary:
        md_lines.append(f"Summary: {summary}")
    if details:
        md_lines.append(f"Details: {details}")
    if ls:
        md_lines.append("Lessons:")
        md_lines.extend([f"- {x}" for x in ls[:10]])
    if anti:
        md_lines.append("Anti-patterns:")
        md_lines.extend([f"- {x}" for x in anti[:10]])
    if ev:
        md_lines.append(f"Evidence: {json.dumps(ev, ensure_ascii=False)[:1000]}")
    append_entry(f"{svc} lesson", "\n".join(md_lines))
    try:
        from modules.platform_runtime_registry import get_runtime_entry
        get_runtime_entry(svc, refresh=True)
    except Exception:
        pass


def search_entries(query: str, limit: int = 5) -> list[dict]:
    _ensure_header(KB_PATH)
    base_text = KB_PATH.read_text(encoding="utf-8")
    runtime_text = RUNTIME_KB_PATH.read_text(encoding="utf-8") if RUNTIME_KB_PATH.exists() else ""
    text = "\n".join(part for part in [base_text, runtime_text] if part.strip())
    sections = re.split(r"\n## ", text)
    results: list[dict] = []
    q = str(query or "").strip().lower()
    for raw in sections[1:]:
        title, _, body = raw.partition("\n\n")
        hay = f"{title}\n{body}".lower()
        if q and q not in hay:
            continue
        results.append({"service": title.strip(), "content": body.strip()[:4000]})
        if len(results) >= limit:
            break
    return results


def get_service_knowledge(service: str) -> dict[str, Any]:
    svc = str(service or "").strip().lower()
    db = _read_json_db()
    services = db.get("services") if isinstance(db, dict) else {}
    if not isinstance(services, dict):
        return {}
    out = services.get(svc) or {}
    return dict(out) if isinstance(out, dict) else {}
