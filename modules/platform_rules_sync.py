"""Platform rules sync: watch official pages, detect changes, persist knowledge."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.platform_knowledge import append_entry
from modules.platform_runtime_registry import get_runtime_entry

logger = get_logger("platform_rules_sync", agent="platform_rules_sync")

STATE_PATH = PROJECT_ROOT / "runtime" / "platform_rules_state.json"
REPORT_PATH = PROJECT_ROOT / "runtime" / "platform_rules_updates.md"


@dataclass(frozen=True)
class RuleSource:
    service: str
    label: str
    url: str


DEFAULT_RULE_SOURCES: list[RuleSource] = [
    RuleSource("gumroad", "Help", "https://gumroad.com/help"),
    RuleSource("etsy", "Seller handbook", "https://www.etsy.com/seller-handbook"),
    RuleSource("kofi", "Help center", "https://help.ko-fi.com/hc/en-us"),
    RuleSource("printful", "API docs", "https://developers.printful.com/docs/"),
    RuleSource("reddit", "API docs", "https://support.reddithelp.com/hc/en-us/sections/360008812051-API"),
    RuleSource("pinterest", "Developer docs", "https://developers.pinterest.com/docs/"),
    RuleSource("amazon_kdp", "KDP help", "https://kdp.amazon.com/en_US/help/topic/G200735480"),
    RuleSource("twitter", "Developer docs", "https://developer.x.com/en/docs"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"sources": {}, "updated_at": ""}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"sources": {}, "updated_at": ""}


def _write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_url_text(url: str, timeout: int = 25, max_bytes: int = 250_000) -> str:
    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; VITO-RulesSync/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes)
    text = raw.decode("utf-8", errors="ignore")
    # remove scripts/styles to avoid noisy hashes
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80_000]


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _ensure_report_header() -> None:
    if not REPORT_PATH.exists():
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text("# Platform Rules Updates\n\n", encoding="utf-8")


def _append_report(service: str, url: str, old_hash: str, new_hash: str, excerpt: str) -> None:
    _ensure_report_header()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    row = (
        f"## {ts} — {service}\n\n"
        f"- Source: {url}\n"
        f"- Old hash: `{old_hash[:12]}`\n"
        f"- New hash: `{new_hash[:12]}`\n"
        f"- Excerpt: {excerpt[:500]}\n\n"
    )
    REPORT_PATH.write_text(REPORT_PATH.read_text(encoding="utf-8") + row, encoding="utf-8")


def sync_platform_rules(
    services: list[str] | None = None,
) -> dict[str, Any]:
    """Return changes across watched platform rule pages."""
    wanted = {str(s).strip().lower() for s in (services or []) if str(s).strip()}
    sources = [s for s in DEFAULT_RULE_SOURCES if (not wanted or s.service in wanted)]
    state = _read_state()
    src_state = state.get("sources") if isinstance(state, dict) else {}
    if not isinstance(src_state, dict):
        src_state = {}

    changes: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for src in sources:
        key = f"{src.service}:{src.url}"
        prev = src_state.get(key, {}) if isinstance(src_state.get(key), dict) else {}
        prev_hash = str(prev.get("hash") or "")
        try:
            text = _fetch_url_text(src.url)
            digest = _hash_text(text)
            src_state[key] = {"service": src.service, "label": src.label, "url": src.url, "hash": digest, "checked_at": _utc_now()}
            if prev_hash and prev_hash != digest:
                excerpt = text[:800]
                changes.append(
                    {
                        "service": src.service,
                        "label": src.label,
                        "url": src.url,
                        "old_hash": prev_hash,
                        "new_hash": digest,
                        "excerpt": excerpt,
                    }
                )
                _append_report(src.service, src.url, prev_hash, digest, excerpt)
                try:
                    append_entry(
                        service=f"{src.service} rules update",
                        content=(
                            f"Source: {src.url}\n"
                            f"Detected rules/content change by hash diff: {prev_hash[:12]} -> {digest[:12]}.\n"
                            f"Excerpt: {excerpt[:1000]}"
                        ),
                    )
                except Exception:
                    pass
                try:
                    get_runtime_entry(src.service, refresh=True)
                except Exception:
                    pass
            checked.append({"service": src.service, "url": src.url, "status": "ok", "hash": digest})
        except Exception as e:
            checked.append({"service": src.service, "url": src.url, "status": "error", "error": str(e)})

    state["sources"] = src_state
    _write_state(state)
    out = {"checked": checked, "changes": changes, "changed_count": len(changes), "checked_count": len(checked)}
    logger.info(
        "Platform rules sync completed",
        extra={"event": "platform_rules_sync_done", "context": {"checked": len(checked), "changed": len(changes)}},
    )
    return out


def configured_services() -> list[str]:
    raw = str(getattr(settings, "PLATFORM_RULES_SYNC_SERVICES", "") or "")
    if not raw.strip():
        return []
    return [x.strip().lower() for x in raw.split(",") if x.strip()]
