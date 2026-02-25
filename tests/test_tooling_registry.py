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


def test_tooling_registry_rotation_approval_flow(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    req = reg.request_contract_rotation(
        adapter_key="rot_demo",
        adapter_version="2.0.0",
        protocol="openapi",
        endpoint="https://example.com/openapi-v2.json",
        schema={"openapi": "3.0.0", "paths": {}},
        requested_by="test",
    )
    assert req["ok"] is True
    pending = reg.list_contract_approvals(status="pending", limit=10)
    assert pending
    app_id = pending[0]["id"]
    approved = reg.approve_contract_rotation(app_id, approver="owner", reason="ok")
    assert approved["ok"] is True
    rows = reg.list_adapters(limit=10)
    assert rows
    assert rows[0]["adapter_key"] == "rot_demo"
    assert rows[0]["adapter_version"] == "2.0.0"
