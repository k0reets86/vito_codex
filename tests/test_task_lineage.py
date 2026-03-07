from modules.owner_task_state import OwnerTaskState
from modules.platform_artifact_pack import build_platform_bundle
from modules.task_lineage import derive_artifact_map, ensure_task_lineage


def test_ensure_task_lineage_generates_root_and_children():
    task_root_id, artifact_ids = ensure_task_lineage({"text": "publish gumroad listing"}, "publish gumroad listing")
    assert task_root_id.startswith("VT")
    assert artifact_ids["project_id"].startswith(task_root_id)
    assert artifact_ids["cover_id"].startswith(task_root_id)
    assert artifact_ids["publish_id"].startswith(task_root_id)


def test_owner_task_state_auto_assigns_lineage_ids(tmp_path):
    state = OwnerTaskState(path=tmp_path / "owner_task_state.json")
    ok = state.set_active("создай продукт на гумроад", source="telegram", intent="goal_request")
    assert ok is True
    active = state.get_active()
    assert active is not None
    task_root_id = str(active.get("task_root_id") or "")
    assert task_root_id.startswith("VT")
    assert str(active.get("content_work_id") or "").startswith(task_root_id)
    assert str(active.get("seo_work_id") or "").startswith(task_root_id)


def test_build_platform_bundle_uses_task_root_id_in_fresh_asset_names(tmp_path):
    task_root_id, artifact_ids = ensure_task_lineage({"text": "publish gumroad listing"}, "publish gumroad listing")
    bundle = build_platform_bundle(
        "gumroad",
        {
            "title": "Test Listing",
            "topic": "AI Side Hustle Starter Kit",
            "fresh_artifacts_only": True,
            "run_tag": "tgtest",
            "task_root_id": task_root_id,
        },
    )
    assert bundle["task_root_id"] == task_root_id
    assert task_root_id in str(bundle["pdf_path"])
    assert task_root_id in str(bundle["cover_path"])
    assert task_root_id in str(bundle["thumb_path"])
    assert bundle["product_file_id"] == artifact_ids["product_file_id"]
    assert bundle["cover_id"] == artifact_ids["cover_id"]
