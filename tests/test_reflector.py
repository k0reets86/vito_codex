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
