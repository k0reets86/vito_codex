from modules.mcp_sandbox_worker import MCPSandboxWorker


def test_mcp_worker_rejects_non_stdio():
    w = MCPSandboxWorker()
    out = w.run("https://example.com", payload={})
    assert out["status"] == "failed"


def test_mcp_worker_runs_stdio_python(monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "TOOLING_MCP_ALLOW_CMDS", "python3")
    w = MCPSandboxWorker()
    # Prints JSON to stdout
    ep = "stdio://python3 -c \"import json,sys; data=json.load(sys.stdin); print(json.dumps({'ok':True,'echo':data.get('x')}))\""
    out = w.run(ep, payload={"x": 7})
    assert out["status"] == "ok"
    assert out["output"]["ok"] is True
    assert out["output"]["echo"] == 7
