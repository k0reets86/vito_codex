from modules.evolution_archive import EvolutionArchive
from modules.knowledge_consolidator import KnowledgeConsolidator
from modules.reflector import VITOReflector
from memory.memory_manager import MemoryManager


def test_knowledge_consolidator_builds_cross_layer_pack(tmp_path):
    memory = MemoryManager()
    memory._sqlite_conn = None
    memory._chroma_client = None
    memory._chroma_collection = None
    memory._chroma_doc_count = 0
    memory._knowledge_graph = memory._knowledge_graph.__class__(str(tmp_path / "kg.db"))

    import memory.memory_manager as mm_mod
    original_sqlite = mm_mod.settings.SQLITE_PATH
    original_chroma = mm_mod.settings.CHROMA_PATH
    try:
        mm_mod.settings.SQLITE_PATH = str(tmp_path / "mm.db")
        mm_mod.settings.CHROMA_PATH = str(tmp_path / "chroma")
        memory.store_knowledge(
            "doc_etsy",
            "Etsy draft workflow with file and images",
            {
                "type": "lesson",
                "platform": "etsy",
                "task_family": "listing_create",
                "task_root_id": "task-42",
                "force_save": True,
            },
        )
        reflector = VITOReflector(sqlite_path=str(tmp_path / "mm.db"), memory_manager=memory)
        archive = EvolutionArchive(sqlite_path=str(tmp_path / "mm.db"))
        archive.record(
            archive_type="self_heal_v2",
            title="repair listing flow",
            payload={"status": "ok"},
            success=True,
            task_root_id="task-42",
        )
        pack = memory.build_runtime_knowledge_pack(
            query="Etsy draft workflow",
            services=["etsy"],
            task_root_id="task-42",
            limit=5,
            reflector=reflector,
            evolution_archive=archive,
        )
    finally:
        mm_mod.settings.SQLITE_PATH = original_sqlite
        mm_mod.settings.CHROMA_PATH = original_chroma

    assert pack["query"] == "Etsy draft workflow"
    assert pack["signals"]["semantic_knowledge"] >= 1
    assert pack["signals"]["platform_knowledge"] >= 0
    assert pack["signals"]["evolution_archive"] >= 1
    assert pack["signals"]["knowledge_graph"] >= 1
    assert "knowledge_pack" in pack["summary"]


def test_platform_knowledge_paths_are_project_relative():
    import modules.platform_knowledge as pk

    assert "vito-agent" in str(pk.KB_PATH)
    assert "vito-agent" in str(pk.JSON_DB_PATH)
