from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT
from modules.platform_docs_runtime import sync_docs_runtime
from modules.platform_knowledge import get_service_knowledge
from modules.platform_policy_packs import build_service_policy_pack, SERVICE_PATTERNS
from modules.platform_requirements import RUNBOOK_REQUIREMENTS

_REGISTRY_PATH = PROJECT_ROOT / "runtime" / "platform_runtime_registry.json"

ALIASES = {
    "amazon": "amazon_kdp",
    "kdp": "amazon_kdp",
    "x": "twitter",
    "ko-fi": "kofi",
}


def _alias(service: str) -> str:
    low = str(service or "").strip().lower()
    return ALIASES.get(low, low)


def _read_registry() -> dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        return {"services": {}, "updated_at": ""}
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("services", {})
            return data
    except Exception:
        pass
    return {"services": {}, "updated_at": ""}


def _write_registry(data: dict[str, Any]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _dedupe_strings(values: list[str], *, limit: int = 50) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _normalize_rule_updates(updates: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in updates or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        excerpt = str(row.get("excerpt") or "").strip()
        key = (title.lower(), excerpt[:160].lower())
        if not title or key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "excerpt": excerpt[:500]})
        if len(out) >= limit:
            break
    return out


def build_runtime_entry(service: str) -> dict[str, Any]:
    svc = _alias(service)
    knowledge = get_service_knowledge(svc)
    policy_pack = build_service_policy_pack(svc)
    base = RUNBOOK_REQUIREMENTS.get(svc, {})
    success_rows = list((knowledge.get("success_runbooks") or [])[-10:])
    failure_rows = list((knowledge.get("failure_runbooks") or [])[-10:])
    lessons: list[str] = []
    anti_patterns: list[str] = []
    evidence_keys: list[str] = []
    urls: list[str] = []
    sources: list[str] = []
    for bucket in (success_rows, failure_rows):
        for row in bucket:
            if not isinstance(row, dict):
                continue
            lessons.extend([str(x) for x in (row.get("lessons") or [])])
            anti_patterns.extend([str(x) for x in (row.get("anti_patterns") or [])])
            if row.get("url"):
                urls.append(str(row.get("url")))
            if row.get("source"):
                sources.append(str(row.get("source")))
            ev = row.get("evidence") or {}
            if isinstance(ev, dict):
                evidence_keys.extend([str(k) for k in ev.keys()])
    recommended_steps = _dedupe_strings(list(base.get("preferred_actions") or []) + lessons + list(policy_pack.get("lessons") or []), limit=30)
    avoid_patterns = _dedupe_strings(anti_patterns + list(policy_pack.get("policy_notes") or []) + list(policy_pack.get("anti_patterns") or []), limit=30)
    return {
        "service": svc,
        "service_patterns": list(SERVICE_PATTERNS.get(svc, [])),
        "required_artifacts": list(base.get("required_artifacts") or []),
        "verify_points": list(base.get("verify_points") or []),
        "preferred_actions": list(base.get("preferred_actions") or []),
        "recommended_steps": recommended_steps,
        "avoid_patterns": avoid_patterns,
        "evidence_keys_seen": _dedupe_strings(evidence_keys, limit=30),
        "known_urls": _dedupe_strings(urls, limit=20),
        "known_sources": _dedupe_strings(sources, limit=20),
        "policy_section_titles": list(policy_pack.get("policy_section_titles") or [])[:20],
        "policy_notes": list(policy_pack.get("policy_notes") or [])[:30],
        "rules_updates": _normalize_rule_updates(list(policy_pack.get("rules_updates") or []), limit=10),
        "docs_runtime": {
            "knowledge_count": int(policy_pack.get("has_policy_knowledge") or 0),
            "rules_count": int(policy_pack.get("has_rules_updates") or 0),
            "evidence_fragments": list(policy_pack.get("evidence_fragments") or [])[:5],
        },
        "recent_success_count": len(success_rows),
        "recent_failure_count": len(failure_rows),
        "knowledge_updated_at": str(knowledge.get("updated_at") or ""),
        "runtime_synced_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_platform_runtime_registry(services: list[str] | None = None) -> dict[str, Any]:
    reg = _read_registry()
    svc_map = reg.setdefault("services", {})
    wanted = [_alias(s) for s in (services or []) if str(s).strip()]
    if not wanted:
        wanted = sorted({*_REGISTRY_SERVICE_SET()})
    docs_runtime = sync_docs_runtime(wanted)
    synced: list[str] = []
    for svc in wanted:
        svc_map[svc] = build_runtime_entry(svc)
        synced.append(svc)
    reg["docs_runtime_meta"] = dict(docs_runtime.get("source_meta") or {})
    reg["docs_runtime_schema_version"] = int(docs_runtime.get("schema_version") or 0)
    _write_registry(reg)
    return {"synced": synced, "count": len(synced), "updated_at": reg.get("updated_at")}


def get_runtime_entry(service: str, *, refresh: bool = False) -> dict[str, Any]:
    svc = _alias(service)
    reg = _read_registry()
    services = reg.get("services") if isinstance(reg, dict) else {}
    entry = services.get(svc) if isinstance(services, dict) else None
    if refresh or not isinstance(entry, dict) or not entry:
        entry = build_runtime_entry(svc)
        if isinstance(services, dict):
            services[svc] = entry
            reg["services"] = services
            _write_registry(reg)
    return dict(entry or {})


def _REGISTRY_SERVICE_SET() -> set[str]:
    return {*(RUNBOOK_REQUIREMENTS.keys()), *(SERVICE_PATTERNS.keys())}
