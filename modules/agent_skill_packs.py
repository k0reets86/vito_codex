"""Runtime skill/runbook packs for VITO agents."""

from __future__ import annotations

from typing import Any


_PACKS: dict[str, dict[str, Any]] = {
    "translation_agent": {
        "skills": ["language_detection", "term_preserving_translation", "listing_localization", "glossary_control", "locale_profile_selection", "consistency_checks"],
        "evidence": ["source_lang", "target_lang", "mode", "translation_quality_hint", "glossary_terms", "quality_checks"],
        "preferred_workflows": ["W01", "W02"],
    },
    "research_agent": {
        "skills": ["iterative_market_research", "evidence_digest", "opportunity_scoring", "operator_ready_recommendation"],
        "evidence": ["report_path", "data_sources", "overall_score", "recommended_product"],
        "preferred_workflows": ["W01", "W08"],
    },
    "trend_scout": {
        "skills": ["multi_source_trend_scan", "fallback_trend_collection", "trend_signal_ranking", "niche_seed_generation"],
        "evidence": ["trend_runtime_profile", "source_count", "fallback_reason", "next_actions"],
        "preferred_workflows": ["W01", "W08"],
    },
    "analytics_agent": {
        "skills": ["dashboard_snapshot", "anomaly_triage", "forecast_packaging", "agent_performance_review"],
        "evidence": ["analytics_runtime_profile", "metrics", "anomalies", "forecast_confidence"],
        "preferred_workflows": ["W03", "W06"],
    },
    "document_agent": {
        "skills": ["document_ingest", "recovery_aware_parse", "ocr_extract", "knowledge_capture"],
        "evidence": ["document_runtime_profile", "path", "next_actions", "source_status"],
        "preferred_workflows": ["W01", "W08"],
    },
    "browser_agent": {
        "skills": ["screenshot_first_execution", "auth_interrupt_detection", "challenge_detection", "form_upload_navigation", "selector_mapping_preflight", "browser_recovery_decisions"],
        "evidence": ["url", "screenshot_path", "browser_runtime_profile", "browser_recovery"],
        "preferred_workflows": ["W01", "W02", "W04"],
    },
    "ecommerce_agent": {
        "skills": ["listing_package_assembly", "platform_runbook_resolution", "publish_quality_gating", "platform_rules_sync"],
        "evidence": ["platform", "status", "contributors", "verification"],
        "preferred_workflows": ["W01"],
    },
    "account_manager": {
        "skills": ["credential_inventory", "auth_state_reporting", "profile_completion_guidance", "email_code_fetch", "auth_remediation_packs", "platform_auth_checkpointing"],
        "evidence": ["account", "auth_state", "platform", "next_actions", "auth_pack"],
        "preferred_workflows": ["W04"],
    },
    "vito_core": {
        "skills": ["goal_to_runbook_compilation", "cross_agent_dispatch", "product_pipeline_orchestration", "self_improve_planning"],
        "evidence": ["capability", "delegations", "final_decision", "task_root_id"],
        "preferred_workflows": ["W01", "W03", "W08"],
    },
    "smm_agent": {
        "skills": ["platform_native_post_packaging", "hashtag_strategy", "campaign_plan", "approval_safe_social_posting"],
        "evidence": ["platform", "published", "file_path", "post_package"],
        "preferred_workflows": ["W05"],
    },
    "publisher_agent": {
        "skills": ["article_publish_packaging", "quality_gate_before_publish", "owner_approval_before_publish", "platform_publish_result_capture"],
        "evidence": ["platform", "preview_path", "quality_score", "publish_result"],
        "preferred_workflows": ["W02"],
    },
    "hr_agent": {
        "skills": ["agent_performance_audit", "knowledge_audit", "benchmark_gap_detection", "development_plan_generation"],
        "evidence": ["agent", "success_rate", "top_risks", "actions"],
        "preferred_workflows": ["W08"],
    },
    "devops_agent": {
        "skills": ["health_snapshot", "whitelisted_shell_execution", "backup_and_rollback_support", "operational_remediation"],
        "evidence": ["health", "checks", "backup_dir", "actions"],
        "preferred_workflows": ["W03"],
    },
    "self_healer": {
        "skills": ["failure_signature_detection", "verified_remediation_pipeline", "rollback_on_failed_fix", "quarantine_and_cooldown_control"],
        "evidence": ["method", "resolved", "remediation_candidates", "safe_action_suggestions"],
        "preferred_workflows": ["W03", "W08"],
    },
    "economics_agent": {
        "skills": ["price_band_selection", "margin_assumption_modeling", "competitor_anchor_fusion", "pricing_confidence_estimation"],
        "evidence": ["pricing_options", "market_signal_pack", "pricing_confidence"],
        "preferred_workflows": ["W01", "W06"],
    },
    "legal_agent": {
        "skills": ["platform_policy_pack_resolution", "copyright_risk_screening", "gdpr_checklist_generation", "publish_blocker_detection"],
        "evidence": ["policy_basis", "risk_score", "decision"],
        "preferred_workflows": ["W01", "W07"],
    },
}


def get_agent_skill_pack(agent_name: str) -> dict[str, Any]:
    name = str(agent_name or "").strip().lower()
    pack = _PACKS.get(name, {})
    return {
        "agent": name,
        "skills": list(pack.get("skills") or []),
        "evidence": list(pack.get("evidence") or []),
        "preferred_workflows": list(pack.get("preferred_workflows") or []),
    }
