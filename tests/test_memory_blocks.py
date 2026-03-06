from modules.memory_blocks import MemoryBlocks


def test_find_blocks_filters_by_agent(tmp_path):
    sqlite_path = tmp_path / "memory.sqlite"
    blocks = MemoryBlocks(sqlite_path=str(sqlite_path))
    blocks.record_block(
        doc_id="research_agent:skill:1",
        block_type="skill",
        summary="research summary",
        metadata={"agent": "research_agent"},
        retention_class="project_mid",
        stage="mid",
        importance=0.8,
    )
    blocks.record_block(
        doc_id="seo_agent:skill:1",
        block_type="skill",
        summary="seo summary",
        metadata={"agent": "seo_agent"},
        retention_class="project_mid",
        stage="mid",
        importance=0.7,
    )
    rows = blocks.find_blocks(agent="research_agent", limit=10)
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "research_agent:skill:1"
