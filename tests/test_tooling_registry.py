from modules.tooling_registry import ToolingRegistry


def test_tooling_registry_upsert_and_list(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    out = reg.upsert_adapter(
        adapter_key="github_openapi",
        protocol="openapi",
        endpoint="https://api.github.com/openapi.json",
        auth_type="bearer",
        enabled=True,
        schema={"openapi": "3.0.0", "paths": {}},
    )
    assert out["ok"] is True
    rows = reg.list_adapters(limit=10)
    assert rows
    assert rows[0]["adapter_key"] == "github_openapi"


def test_tooling_registry_validate_mcp(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    bad = reg.upsert_adapter(
        adapter_key="bad_mcp",
        protocol="mcp",
        endpoint="stdio://local",
        schema={},
    )
    assert bad["ok"] is False
    assert bad["errors"]
