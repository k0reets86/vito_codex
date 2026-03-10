from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    capability: str
    kwargs: dict[str, Any]


WORKFLOW_SCENARIOS: dict[str, list[WorkflowStep]] = {
    "W01_digital_product_sales": [
        WorkflowStep("trend_scan", {"keywords": ["digital products", "ai tools"]}),
        WorkflowStep("research", {"topic": "digital product niche"}),
        WorkflowStep("pricing_strategy", {"product_type": "digital_product"}),
        WorkflowStep("legal", {"action": "check_tos", "platform": "gumroad"}),
        WorkflowStep("content_creation", {"topic": "digital product niche"}),
        WorkflowStep("quality_review", {"content_type": "listing"}),
        WorkflowStep("listing_seo_pack", {"platform": "gumroad"}),
        WorkflowStep("translate", {"text": "listing pack", "target_lang": "de"}),
        WorkflowStep("listing_create", {"platform": "gumroad"}),
        WorkflowStep("campaign_plan", {"platform": "twitter"}),
        WorkflowStep("analytics", {"metric": "sales_snapshot"}),
    ],
    "W02_content_publication": [
        WorkflowStep("trend_scan", {"keywords": ["automation", "content"]}),
        WorkflowStep("listing_seo_pack", {"platform": "wordpress"}),
        WorkflowStep("content_creation", {"topic": "automation article"}),
        WorkflowStep("quality_review", {"content_type": "article"}),
        WorkflowStep("translate", {"text": "article", "target_lang": "de"}),
        WorkflowStep("publish", {"platform": "wordpress"}),
        WorkflowStep("campaign_plan", {"platform": "twitter"}),
        WorkflowStep("email", {"action": "newsletter"}),
        WorkflowStep("analytics", {"metric": "content_views"}),
    ],
    "W03_monitoring_self_heal": [
        WorkflowStep("monitoring", {"scope": "runtime"}),
        WorkflowStep("analytics", {"metric": "error_rate"}),
        WorkflowStep("self_heal", {"issue": "runtime_anomaly"}),
        WorkflowStep("security", {"action": "scan_runtime"}),
        WorkflowStep("monitoring", {"scope": "post_fix"}),
    ],
    "W04_account_auth": [
        WorkflowStep("auth", {"platform": "amazon"}),
        WorkflowStep("browse", {"url": "https://www.amazon.com/ap/signin"}),
        WorkflowStep("auth", {"platform": "etsy"}),
        WorkflowStep("browse", {"url": "https://www.etsy.com/your/shops/me/tools/listings"}),
    ],
    "W05_social_launch": [
        WorkflowStep("marketing_strategy", {"product": "launch asset"}),
        WorkflowStep("campaign_plan", {"platform": "twitter"}),
        WorkflowStep("campaign_plan", {"platform": "pinterest"}),
        WorkflowStep("publish", {"platform": "twitter"}),
        WorkflowStep("publish", {"platform": "pinterest"}),
    ],
    "W06_analytics_response": [
        WorkflowStep("analytics", {"metric": "conversion_drop"}),
        WorkflowStep("pricing_strategy", {"product_type": "digital_product"}),
        WorkflowStep("listing_update", {"platform": "gumroad"}),
        WorkflowStep("campaign_plan", {"platform": "twitter"}),
    ],
    "W07_compliance_risk_gating": [
        WorkflowStep("legal", {"action": "check_tos", "platform": "etsy"}),
        WorkflowStep("risk", {"action": "moderation_risk", "platform": "reddit"}),
        WorkflowStep("security", {"action": "key_validation"}),
        WorkflowStep("quality_review", {"content_type": "listing"}),
    ],
    "W08_skill_growth_self_upgrade": [
        WorkflowStep("research", {"topic": "missing capability"}),
        WorkflowStep("knowledge_ingest", {"source": "platform_docs"}),
        WorkflowStep("agent_development", {"target": "weak_agent"}),
        WorkflowStep("self_heal", {"issue": "regression"}),
    ],
}


