"""Platform knowledge manager for VITO."""

import re
from datetime import datetime, timezone
from pathlib import Path

from config.logger import get_logger

logger = get_logger("platform_knowledge", agent="platform_knowledge")

KB_PATH = Path("/home/vito/vito-agent/docs/platform_knowledge.md")


def _ensure_header() -> None:
    if not KB_PATH.exists():
        KB_PATH.write_text(
            "# Platform Knowledge Base (VITO)\n\n"
            "Updated: N/A\n\n",
            encoding="utf-8",
        )


def append_entry(service: str, content: str) -> None:
    """Append a new service entry with timestamp."""
    _ensure_header()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n## {service}\n\n{content.strip()}\n"
    text = KB_PATH.read_text(encoding="utf-8")
    if text.startswith("Updated: "):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[1].startswith("Updated:"):
            lines[1] = f"Updated: {ts}"
            text = "\n".join(lines) + "\n"
    KB_PATH.write_text(text + entry, encoding="utf-8")
    logger.info(
        "Platform knowledge appended",
        extra={"event": "platform_kb_append", "context": {"service": service}},
    )


def search_entries(query: str, limit: int = 5) -> list[dict]:
    _ensure_header()
    text = KB_PATH.read_text(encoding="utf-8")
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
