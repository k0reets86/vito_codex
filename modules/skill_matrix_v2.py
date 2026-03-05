"""Skill Matrix v2: service/helper/persona/recipe mapping for all VITO agents."""

from __future__ import annotations

from typing import Any

VALID_SKILL_KINDS = {"service", "helper", "persona", "recipe"}


_AGENT_PRIMARY_KIND: dict[str, str] = {
    "vito_core": "persona",
    "trend_scout": "service",
    "content_creator": "service",
    "smm_agent": "service",
    "marketing_agent": "service",
    "ecommerce_agent": "service",
    "seo_agent": "service",
    "email_agent": "service",
    "translation_agent": "helper",
    "analytics_agent": "service",
    "economics_agent": "helper",
    "legal_agent": "helper",
    "risk_agent": "helper",
    "security_agent": "helper",
    "devops_agent": "helper",
    "hr_agent": "service",
    "partnership_agent": "service",
    "research_agent": "service",
    "document_agent": "helper",
    "account_manager": "service",
    "browser_agent": "helper",
    "publisher_agent": "service",
    "quality_judge": "persona",
}


def _infer_recipe_names(agent_name: str, capabilities: list[str]) -> list[str]:
    caps = [str(c).strip().lower() for c in (capabilities or []) if str(c).strip()]
    recipes: list[str] = []
    if any("research" in c or "trend" in c for c in caps):
        recipes.append("recipe.research_pipeline")
    if any("listing" in c or "ecommerce" in c or "publish" in c for c in caps):
        recipes.append("recipe.listing_publish_pipeline")
    if any("security" in c or "risk" in c for c in caps):
        recipes.append("recipe.risk_gate_pipeline")
    if any("documentation" in c or "knowledge" in c or "document" in c for c in caps):
        recipes.append("recipe.knowledge_ingest_pipeline")
    if any("orchestrate" in c or "dispatch" in c for c in caps):
        recipes.append("recipe.orchestration_pipeline")
    if not recipes:
        recipes.append(f"recipe.{agent_name}.default")
    return recipes


def build_agent_skill_matrix_v2(agent_name: str, capabilities: list[str], description: str = "") -> dict[str, Any]:
    name = str(agent_name or "").strip().lower()
    primary_kind = _AGENT_PRIMARY_KIND.get(name, "service")
    if primary_kind not in VALID_SKILL_KINDS:
        primary_kind = "service"
    caps = [str(c).strip() for c in (capabilities or []) if str(c).strip()]
    return {
        "agent": name,
        "description": str(description or "").strip(),
        "primary_kind": primary_kind,
        "service": caps,
        "helper": [c for c in caps if any(k in c.lower() for k in ("check", "health", "translate", "parse", "monitor"))],
        "persona": [f"persona.{name}"],
        "recipe": _infer_recipe_names(name, caps),
    }


def validate_agent_skill_matrix_v2(row: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(row, dict):
        return False, ["row_not_dict"]
    if not str(row.get("agent", "")).strip():
        errors.append("agent_missing")
    kind = str(row.get("primary_kind", "")).strip().lower()
    if kind not in VALID_SKILL_KINDS:
        errors.append("primary_kind_invalid")
    for key in ("service", "helper", "persona", "recipe"):
        val = row.get(key)
        if not isinstance(val, list):
            errors.append(f"{key}_not_list")
            continue
        if any(not str(x).strip() for x in val):
            errors.append(f"{key}_contains_empty")
    return len(errors) == 0, errors

