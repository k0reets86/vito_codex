from modules.platform_docs_runtime import sync_docs_runtime
from modules.platform_policy_packs import build_service_policy_pack
from modules.platform_runtime_registry import sync_platform_runtime_registry


def test_runtime_registry_captures_docs_runtime_meta():
    docs = sync_docs_runtime(["etsy"])
    result = sync_platform_runtime_registry(["etsy"])
    assert result["count"] == 1
    from modules.platform_runtime_registry import _read_registry  # local import for current persisted state

    reg = _read_registry()
    meta = reg.get("docs_runtime_meta") or {}
    assert meta.get("knowledge_hash") == docs["source_meta"]["knowledge_hash"]
    assert meta.get("rules_hash") == docs["source_meta"]["rules_hash"]
    assert int(reg.get("docs_runtime_schema_version") or 0) >= 2


def test_policy_pack_prefers_runtime_registry_values():
    sync_platform_runtime_registry(["etsy"])
    pack = build_service_policy_pack("etsy")
    assert pack["service"] == "etsy"
    assert isinstance(pack["policy_notes"], list)
    assert isinstance(pack["rules_updates"], list)
    assert "has_policy_knowledge" in pack
