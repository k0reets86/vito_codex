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


class AgentWorkflowRuntime:
    def __init__(self, registry):
        self.registry = registry

    async def run(self, workflow_id: str, seed_context: dict[str, Any] | None = None) -> dict[str, Any]:
        steps = WORKFLOW_SCENARIOS.get(str(workflow_id or "").strip())
        if not steps:
            return {"success": False, "error": "workflow_not_found", "workflow_id": workflow_id}
        ctx = dict(seed_context or {})
        results: list[dict[str, Any]] = []
        for step in steps:
            payload = dict(step.kwargs or {})
            payload.update({k: v for k, v in ctx.items() if k not in {"task_type", "handled_by", "error"}})
            result = await self.registry.dispatch(step.capability, **payload)
            row = {
                "capability": step.capability,
                "success": bool(result and result.success),
                "error": getattr(result, "error", None),
                "output": getattr(result, "output", None),
            }
            results.append(row)
            if result and result.success and isinstance(result.output, dict):
                ctx.update({k: v for k, v in result.output.items() if k not in {"error"}})
        return {
            "success": all(bool(r.get("success")) for r in results),
            "workflow_id": workflow_id,
            "steps": results,
            "events": self.registry.get_recent_agent_events(limit=200),
        }
