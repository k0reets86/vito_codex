from pathlib import Path
from unittest.mock import MagicMock

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


def test_skill_library_semantic_merge_prioritizes_memory_hits(tmp_path):
    db = tmp_path / "test.sqlite"
    skill_library_module.SKILL_LIBRARY_DIR = tmp_path / "skills"
    memory = MagicMock()
    memory._chroma_doc_count = 2
    memory.search_knowledge.return_value = [
        {
            "id": "skill_lib_semantic_launch",
            "text": "semantic hit",
            "metadata": {"skill_name": "semantic_launch"},
            "relevance": 0.91,
        }
    ]
    lib = VITOSkillLibrary(sqlite_path=str(db), memory=memory)
    lib.add_skill(
        name="semantic_launch",
        description="Launch a product across platforms.",
        category="commerce_execution",
        source_agent="publisher_agent",
        trigger_hint="launch product",
        tags=["launch"],
        metadata={"task_family": "product_launch"},
    )
    lib.add_skill(
        name="plain_writer",
        description="Write generic content copy.",
        category="content_growth",
        source_agent="content_creator",
        trigger_hint="write content",
        tags=["content"],
    )

    found = lib.retrieve("product launch workflow", n=2)
    assert found
    assert found[0]["name"] == "semantic_launch"
    assert float(found[0].get("semantic_score", 0.0)) > 0.0
