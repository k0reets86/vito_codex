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
    ok, reason = reg.verify_contract(rows[0])
    assert ok is True
    assert reason == "contract_ok"


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


def test_tooling_registry_contract_mismatch(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="demo",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    conn = reg._get_conn()
    try:
        conn.execute("UPDATE tooling_registry SET contract_signature = 'bad' WHERE adapter_key='demo'")
        conn.commit()
    finally:
        conn.close()
    row = reg.list_adapters(limit=10)[0]
    ok, reason = reg.verify_contract(row)
    assert ok is False
    assert reason in {"contract_signature_mismatch", "contract_hash_mismatch"}
