from modules.tooling_registry import ToolingRegistry
from modules.tooling_runner import ToolingRunner


def test_tooling_runner_dry_run(tmp_path):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    out = reg.upsert_adapter(
        adapter_key="demo_adapter",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    assert out["ok"] is True
    run = ToolingRunner(sqlite_path=db).run("demo_adapter", {"q": "x"}, dry_run=True)
    assert run["status"] == "dry_run"
    assert run["adapter_key"] == "demo_adapter"


def test_tooling_runner_policy_block(tmp_path):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="blocked_adapter",
        protocol="mcp",
        endpoint="stdio://local",
        schema={"tools": []},
    )
    from modules.operator_policy import OperatorPolicy
    OperatorPolicy(sqlite_path=db).set_tool_policy("tooling:blocked_adapter", enabled=False, notes="owner block")
    run = ToolingRunner(sqlite_path=db).run("blocked_adapter", dry_run=True)
    assert run["status"] == "error"
    assert run["error"] == "policy_blocked"


def test_tooling_runner_live_disabled_returns_dry_reason(tmp_path, monkeypatch):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="openapi_adapter",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_RUN_LIVE_ENABLED", False)
    run = ToolingRunner(sqlite_path=db).run("openapi_adapter", dry_run=False)
    assert run["status"] == "dry_run"
    assert run["reason"] == "live_disabled"


def test_tooling_runner_mcp_live_path(tmp_path, monkeypatch):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="mcp_adapter",
        adapter_stage="production",
        protocol="mcp",
        endpoint="stdio://python3 -c \"import json,sys; data=json.load(sys.stdin); print(json.dumps({'ok':True,'v':data.get('v')}))\"",
        schema={"tools": []},
    )
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_RUN_LIVE_ENABLED", True)
    monkeypatch.setattr(settings_mod.settings, "TOOLING_MCP_ALLOW_CMDS", "python3")
    run = ToolingRunner(sqlite_path=db).run("mcp_adapter", {"v": 3}, dry_run=False)
    assert run["status"] == "ok"
    assert run["protocol"] == "mcp"


def test_tooling_runner_blocks_invalid_contract(tmp_path):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="broken_contract",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    conn = reg._get_conn()
    try:
        conn.execute("UPDATE tooling_registry SET contract_signature='invalid' WHERE adapter_key='broken_contract'")
        conn.commit()
    finally:
        conn.close()
    run = ToolingRunner(sqlite_path=db).run("broken_contract", dry_run=True)
    assert run["status"] == "error"
    assert run["error"] == "adapter_contract_invalid"


def test_tooling_runner_blocks_live_when_pending_rotation(tmp_path, monkeypatch):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="pending_demo",
        adapter_stage="production",
        protocol="mcp",
        endpoint="stdio://python3 -c \"import json; print(json.dumps({'ok':True}))\"",
        schema={"tools": []},
    )
    req = reg.request_contract_rotation(
        adapter_key="pending_demo",
        adapter_version="1.0.1",
        protocol="mcp",
        endpoint="stdio://python3 -c \"import json; print(json.dumps({'ok':True}))\"",
        schema={"tools": []},
        requested_by="test",
    )
    assert req["ok"] is True
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_RUN_LIVE_ENABLED", True)
    monkeypatch.setattr(settings_mod.settings, "TOOLING_BLOCK_WITH_PENDING_ROTATION", True)
    monkeypatch.setattr(settings_mod.settings, "TOOLING_MCP_ALLOW_CMDS", "python3")
    run = ToolingRunner(sqlite_path=db).run("pending_demo", dry_run=False)
    assert run["status"] == "error"
    assert run["error"] == "pending_rotation_approval"


def test_tooling_runner_live_stage_gate(tmp_path, monkeypatch):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="stage_demo",
        adapter_stage="accepted",
        protocol="mcp",
        endpoint="stdio://python3 -c \"import json; print(json.dumps({'ok':True}))\"",
        schema={"tools": []},
    )
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_RUN_LIVE_ENABLED", True)
    monkeypatch.setattr(settings_mod.settings, "TOOLING_MCP_ALLOW_CMDS", "python3")
    monkeypatch.setattr(settings_mod.settings, "TOOLING_LIVE_REQUIRED_STAGE", "production")
    run = ToolingRunner(sqlite_path=db).run("stage_demo", dry_run=False)
    assert run["status"] == "error"
    assert run["error"] == "adapter_stage_not_allowed_for_live"


def test_tooling_runner_mcp_scope_block(tmp_path, monkeypatch):
    db = str(tmp_path / "tool_run.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="mcp_scope_adapter",
        adapter_stage="production",
        protocol="mcp",
        endpoint="stdio://python3 -c \"import json,sys; print(json.dumps({'ok':True}))\"",
        schema={"tools": [{"name": "create_post"}, {"name": "delete_user"}]},
    )
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_RUN_LIVE_ENABLED", True)
    monkeypatch.setattr(settings_mod.settings, "TOOLING_MCP_ALLOW_CMDS", "python3")
    monkeypatch.setattr(settings_mod.settings, "MCP_TOOL_SCOPING_ENABLED", True)
    run = ToolingRunner(sqlite_path=db).run(
        "mcp_scope_adapter",
        {"task_type": "social_publish", "requested_tools": ["delete_user"]},
        dry_run=False,
    )
    assert run["status"] == "error"
    assert run["error"] == "mcp_scope_blocked"