WORKFLOW_COLLAB_ASSERTIONS: dict[str, dict[str, list[str]]] = {
    "W01_digital_product_sales": {
        "required_agents": ["trend_scout", "research_agent", "economics_agent", "legal_agent", "content_creator", "quality_judge", "seo_agent", "ecommerce_agent", "smm_agent"],
        "required_verify_agents": ["quality_judge"],
    },
    "W02_content_publication": {
        "required_agents": ["trend_scout", "seo_agent", "content_creator", "quality_judge", "publisher_agent", "smm_agent", "email_agent"],
        "required_verify_agents": ["quality_judge"],
    },
    "W03_monitoring_self_heal": {
        "required_agents": ["devops_agent", "analytics_agent", "self_healer", "security_agent"],
        "required_verify_agents": [],
    },
    "W04_account_auth": {
        "required_agents": ["account_manager", "browser_agent"],
        "required_verify_agents": [],
    },
    "W05_social_launch": {
        "required_agents": ["marketing_agent", "smm_agent", "publisher_agent"],
        "required_verify_agents": [],
    },
    "W06_analytics_response": {
        "required_agents": ["analytics_agent", "economics_agent", "ecommerce_agent", "smm_agent"],
        "required_verify_agents": [],
    },
    "W07_compliance_risk_gating": {
        "required_agents": ["legal_agent", "risk_agent", "security_agent", "quality_judge"],
        "required_verify_agents": ["quality_judge"],
    },
    "W08_skill_growth_self_upgrade": {
        "required_agents": ["research_agent", "document_agent", "hr_agent", "self_healer"],
        "required_verify_agents": [],
    },
}


class AgentWorkflowRuntime:
    def __init__(self, registry):
        self.registry = registry

    async def run(self, workflow_id: str, seed_context: dict[str, Any] | None = None) -> dict[str, Any]:
        steps = WORKFLOW_SCENARIOS.get(str(workflow_id or "").strip())
        if not steps:
            return {"success": False, "error": "workflow_not_found", "workflow_id": workflow_id}
        ctx = dict(seed_context or {})
        results: list[dict[str, Any]] = []
        observed_agents: set[str] = set()
        for step in steps:
            payload = dict(step.kwargs or {})
            payload.update({k: v for k, v in ctx.items() if k not in {"task_type", "handled_by", "error"}})
            result = await self.registry.dispatch(step.capability, **payload)
            handled_by = ""
            if result and isinstance(getattr(result, "output", None), dict):
                handled_by = str((result.output or {}).get("handled_by") or "").strip()
            if not handled_by and result and isinstance(getattr(result, "metadata", None), dict):
                md = result.metadata or {}
                handled_by = str(
                    md.get("responsible_agent")
                    or md.get("agent")
                    or ""
                ).strip()
            if not handled_by:
                candidates = list(self.registry.find_by_capability(step.capability) or [])
                if len(candidates) == 1:
                    handled_by = str(getattr(candidates[0], "name", "") or "").strip()
            if handled_by:
                observed_agents.add(handled_by)
            row = {
                "capability": step.capability,
                "success": bool(result and result.success),
                "error": getattr(result, "error", None),
                "output": getattr(result, "output", None),
                "handled_by": handled_by,
            }
            results.append(row)
            if result and result.success and isinstance(result.output, dict):
                ctx.update({k: v for k, v in result.output.items() if k not in {"error"}})
                if result.output.get("handled_by"):
                    observed_agents.add(str(result.output.get("handled_by")).strip())
        collab = WORKFLOW_COLLAB_ASSERTIONS.get(str(workflow_id or "").strip(), {})
        required = [str(x).strip() for x in (collab.get("required_agents") or []) if str(x).strip()]
        required_verify = [str(x).strip() for x in (collab.get("required_verify_agents") or []) if str(x).strip()]
        missing_agents = [name for name in required if name not in observed_agents]
        missing_verify = [name for name in required_verify if name not in observed_agents]
        degraded = bool(missing_agents or missing_verify)
        return {
            "success": all(bool(r.get("success")) for r in results) and not degraded,
            "workflow_id": workflow_id,
            "steps": results,
            "collaboration_assertions": {
                "required_agents": required,
                "required_verify_agents": required_verify,
                "observed_agents": sorted(observed_agents),
                "missing_agents": missing_agents,
                "missing_verify_agents": missing_verify,
                "degraded": degraded,
            },
            "events": self.registry.get_recent_agent_events(limit=200),
        }
