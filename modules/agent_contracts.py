"""Единый контрактный слой для всех 23 агентов VITO.

Контракт нужен не для описательной витрины, а как operational source of truth:
- кто за что отвечает
- какой результат считается завершённым
- какие доказательства обязательны
- с кем агент должен координироваться
- какие типы памяти он читает и пишет
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VALID_SKILL_KINDS = {"service", "helper", "persona", "recipe"}

_BASE_CONTRACT: dict[str, Any] = {
    "role": "specialist",
    "primary_kind": "service",
    "owned_outcomes": [],
    "required_evidence": ["status"],
    "runtime_enforced": False,
    "tool_scopes": [],
    "collaborates_with": [],
    "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory"],
    "memory_outputs": ["execution_facts", "skill_lessons"],
    "escalation_rules": ["escalate_on_policy_conflict", "escalate_on_missing_evidence"],
    "workflow_roles": {
        "lead": [],
        "support": [],
        "verify": [],
    },
}

_CONTRACTS: dict[str, dict[str, Any]] = {
    "vito_core": {
        "role": "owner_orchestrator_manager",
        "primary_kind": "persona",
        "owned_outcomes": ["task_routing", "workflow_state", "agent_handoff", "owner_response"],
        "required_evidence": ["workflow_status", "responsible_agent", "verification_state"],
        "runtime_enforced": True,
        "tool_scopes": ["registry", "memory", "workflow_state_machine", "llm_router"],
        "collaborates_with": ["quality_judge", "hr_agent", "devops_agent", "ecommerce_agent", "publisher_agent", "browser_agent", "account_manager"],
        "memory_inputs": ["owner_memory", "workflow_memory", "skill_memory", "anti_pattern_memory"],
        "memory_outputs": ["workflow_facts", "owner_context_updates", "routing_lessons", "orchestration_recovery_notes", "final_decision_records"],
        "escalation_rules": ["escalate_on_policy_conflict", "escalate_on_missing_evidence", "escalate_on_workflow_degradation"],
        "workflow_roles": {
            "lead": ["research_pipeline", "publish_pipeline", "self_improvement_pipeline"],
            "support": ["all"],
            "verify": [],
        },
    },
    "trend_scout": {
        "role": "trend_discovery_operator",
        "owned_outcomes": ["trend_scan_report", "niche_candidates", "source_shortlist"],
        "required_evidence": ["source_urls", "trend_summary", "signal_score"],
        "runtime_enforced": True,
        "tool_scopes": ["browser_read", "search", "feeds", "pytrends", "rss_registry", "trend_runtime_profile", "source_matrix_builder", "signal_ranking_rules", "distribution_seed_rules"],
        "collaborates_with": ["research_agent", "seo_agent", "marketing_agent", "analytics_agent", "quality_judge", "vito_core", "devops_agent"],
        "memory_inputs": ["trend_runtime_profiles", "market_signals", "owner_preferences", "anti_pattern_memory"],
        "memory_outputs": ["market_signals", "trend_lessons", "fallback_signal_notes", "trend_recovery_patterns", "signal_conflict_notes"],
        "escalation_rules": ["escalate_on_source_drought", "escalate_on_only_fallback_sources", "escalate_on_conflicting_signal_direction"],
        "workflow_roles": {"lead": ["trend_pipeline"], "support": ["research_pipeline", "marketing_pipeline", "growth_pipeline", "seo_pipeline", "social_publish_pipeline"], "verify": ["quality_judge", "vito_core", "analytics_pipeline"]},
    },
    "content_creator": {
        "role": "content_pack_operator",
        "owned_outcomes": ["product_copy", "article_draft", "ebook_draft", "asset_manifest"],
        "required_evidence": ["title", "body", "asset_paths"],
        "runtime_enforced": True,
        "tool_scopes": ["llm_router", "file_generation", "template_assets", "content_runtime_profile", "listing_optimizer", "asset_manifest_builder", "preview_gallery_builder", "quality_self_check"],
        "collaborates_with": ["seo_agent", "quality_judge", "marketing_agent", "smm_agent", "ecommerce_agent", "publisher_agent", "vito_core", "devops_agent"],
        "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory", "content_patterns", "asset_recipes"],
        "memory_outputs": ["content_patterns", "asset_recipes", "content_recovery_patterns", "platform_fit_notes", "asset_generation_lessons"],
        "escalation_rules": ["escalate_on_missing_assets", "escalate_on_quality_reject", "escalate_on_platform_fit_conflict"],
        "workflow_roles": {"lead": ["content_pipeline"], "support": ["publish_pipeline", "launch_pipeline", "growth_pipeline", "seo_pipeline", "email_pipeline"], "verify": ["quality_judge", "vito_core", "marketing_pipeline"]},
    },
    "smm_agent": {
        "role": "social_operator",
        "owned_outcomes": ["campaign_plan", "platform_posts", "social_queue"],
        "required_evidence": ["platform", "post_url_or_status", "content_variant"],
        "tool_scopes": ["social_platforms", "browser_posting", "scheduler", "social_runbooks", "platform_rules", "growth_runtime_profile"],
        "collaborates_with": ["marketing_agent", "content_creator", "publisher_agent", "quality_judge", "analytics_agent", "seo_agent", "vito_core"],
        "memory_inputs": ["owner_preferences", "social_runbooks", "platform_rules", "campaign_results", "platform_format_lessons"],
        "memory_outputs": ["campaign_results", "platform_format_lessons", "engagement_notes", "moderation_outcomes"],
        "escalation_rules": ["escalate_on_moderation_reject", "escalate_on_auth_blocker", "escalate_on_low_confidence_copy"],
        "workflow_roles": {"lead": ["social_publish_pipeline"], "support": ["launch_pipeline", "growth_pipeline"], "verify": ["quality_judge"]},
    },
    "marketing_agent": {
        "role": "go_to_market_manager",
        "owned_outcomes": ["marketing_strategy", "funnel_plan", "positioning"],
        "required_evidence": ["strategy_summary", "target_audience", "offer_angle"],
        "runtime_enforced": True,
        "tool_scopes": ["llm_router", "analytics_inputs", "research_inputs", "budget_profiles", "channel_mix_rules", "growth_runtime_profile", "experiment_matrix_builder", "positioning_risk_rules", "audience_hypothesis_map"],
        "collaborates_with": ["trend_scout", "research_agent", "smm_agent", "seo_agent", "analytics_agent", "quality_judge", "vito_core", "devops_agent"],
        "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory", "offer_playbooks", "positioning_lessons"],
        "memory_outputs": ["offer_playbooks", "positioning_lessons", "channel_mix_patterns", "budget_fit_rules", "strategy_recovery_notes", "creative_test_matrixes", "audience_validation_rules"],
        "escalation_rules": ["escalate_on_unclear_audience", "escalate_on_no_budget_fit", "escalate_on_strategy_conflict"],
        "workflow_roles": {"lead": ["marketing_pipeline"], "support": ["publish_pipeline", "growth_pipeline", "launch_pipeline", "email_pipeline", "social_publish_pipeline"], "verify": ["quality_judge", "vito_core", "analytics_pipeline"]},
    },
    "ecommerce_agent": {
        "role": "listing_owner_operator",
        "owned_outcomes": ["listing_package", "listing_publish", "platform_rules_sync"],
        "required_evidence": ["platform_status", "listing_id_or_url", "artifact_manifest"],
        "runtime_enforced": True,
        "tool_scopes": ["commerce_platforms", "artifact_pack", "browser_publish", "platform_runbook_pack", "final_verifier"],
        "collaborates_with": ["content_creator", "seo_agent", "marketing_agent", "smm_agent", "quality_judge", "publisher_agent", "vito_core"],
        "memory_outputs": ["platform_runbooks", "listing_recipes", "platform_constraints", "listing_runtime_profiles", "publish_recovery_notes"],
        "escalation_rules": ["escalate_on_policy_conflict", "escalate_on_missing_evidence", "escalate_on_verifier_reject"],
        "workflow_roles": {"lead": ["publish_pipeline", "listing_update_pipeline"], "support": ["launch_pipeline"], "verify": ["quality_judge"]},
    },
    "seo_agent": {
        "role": "seo_operator",
        "owned_outcomes": ["keyword_pack", "seo_listing_pack", "metadata_rewrite"],
        "required_evidence": ["keywords", "seo_title", "seo_description", "seo_score"],
        "tool_scopes": ["llm_router", "search", "keyword_tools", "listing_optimizer", "platform_rules", "growth_runtime_profile"],
        "collaborates_with": ["content_creator", "research_agent", "marketing_agent", "ecommerce_agent", "quality_judge", "analytics_agent", "smm_agent"],
        "memory_inputs": ["seo_patterns", "keyword_clusters", "owner_preferences", "platform_rules", "research_artifacts"],
        "memory_outputs": ["seo_patterns", "keyword_clusters", "listing_seo_packs", "serp_lessons"],
        "escalation_rules": ["escalate_on_keyword_conflict", "escalate_on_low_seo_score", "escalate_on_platform_rule_conflict"],
        "workflow_roles": {"lead": ["seo_pipeline"], "support": ["publish_pipeline", "optimization_pipeline"], "verify": ["quality_judge"]},
    },
    "email_agent": {
        "role": "email_operator",
        "owned_outcomes": ["email_message", "newsletter_draft", "email_send"],
        "required_evidence": ["subject", "body", "recipient_scope"],
        "runtime_enforced": True,
        "tool_scopes": ["gmail", "newsletter_tools", "templates", "send_checklists", "email_runtime_profile", "deliverability_rules", "audience_segment_rules", "sequence_gap_checks"],
        "collaborates_with": ["content_creator", "marketing_agent", "account_manager", "analytics_agent", "quality_judge", "vito_core", "devops_agent"],
        "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory", "email_templates", "sequence_patterns"],
        "memory_outputs": ["email_templates", "engagement_lessons", "sequence_patterns", "deliverability_notes", "email_recovery_patterns", "send_window_rules", "subject_line_tests"],
        "escalation_rules": ["escalate_on_missing_audience", "escalate_on_send_blocker", "escalate_on_sequence_gap"],
        "workflow_roles": {"lead": ["email_pipeline"], "support": ["launch_pipeline", "retention_pipeline", "growth_pipeline", "marketing_pipeline"], "verify": ["quality_judge", "vito_core", "analytics_pipeline"]},
    },
    "translation_agent": {
        "role": "language_adapter",
        "primary_kind": "helper",
        "owned_outcomes": ["translation", "localization_variant", "translation_validation_pack", "locale_consistency_decision"],
        "required_evidence": ["source_lang", "target_lang", "translated_text", "quality_checks", "locale_profile", "provider_route"],
        "runtime_enforced": True,
        "tool_scopes": ["llm_router", "glossary_memory", "locale_rules", "translation_cache", "quality_checks", "translation_runtime_profile", "terminology_guard", "localization_validator", "fallback_route_selector"],
        "collaborates_with": ["content_creator", "smm_agent", "publisher_agent", "quality_judge", "vito_core", "seo_agent", "marketing_agent"],
        "memory_outputs": ["localization_lessons", "translation_cache_entries", "glossary_terms", "localization_consistency_notes", "translation_validation_packs", "locale_recovery_patterns"],
        "escalation_rules": ["escalate_on_term_conflict", "escalate_on_locale_mismatch", "escalate_on_translation_uncertainty", "escalate_on_consistency_check_fail", "escalate_on_script_mismatch"],
        "workflow_roles": {"lead": [], "support": ["content_pipeline", "publish_pipeline", "growth_pipeline"], "verify": ["quality_judge"]},
    },
    "analytics_agent": {
        "role": "performance_analyst",
        "owned_outcomes": ["analytics_snapshot", "forecast", "dashboard_metrics", "anomaly_investigation_pack", "benchmark_review"],
        "required_evidence": ["metric_table", "timeframe", "summary", "analytics_runtime_profile", "investigation_plan"],
        "runtime_enforced": True,
        "tool_scopes": ["analytics_sources", "dashboard", "forecasting", "anomaly_triage", "agent_runtime_scores", "baseline_store", "trend_delta_checks", "alert_router", "evidence_normalizer"],
        "collaborates_with": ["marketing_agent", "economics_agent", "smm_agent", "hr_agent", "quality_judge", "vito_core", "devops_agent", "research_agent"],
        "memory_inputs": ["performance_baselines", "campaign_results", "forecast_lessons", "anomaly_signatures"],
        "memory_outputs": ["performance_baselines", "forecast_lessons", "anomaly_signatures", "optimization_recommendations", "benchmark_snapshots", "investigation_playbooks"],
        "escalation_rules": ["escalate_on_anomaly_cluster", "escalate_on_negative_margin_pattern", "escalate_on_low_confidence_forecast", "escalate_on_missing_baseline", "escalate_on_benchmark_regression"],
        "workflow_roles": {"lead": ["analytics_pipeline"], "support": ["optimization_pipeline", "research_pipeline"], "verify": ["quality_judge", "vito_core"]},
    },
    "economics_agent": {
        "role": "pricing_helper",
        "primary_kind": "helper",
        "owned_outcomes": ["price_recommendation", "unit_economics_snapshot", "pricing_validation_pack", "pnl_projection"],
        "required_evidence": ["price_point", "margin_logic", "assumptions", "market_signal_pack", "pricing_confidence", "recommendation_rationale"],
        "runtime_enforced": True,
        "tool_scopes": ["pricing_models", "analytics_inputs", "market_signal_pack", "competitor_anchor_bands", "margin_assumption_tables", "scenario_simulator", "profitability_guard", "pricing_validator", "anchor_confidence_router"],
        "collaborates_with": ["analytics_agent", "marketing_agent", "ecommerce_agent", "research_agent", "quality_judge", "publisher_agent", "vito_core"],
        "memory_outputs": ["pricing_rules", "market_signal_notes", "price_anchor_memory", "margin_assumption_memory", "pricing_validation_packs", "pricing_recovery_patterns"],
        "escalation_rules": ["escalate_on_missing_market_signal", "escalate_on_margin_uncertainty", "escalate_on_no_price_anchor", "escalate_on_negative_unit_economics", "escalate_on_conflicting_anchor_signals"],
        "workflow_roles": {"lead": [], "support": ["publish_pipeline", "optimization_pipeline", "analytics_pipeline"], "verify": ["quality_judge"]},
    },
    "legal_agent": {
        "role": "policy_guard",
        "primary_kind": "helper",
        "owned_outcomes": ["legal_review", "policy_notes", "copyright_flags"],
        "required_evidence": ["risk_summary", "policy_basis"],
        "tool_scopes": ["llm_router", "policy_docs", "platform_policy_packs", "copyright_checks", "compliance_basis"],
        "collaborates_with": ["risk_agent", "security_agent", "publisher_agent", "quality_judge", "vito_core", "account_manager"],
        "memory_inputs": ["platform_rules", "policy_constraints", "owner_requirements", "publish_history"],
        "memory_outputs": ["policy_constraints", "legal_lessons", "policy_basis_records", "blocked_policy_patterns", "review_decisions"],
        "escalation_rules": ["escalate_on_policy_basis_missing", "escalate_on_publish_blocker", "escalate_on_copyright_ambiguity"],
        "workflow_roles": {"lead": [], "support": ["publish_pipeline", "platform_compliance_pipeline"], "verify": ["quality_judge"]},
    },
    "risk_agent": {
        "role": "risk_guard",
        "primary_kind": "helper",
        "owned_outcomes": ["risk_assessment", "reputation_flags"],
        "required_evidence": ["risk_level", "risk_factors"],
        "tool_scopes": ["llm_router", "policy_checks", "reputation_inputs", "growth_runtime_profile", "block_recommendation_rules"],
        "collaborates_with": ["legal_agent", "security_agent", "quality_judge", "vito_core", "publisher_agent"],
        "memory_inputs": ["risk_patterns", "anti_patterns", "platform_rules", "publish_history"],
        "memory_outputs": ["risk_patterns", "anti_patterns", "block_decision_memory", "risk_signatures"],
        "escalation_rules": ["escalate_on_high_risk", "escalate_on_anti_abuse_risk", "escalate_on_reputation_spike"],
        "workflow_roles": {"lead": ["risk_pipeline"], "support": ["publish_pipeline"], "verify": ["quality_judge"]},
    },
    "security_agent": {
        "role": "security_guard",
        "primary_kind": "helper",
        "owned_outcomes": ["security_check", "key_rotation_plan", "policy_enforcement"],
        "required_evidence": ["security_state", "policy_decision"],
        "tool_scopes": ["security_policies", "secrets_health", "tooling_policies", "audit_rules", "ops_runtime_profile"],
        "collaborates_with": ["risk_agent", "devops_agent", "vito_core", "quality_judge", "account_manager"],
        "memory_inputs": ["security_lessons", "blocked_patterns", "owner_requirements", "incident_memory"],
        "memory_outputs": ["security_lessons", "blocked_patterns", "audit_findings", "remediation_history"],
        "escalation_rules": ["escalate_on_missing_secrets", "escalate_on_runtime_exposure", "escalate_on_policy_violation"],
        "workflow_roles": {"lead": ["security_pipeline"], "support": ["tooling_pipeline", "runtime_maintenance_pipeline"], "verify": ["quality_judge"]},
    },
    "devops_agent": {
        "role": "runtime_operator",
        "primary_kind": "helper",
        "owned_outcomes": ["health_report", "backup_result", "runtime_fix", "repair_verification_pack"],
        "required_evidence": ["status", "logs_or_paths", "recovery_hints", "devops_runtime_profile"],
        "runtime_enforced": True,
        "tool_scopes": ["shell", "health_checks", "backup_tools", "runtime_remediation", "ops_runtime_profile", "repair_verifier", "incident_classifier", "rollback_guides"],
        "collaborates_with": ["security_agent", "hr_agent", "vito_core", "self_healer", "quality_judge", "analytics_agent", "browser_agent"],
        "memory_inputs": ["ops_runbooks", "incident_lessons", "failure_memory", "tooling_governance"],
        "memory_outputs": ["ops_runbooks", "incident_lessons", "repair_journal", "runtime_fix_history", "ops_recovery_patterns", "incident_signatures"],
        "escalation_rules": ["escalate_on_repeat_failure", "escalate_on_unsafe_command", "escalate_on_backup_gap", "escalate_on_missing_repair_evidence", "escalate_on_nonrecoverable_runtime_state"],
        "workflow_roles": {"lead": ["runtime_maintenance_pipeline"], "support": ["self_healing_pipeline", "analytics_pipeline"], "verify": ["quality_judge", "vito_core"]},
    },
    "hr_agent": {
        "role": "agent_development_manager",
        "owned_outcomes": ["agent_audit", "development_plan", "knowledge_gap_report"],
        "required_evidence": ["rankings", "gaps", "recommended_actions"],
        "tool_scopes": ["registry", "memory", "llm_router", "agent_benchmark_matrix", "agent_runtime_verifier"],
        "collaborates_with": ["vito_core", "quality_judge", "devops_agent", "self_evolver"],
        "memory_inputs": ["agent_improvement_plans", "capability_gaps", "benchmark_history"],
        "memory_outputs": ["agent_improvement_plans", "capability_gaps", "benchmark_history", "owner_feedback_memory"],
        "escalation_rules": ["escalate_on_regression_cluster", "escalate_on_benchmark_drop", "escalate_on_skill_gap_persistence"],
        "workflow_roles": {"lead": ["agent_improvement_pipeline"], "support": ["self_learning_pipeline"], "verify": ["quality_judge"]},
    },
    "partnership_agent": {
        "role": "partner_ops",
        "owned_outcomes": ["partnership_shortlist", "affiliate_plan", "partner_scorecard", "outreach_execution_pack"],
        "required_evidence": ["candidate_list", "fit_reasoning", "runtime_candidates", "outreach_plan"],
        "runtime_enforced": True,
        "tool_scopes": ["research", "crm_notes", "outreach_templates", "partner_scoring_rules", "growth_runtime_profile", "outreach_validator", "crm_memory", "offer_matcher", "partner_fit_router"],
        "collaborates_with": ["marketing_agent", "email_agent", "research_agent", "quality_judge", "analytics_agent", "content_creator", "vito_core"],
        "memory_inputs": ["partner_playbooks", "partner_fit_scores", "outreach_learning", "owner_preferences"],
        "memory_outputs": ["partner_playbooks", "partner_fit_scores", "outreach_learning", "deal_outcomes", "partner_recovery_patterns", "outreach_sequences"],
        "escalation_rules": ["escalate_on_low_fit_pool", "escalate_on_missing_partner_data", "escalate_on_outreach_blocker", "escalate_on_weak_partner_score", "escalate_on_missing_offer_match"],
        "workflow_roles": {"lead": ["partnership_pipeline"], "support": ["growth_pipeline", "email_pipeline"], "verify": ["quality_judge", "analytics_pipeline"]},
    },
    "research_agent": {
        "role": "deep_research_operator",
        "owned_outcomes": ["research_report", "competitor_matrix", "market_analysis"],
        "required_evidence": ["sources", "findings", "comparisons"],
        "runtime_enforced": True,
        "tool_scopes": ["browser_read", "search", "url_context", "research_cache", "judge_pipeline", "report_store", "source_coverage_runtime", "source_mix_expansion", "gap_triage_rules", "evidence_digest_builder"],
        "collaborates_with": ["trend_scout", "seo_agent", "marketing_agent", "document_agent", "analytics_agent", "quality_judge", "vito_core", "devops_agent"],
        "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory", "research_findings", "source_quality_lessons"],
        "memory_outputs": ["research_findings", "source_quality_lessons", "research_gap_signatures", "research_recovery_patterns", "source_mix_notes", "source_coverage_maps", "operator_research_briefs"],
        "escalation_rules": ["escalate_on_gap_count", "escalate_on_weak_source_mix", "escalate_on_judge_reject"],
        "workflow_roles": {"lead": ["research_pipeline"], "support": ["strategy_pipeline", "trend_pipeline", "marketing_pipeline", "seo_pipeline"], "verify": ["quality_judge", "vito_core", "analytics_pipeline"]},
    },
    "document_agent": {
        "role": "knowledge_ingest_operator",
        "primary_kind": "helper",
        "owned_outcomes": ["doc_parse", "ocr_extract", "knowledge_base_update"],
        "required_evidence": ["source_path_or_url", "extracted_summary"],
        "runtime_enforced": True,
        "tool_scopes": ["document_parsers", "ocr", "video_extract", "source_existence_checks", "document_runtime_profile", "extract_review_checklists", "manifest_builder", "source_integrity_rules"],
        "collaborates_with": ["research_agent", "vito_core", "hr_agent", "quality_judge", "devops_agent", "security_agent"],
        "memory_inputs": ["owner_memory", "skill_memory", "anti_pattern_memory", "knowledge_blocks", "document_lessons"],
        "memory_outputs": ["knowledge_blocks", "document_lessons", "document_recovery_patterns", "extract_quality_notes", "source_integrity_notes", "parser_switch_rules", "documentation_templates"],
        "escalation_rules": ["escalate_on_unsupported_format", "escalate_on_missing_source_file", "escalate_on_ocr_unavailable"],
        "workflow_roles": {"lead": ["knowledge_ingest_pipeline"], "support": ["research_pipeline", "agent_improvement_pipeline", "content_pipeline", "runtime_maintenance_pipeline"], "verify": ["quality_judge", "vito_core", "security_pipeline"]},
    },
    "account_manager": {
        "role": "account_auth_operator",
        "owned_outcomes": ["account_status", "email_code_fetch", "session_support"],
        "required_evidence": ["account", "auth_state"],
        "runtime_enforced": True,
        "tool_scopes": ["mailbox", "auth_session_state", "auth_remediation_packs", "otp_flows", "profile_completion_runbooks"],
        "collaborates_with": ["browser_agent", "ecommerce_agent", "smm_agent", "quality_judge", "vito_core"],
        "memory_outputs": ["auth_runbooks", "session_notes", "auth_blockers", "profile_completion_notes"],
        "escalation_rules": ["escalate_on_otp_required", "escalate_on_session_expired", "escalate_on_cloudflare_gate"],
        "workflow_roles": {"lead": ["auth_pipeline"], "support": ["publish_pipeline"], "verify": []},
    },
    "browser_agent": {
        "role": "browser_executor",
        "primary_kind": "helper",
        "owned_outcomes": ["page_navigation", "form_submission", "browser_evidence"],
        "required_evidence": ["page_url", "dom_signal", "screenshot_or_trace"],
        "runtime_enforced": True,
        "tool_scopes": ["playwright", "browser_profile", "cookie_sessions", "selector_mapping", "challenge_solver", "profile_completion_runbooks"],
        "collaborates_with": ["account_manager", "research_agent", "ecommerce_agent", "smm_agent", "quality_judge", "vito_core"],
        "memory_outputs": ["browser_runbooks", "anti_bot_lessons", "selector_map_notes", "auth_interrupt_notes"],
        "escalation_rules": ["escalate_on_auth_interrupt", "escalate_on_challenge_detected", "escalate_on_profile_completion_required"],
        "workflow_roles": {"lead": ["browser_execution_pipeline"], "support": ["auth_pipeline", "publish_pipeline"], "verify": []},
    },
    "publisher_agent": {
        "role": "editorial_publisher_operator",
        "owned_outcomes": ["article_publish", "cms_publish", "content_distribution"],
        "required_evidence": ["platform_status", "published_url_or_status"],
        "runtime_enforced": True,
        "tool_scopes": ["cms_platforms", "preview_generation", "approval_flow", "publisher_runtime_profile", "publish_retry_rules"],
        "collaborates_with": ["content_creator", "seo_agent", "quality_judge", "translation_agent", "vito_core", "devops_agent"],
        "memory_outputs": ["publishing_runbooks", "editorial_patterns", "publish_recovery_notes", "evidence_patterns", "distribution_lessons"],
        "escalation_rules": ["escalate_on_policy_conflict", "escalate_on_missing_evidence", "escalate_on_publish_platform_unavailable"],
        "workflow_roles": {"lead": ["editorial_publish_pipeline"], "support": ["launch_pipeline"], "verify": ["quality_judge"]},
    },
    "quality_judge": {
        "role": "quality_guard",
        "primary_kind": "persona",
        "owned_outcomes": ["approval_decision", "quality_score", "revision_feedback"],
        "required_evidence": ["score", "approved", "feedback"],
        "runtime_enforced": True,
        "tool_scopes": ["llm_router", "quality_policies", "agent_runtime_verifier", "quality_runtime_profile", "platform_rules", "evidence_contracts"],
        "collaborates_with": ["vito_core", "content_creator", "ecommerce_agent", "publisher_agent", "risk_agent", "legal_agent", "security_agent"],
        "memory_inputs": ["quality_patterns", "rejection_reasons", "platform_rules", "owner_requirements"],
        "memory_outputs": ["quality_patterns", "rejection_reasons", "repair_recommendations", "quality_score_history"],
        "escalation_rules": ["escalate_on_threshold_failure", "escalate_on_missing_evidence", "escalate_on_policy_conflict"],
        "workflow_roles": {"lead": ["quality_gate_pipeline"], "support": ["all"], "verify": ["all", "vito_core"]},
    },
}


def get_agent_contract(agent_name: str, capabilities: list[str] | None = None, description: str = "") -> dict[str, Any]:
    name = str(agent_name or "").strip().lower()
    contract = deepcopy(_BASE_CONTRACT)
    contract.update(deepcopy(_CONTRACTS.get(name, {})))
    caps = [str(c).strip() for c in (capabilities or []) if str(c).strip()]
    contract["agent"] = name
    contract["description"] = str(description or "").strip()
    contract["capabilities"] = caps
    contract["service"] = caps
    contract["helper"] = [c for c in caps if contract.get("primary_kind") == "helper"]
    contract["persona"] = [f"persona.{name}"]
    recipes = []
    for recipe_name, leaders in (contract.get("workflow_roles") or {}).items():
        if recipe_name == "verify":
            continue
        if isinstance(leaders, list) and leaders:
            role_prefix = "recipe."
            for leader in leaders:
                if leader == "all":
                    continue
                recipes.append(f"{role_prefix}{leader}")
    if not recipes:
        recipes = [f"recipe.{name}.default"]
    contract["recipe"] = sorted(set(recipes))
    return contract


def list_agent_contracts() -> dict[str, dict[str, Any]]:
    return {name: get_agent_contract(name) for name in sorted(_CONTRACTS)}


def validate_agent_contract(contract: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return False, ["contract_not_dict"]
    if not str(contract.get("agent", "")).strip():
        errors.append("agent_missing")
    if str(contract.get("primary_kind", "")).strip().lower() not in VALID_SKILL_KINDS:
        errors.append("primary_kind_invalid")
    if not isinstance(contract.get("runtime_enforced", False), bool):
        errors.append("runtime_enforced_not_bool")
    for key in (
        "owned_outcomes",
        "required_evidence",
        "tool_scopes",
        "collaborates_with",
        "memory_inputs",
        "memory_outputs",
        "escalation_rules",
        "service",
        "helper",
        "persona",
        "recipe",
    ):
        if not isinstance(contract.get(key), list):
            errors.append(f"{key}_not_list")
    workflow_roles = contract.get("workflow_roles")
    if not isinstance(workflow_roles, dict):
        errors.append("workflow_roles_not_dict")
    else:
        for key in ("lead", "support", "verify"):
            if not isinstance(workflow_roles.get(key), list):
                errors.append(f"workflow_roles_{key}_not_list")
    return len(errors) == 0, errors
