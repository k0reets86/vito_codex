#!/usr/bin/env python3
"""Sync platform run outcomes into VITO memory as skills/patterns/anti-patterns.

Usage:
  PYTHONPATH=. python3 scripts/sync_platform_learnings.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from memory.memory_manager import MemoryManager
from modules.playbook_registry import PlaybookRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_report(prefix: str) -> Path | None:
    candidates = sorted(REPORTS_DIR.glob(f"{prefix}_*.json"))
    return candidates[-1] if candidates else None


def _normalize_status(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {"published", "created", "completed", "success"}:
        return "success"
    if status in {"prepared", "draft"}:
        return "prepared"
    if status in {"error", "failed", "timeout", "network_unavailable", "not_authenticated"}:
        return "failed"
    if not status:
        return "unknown"
    return status


def main() -> int:
    mm = MemoryManager()
    synced = 0
    failed = 0

    # 1) Backfill auto-playbooks from execution facts history
    try:
        PlaybookRegistry().backfill_from_execution_facts(limit=5000)
    except Exception:
        pass

    # 2) Ingest latest all-platform probe (most complete matrix)
    matrix_path = _latest_report("VITO_ALL_PLATFORMS_PROBE")
    docs: list[dict[str, Any]] = []
    if matrix_path:
        data = _load_json(matrix_path) or {}
        docs.extend(list(data.get("results") or []))

    # 3) Ingest latest auth probe
    auth_path = _latest_report("VITO_PLATFORM_AUTH_LIVE_PROBE")
    if auth_path:
        data = _load_json(auth_path) or {}
        docs.extend(list(data.get("results") or []))

    # 4) Ingest latest live publish matrix (API/browser mixed probe)
    live_matrix_path = _latest_report("VITO_PUBLISH_MATRIX_LIVE")
    if live_matrix_path:
        data = _load_json(live_matrix_path) or {}
        docs.extend(list(data.get("results") or []))

    for row in docs:
        platform = str(row.get("platform") or "").strip().lower()
        if not platform:
            continue
        publish = row.get("publish") if isinstance(row.get("publish"), dict) else {}
        auth_ok = bool(row.get("auth_ok", False))
        status_norm = _normalize_status(publish) if publish else ("success" if auth_ok else "failed")

        try:
            if status_norm in {"success", "published", "created"}:
                # Positive skill
                mm.save_skill(
                    name=f"platform:{platform}:publish_path",
                    description=f"Проверенный рабочий путь публикации на {platform}. Использовать как приоритетный flow.",
                    agent="platform_runtime",
                    task_type="platform_publish",
                    method={
                        "status": status_norm,
                        "auth_ok": auth_ok,
                        "evidence": row,
                        "tests_passed": True,
                    },
                )
                mm.save_pattern(
                    category="platform_success_path",
                    key=platform,
                    value=json.dumps(
                        {
                            "status": status_norm,
                            "auth_ok": auth_ok,
                            "source_report": matrix_path.name if matrix_path else "",
                        },
                        ensure_ascii=False,
                    )[:1500],
                    confidence=0.95,
                )
                synced += 1
            elif status_norm in {"prepared", "draft"}:
                # Partial good: flow prepared, but not confirmed live.
                mm.save_pattern(
                    category="platform_prepared_only",
                    key=platform,
                    value=json.dumps(
                        {
                            "status": status_norm,
                            "auth_ok": auth_ok,
                            "note": "Подготовка работает, live-подтверждение отсутствует.",
                            "evidence": row,
                        },
                        ensure_ascii=False,
                    )[:1500],
                    confidence=0.75,
                )
                synced += 1
            else:
                # Anti-pattern + error memory
                reason = (
                    str((publish or {}).get("error") or "")
                    or str(row.get("instantiation_error") or "")
                    or str(row.get("auth_error") or "")
                    or "unknown_failure"
                )
                mm.save_pattern(
                    category="anti_pattern",
                    key=f"platform:{platform}:publish_fail",
                    value=f"Не использовать неподтвержденный flow для {platform}: {reason[:400]}",
                    confidence=0.95,
                )
                mm.log_error(
                    module=f"platform:{platform}",
                    error_type="publish_or_auth_failure",
                    message=reason[:500],
                    resolution="Требуется доработка flow/ключей/авторизации перед повторным live-запуском.",
                )
                failed += 1
        except Exception:
            failed += 1

    print(
        json.dumps(
            {
                "ok": True,
                "source_reports": [p.name for p in [matrix_path, auth_path, live_matrix_path] if p],
                "synced": synced,
                "failed_records": failed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
