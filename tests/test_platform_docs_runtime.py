from modules.platform_docs_runtime import get_docs_runtime, sync_docs_runtime
from modules.platform_policy_packs import build_service_policy_pack
from modules.platform_runtime_registry import get_runtime_entry


def test_docs_runtime_extracts_service_sections():
    data = sync_docs_runtime(["etsy"])
    etsy = data["services"]["etsy"]
    assert etsy["service"] == "etsy"
    assert "knowledge_count" in etsy
    assert "rules_count" in etsy


def test_policy_pack_reads_docs_runtime_cache():
    sync_docs_runtime(["etsy"])
    pack = build_service_policy_pack("etsy")
    assert pack["service"] == "etsy"
    assert "policy_notes" in pack
    assert "rules_updates" in pack


def test_runtime_entry_includes_docs_runtime_metadata():
    sync_docs_runtime(["etsy"])
    entry = get_runtime_entry("etsy", refresh=True)
    assert entry["service"] == "etsy"
    assert "docs_runtime" in entry
