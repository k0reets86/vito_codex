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
