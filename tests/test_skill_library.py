from pathlib import Path

import modules.skill_library as skill_library_module
from modules.skill_library import VITOSkillLibrary


def test_skill_library_add_retrieve_and_record_use(tmp_path):
    db = tmp_path / "test.sqlite"
    skill_library_module.SKILL_LIBRARY_DIR = tmp_path / "skills"
    lib = VITOSkillLibrary(sqlite_path=str(db))

    lib.add_skill(
        name="meme_pack_launch",
        description="Launch a meme-based digital product across marketplaces.",
        category="commerce_execution",
        source_agent="ecommerce_agent",
        trigger_hint="meme gumroad etsy launch",
        code_ref="platforms/gumroad.py",
        tags=["meme", "gumroad", "etsy"],
    )
    lib.record_use("meme_pack_launch", success=True)

    found = lib.retrieve("launch meme product on etsy", n=3)
    assert found
    assert found[0]["name"] == "meme_pack_launch"
    assert int(found[0]["usage_count"] or 0) >= 1
    assert Path(skill_library_module.SKILL_LIBRARY_DIR / "meme_pack_launch.json").exists()
