"""Runtime helpers for intelligence/research family agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_research_runtime_profile(
    topic: str,
    data_sources: list[str] | None,
    judge_payload: dict[str, Any] | None,
    report_path: str | None,
) -> dict[str, Any]:
    sources = [str(s).strip() for s in (data_sources or []) if str(s).strip()]
    judge = dict(judge_payload or {})
    gaps = list(judge.get("gaps") or [])
    return {
        "topic": str(topic or "").strip(),
        "source_count": len(sources),
        "sources": sources,
        "judge_decision": judge.get("decision"),
        "judge_score": judge.get("score"),
        "gap_count": len(gaps),
        "recovery_mode": "gap_repair" if gaps else "ready",
        "next_actions": (
            ["collect_additional_sources", "rerun_synthesis", "rerun_judge"]
            if gaps
            else ["promote_report_to_runbook", "pass_to_marketing_or_ecommerce"]
        ),
        "report_path": str(report_path or "").strip(),
    }


def build_trend_runtime_profile(
    mode: str,
    source_urls: list[str] | None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    urls = [str(u).strip() for u in (source_urls or []) if str(u).strip()]
    has_fallback = bool(str(fallback_reason or "").strip())
    return {
        "mode": str(mode or "").strip() or "unknown",
        "source_count": len(urls),
        "source_urls": urls,
        "fallback_reason": str(fallback_reason or "").strip(),
        "recovery_mode": "fallback_active" if has_fallback else "primary_sources",
        "next_actions": (
            ["restore_primary_source", "rerun_trend_scan", "compare_fallback_vs_primary"]
            if has_fallback
            else ["rank_trends", "handoff_to_research_agent"]
        ),
    }


def build_analytics_runtime_profile(
    anomalies: list[str] | None,
    health: str | None,
    forecast_confidence: str | None,
) -> dict[str, Any]:
    anomaly_list = [str(a).strip() for a in (anomalies or []) if str(a).strip()]
    status = str(health or "").strip() or "unknown"
    confidence = str(forecast_confidence or "").strip() or "unknown"
    return {
        "anomaly_count": len(anomaly_list),
        "anomalies": anomaly_list,
        "health": status,
        "forecast_confidence": confidence,
        "recovery_mode": "anomaly_recovery" if anomaly_list else "steady_state",
        "next_actions": (
            ["open_investigation", "escalate_to_marketing_and_ecommerce", "rerun_dashboard_after_fix"]
            if anomaly_list
            else ["monitor", "refresh_dashboard", "compare_with_next_period"]
        ),
    }


def build_document_runtime_profile(path: str, capability: str) -> dict[str, Any]:
    file_path = Path(str(path or "").strip()).expanduser()
    exists = file_path.exists()
    suffix = file_path.suffix.lower() if file_path.suffix else ""
    return {
        "capability": str(capability or "").strip(),
        "path": str(file_path),
        "exists": exists,
        "suffix": suffix,
        "recovery_mode": "needs_source_file" if not exists else "parse_ready",
        "next_actions": (
            ["provide_existing_file_path", "choose_supported_format", "retry_parse"]
            if not exists
            else ["parse_document", "store_extract", "handoff_to_research_agent"]
        ),
    }

