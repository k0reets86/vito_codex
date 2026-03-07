from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re

from config.paths import root_path


def _safe_slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return (s[:max_len].strip("-") or "research")


def save_full_report(
    topic: str,
    body: str,
    *,
    task_root_id: str = "",
    sources: list[str] | None = None,
    structured: dict | None = None,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(root_path("runtime", "research_reports"))
    root.mkdir(parents=True, exist_ok=True)
    prefix = str(task_root_id or "").strip() or f"research_{ts}"
    path = root / f"{prefix}_{_safe_slug(topic)}.md"
    src = ", ".join(sorted({str(x).strip() for x in (sources or []) if str(x).strip()})) or "not_detected"
    structured_block = ""
    if isinstance(structured, dict) and structured:
        structured_block = (
            "\n## Structured Research Payload\n"
            "```json\n"
            f"{json.dumps(structured, ensure_ascii=False, indent=2)}\n"
            "```\n"
        )
    text = (
        f"# Deep Research Report\n\n"
        f"- Topic: {topic}\n"
        f"- Task Root ID: {task_root_id or 'n/a'}\n"
        f"- Sources: {src}\n"
        f"- Generated At (UTC): {datetime.now(timezone.utc).isoformat()}\n\n"
        f"{str(body or '').strip()}\n"
        f"{structured_block}"
    )
    path.write_text(text, encoding="utf-8")
    return str(path)
