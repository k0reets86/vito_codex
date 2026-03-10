from __future__ import annotations

from typing import Any

from modules.platform_knowledge import get_service_knowledge
from modules.platform_requirements import RUNBOOK_REQUIREMENTS
from modules.platform_runtime_registry import get_runtime_entry


def _service_alias(service: str) -> str:
    low = str(service or "").strip().lower()
    aliases = {
        "amazon": "amazon_kdp",
        "kdp": "amazon_kdp",
        "x": "twitter",
        "ko-fi": "kofi",
    }
    return aliases.get(low, low)


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_service_runbook_pack(service: str) -> dict[str, Any]:
    svc = _service_alias(service)
    runtime_entry = get_runtime_entry(svc)
    knowledge = get_service_knowledge(svc)
    base = RUNBOOK_REQUIREMENTS.get(svc, {})
    success_rows = list((knowledge.get("success_runbooks") or [])[-5:])
    failure_rows = list((knowledge.get("failure_runbooks") or [])[-5:])

    lessons: list[str] = []
    anti_patterns: list[str] = []
    evidence_keys: list[str] = []
    urls: list[str] = []
    for row in success_rows:
        lessons.extend([str(x) for x in (row.get("lessons") or [])])
        anti_patterns.extend([str(x) for x in (row.get("anti_patterns") or [])])
        urls.append(str(row.get("url") or "").strip())
        evidence = row.get("evidence") or {}
        if isinstance(evidence, dict):
            evidence_keys.extend([str(k) for k in evidence.keys()])
    for row in failure_rows:
        anti_patterns.extend([str(x) for x in (row.get("anti_patterns") or [])])
        evidence = row.get("evidence") or {}
        if isinstance(evidence, dict):
            evidence_keys.extend([str(k) for k in evidence.keys()])

    return {
        "service": svc,
        "required_artifacts": list(runtime_entry.get("required_artifacts") or base.get("required_artifacts") or []),
        "verify_points": list(runtime_entry.get("verify_points") or base.get("verify_points") or []),
        "preferred_actions": list(runtime_entry.get("preferred_actions") or base.get("preferred_actions") or []),
        "recommended_steps": _dedupe_strings(list(runtime_entry.get("recommended_steps") or []) + lessons)[:20],
        "avoid_patterns": _dedupe_strings(list(runtime_entry.get("avoid_patterns") or []) + anti_patterns)[:20],
        "evidence_keys_seen": _dedupe_strings(list(runtime_entry.get("evidence_keys_seen") or []) + evidence_keys)[:20],
        "known_urls": _dedupe_strings(list(runtime_entry.get("known_urls") or []) + urls)[:10],
        "recent_success_count": len(success_rows),
        "recent_failure_count": len(failure_rows),
        "updated_at": str(knowledge.get("updated_at") or ""),
        "policy_pack": {
            "service": svc,
            "policy_section_titles": list(runtime_entry.get("policy_section_titles") or [])[:20],
            "policy_notes": list(runtime_entry.get("policy_notes") or [])[:30],
            "rules_updates": list(runtime_entry.get("rules_updates") or [])[:10],
            "has_policy_knowledge": bool(runtime_entry.get("policy_section_titles") or runtime_entry.get("policy_notes")),
            "has_rules_updates": bool(runtime_entry.get("rules_updates") or []),
        },
        "policy_notes": list(runtime_entry.get("policy_notes") or [])[:20],
        "rules_updates": list(runtime_entry.get("rules_updates") or [])[:5],
        "runtime_registry": runtime_entry,
    }


def build_runbook_packs_for_services(services: list[str] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for service in services or []:
        svc = _service_alias(service)
        if not svc or svc in seen:
            continue
        seen.add(svc)
        out.append(build_service_runbook_pack(svc))
    return out
