from __future__ import annotations

from typing import Any

from modules.task_lineage import derive_artifact_map, derive_child_id, generate_task_root_id


def ensure_lineage_payload(task_type: str, kwargs: dict[str, Any] | None, responsible_agent: str = "") -> tuple[dict[str, Any], dict[str, str]]:
    payload = dict(kwargs or {})
    task_root_id = str(payload.get("task_root_id") or "").strip()
    if not task_root_id:
        seed = (
            str(payload.get("goal_title") or "").strip()
            or str(payload.get("step") or "").strip()
            or str(payload.get("topic") or "").strip()
            or str(payload.get("text") or "").strip()
            or str(task_type or "").strip()
        )
        task_root_id = generate_task_root_id(seed)
        payload["task_root_id"] = task_root_id

    artifact_map = derive_artifact_map(task_root_id)
    for key, value in artifact_map.items():
        payload.setdefault(key, value)

    if responsible_agent:
        payload.setdefault(
            "agent_work_id",
            derive_child_id(task_root_id, "agent_work", 1, responsible_agent),
        )

    return payload, artifact_map


def attach_lineage_metadata(
    metadata: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    task_type: str,
    responsible_agent: str = "",
) -> dict[str, Any]:
    md = dict(metadata or {})
    src = dict(payload or {})
    task_root_id = str(src.get("task_root_id") or md.get("task_root_id") or "").strip()
    if not task_root_id:
        task_root_id = generate_task_root_id(task_type or responsible_agent or "task")
    artifact_map = derive_artifact_map(task_root_id)

    md.setdefault("task_root_id", task_root_id)
    md.setdefault("project_id", str(src.get("project_id") or artifact_map.get("project_id") or ""))
    md.setdefault("listing_work_id", str(src.get("listing_id") or src.get("listing_work_id") or artifact_map.get("listing_id") or ""))
    md.setdefault("research_work_id", str(src.get("research_id") or src.get("research_work_id") or artifact_map.get("research_id") or ""))
    md.setdefault("content_work_id", str(src.get("content_id") or src.get("content_work_id") or artifact_map.get("content_id") or ""))
    md.setdefault("seo_work_id", str(src.get("seo_id") or src.get("seo_work_id") or artifact_map.get("seo_id") or ""))
    md.setdefault("publish_work_id", str(src.get("publish_id") or src.get("publish_work_id") or artifact_map.get("publish_id") or ""))
    md.setdefault("metadata_work_id", str(src.get("metadata_id") or src.get("metadata_work_id") or artifact_map.get("metadata_id") or ""))
    md.setdefault("cover_id", str(src.get("cover_id") or artifact_map.get("cover_id") or ""))
    md.setdefault("preview_id", str(src.get("preview_id") or artifact_map.get("preview_id") or ""))
    md.setdefault("social_image_id", str(src.get("social_image_id") or artifact_map.get("social_image_id") or ""))
    if responsible_agent:
        md.setdefault(
            "agent_work_id",
            str(src.get("agent_work_id") or derive_child_id(task_root_id, "agent_work", 1, responsible_agent)),
        )
    return md
