import json

import pytest

import modules.reflector as reflector_module
from modules.reflector import VITOReflector


@pytest.mark.asyncio
async def test_reflector_persists_reflection_and_attribution(tmp_path):
    db = tmp_path / "test.sqlite"
    reflector_module.LEARNINGS_DIR = tmp_path / ".learnings"
    reflector_module.LEARNINGS_FILE = reflector_module.LEARNINGS_DIR / "LEARNINGS.md"
    reflector_module.ATTRIBUTION_FILE = reflector_module.LEARNINGS_DIR / "attribution_map.json"
    r = VITOReflector(sqlite_path=str(db))

    out = await r.reflect(
        category="ecommerce",
        action_type="listing_create",
        input_summary="Create Etsy listing",
        outcome_summary="Listing saved with file and cover",
        success=True,
        task_root_id="task123",
        context={"platform": "etsy", "source": "decision_loop", "factors": ["file", "cover"]},
    )
    assert "reflection" in out
    recent = r.get_recent(n=5, category="ecommerce")
    assert recent
    amap = json.loads(reflector_module.ATTRIBUTION_FILE.read_text(encoding="utf-8"))
    assert amap["listing_create"]["success"] >= 1
    assert "etsy" in amap["listing_create"]["platforms"]


@pytest.mark.asyncio
async def test_reflector_stores_and_uses_semantic_reflections(tmp_path):
    db = tmp_path / "test.sqlite"
    reflector_module.LEARNINGS_DIR = tmp_path / ".learnings"
    reflector_module.LEARNINGS_FILE = reflector_module.LEARNINGS_DIR / "LEARNINGS.md"
    reflector_module.ATTRIBUTION_FILE = reflector_module.LEARNINGS_DIR / "attribution_map.json"

    class _Memory:
        def __init__(self):
            self.saved = []

        def store_knowledge(self, doc_id, text, metadata):
            self.saved.append({"doc_id": doc_id, "text": text, "metadata": metadata})

        def search_knowledge(self, query, n_results=10):
            return [
                {
                    "text": "reflection ecommerce listing_create",
                    "metadata": {
                        "block_type": "reflection",
                        "category": "ecommerce",
                        "action_type": "listing_create",
                    },
                }
            ]

    mem = _Memory()
    r = VITOReflector(sqlite_path=str(db), memory_manager=mem)
    await r.reflect(
        category="ecommerce",
        action_type="listing_create",
        input_summary="Create Etsy listing",
        outcome_summary="Saved with media",
        success=True,
        task_root_id="task999",
        context={"platform": "etsy", "source": "decision_loop"},
    )
    assert mem.saved
    top = r.top_relevant("etsy listing media", n=3)
    assert top
    assert top[0]["category"] == "ecommerce"
    assert top[0]["action_type"] == "listing_create"
