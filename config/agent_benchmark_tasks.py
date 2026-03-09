"""Fixed benchmark tasks for all 23 agents.

Phase F requires a deterministic benchmark map so HR/audit can measure agents as
operational units, not ad-hoc wrappers.
"""

from __future__ import annotations

AGENT_BENCHMARK_TASKS: dict[str, list[dict[str, str]]] = {
    "vito_core": [{"capability": "orchestrate", "task": "Route owner request into a verified workflow."}],
    "trend_scout": [{"capability": "trend_scan", "task": "Find three trend signals with source links."}],
    "content_creator": [{"capability": "product_turnkey", "task": "Build a turnkey listing content pack."}],
    "smm_agent": [{"capability": "social_media", "task": "Prepare one platform-native social post."}],
    "marketing_agent": [{"capability": "marketing_strategy", "task": "Generate a GTM plan with audience and offer angle."}],
    "ecommerce_agent": [{"capability": "listing_create", "task": "Create or update one listing package with proof."}],
    "seo_agent": [{"capability": "seo", "task": "Produce a keyword pack and SEO metadata."}],
    "email_agent": [{"capability": "email", "task": "Prepare a conversion-focused email draft."}],
    "translation_agent": [{"capability": "translate", "task": "Translate one listing variant preserving meaning."}],
    "analytics_agent": [{"capability": "analytics", "task": "Produce one analytics snapshot with summary."}],
    "economics_agent": [{"capability": "pricing", "task": "Recommend a price point with margin logic."}],
    "legal_agent": [{"capability": "legal", "task": "Review one product for policy/copyright risk."}],
    "risk_agent": [{"capability": "risk_assessment", "task": "Assess risk level with explicit factors."}],
    "security_agent": [{"capability": "security", "task": "Run one security/policy compliance check."}],
    "devops_agent": [{"capability": "health_check", "task": "Return runtime health report and remediation."}],
    "hr_agent": [{"capability": "agent_development", "task": "Audit agent capability gaps and actions."}],
    "partnership_agent": [{"capability": "partnership", "task": "Build a shortlist of partner candidates."}],
    "research_agent": [{"capability": "research", "task": "Run deep research and return scored findings."}],
    "document_agent": [{"capability": "documentation", "task": "Extract and summarize source material."}],
    "account_manager": [{"capability": "account_management", "task": "Return account/auth state for one platform."}],
    "browser_agent": [{"capability": "browse", "task": "Navigate a page and capture verified browser evidence."}],
    "publisher_agent": [{"capability": "publish", "task": "Publish content and return platform evidence."}],
    "quality_judge": [{"capability": "quality_review", "task": "Score output and provide revision feedback."}],
}

