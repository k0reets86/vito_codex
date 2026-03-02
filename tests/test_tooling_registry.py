from modules.tooling_registry import ToolingRegistry
from config.settings import settings


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
    assert rows[0]["adapter_stage"] == "staging"


def test_tooling_registry_production_requires_stage_approval(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="need_appr",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
        adapter_stage="accepted",
    )
    out = reg.promote_adapter("need_appr", "production", actor="owner", reason="release")
    assert out["ok"] is False
    assert out["error"] == "production_approval_required"


def test_tooling_registry_promote_and_rollback(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="prom_demo",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
        adapter_stage="staging",
    )
    # Promote to accepted (no mandatory approval by default policy)
    p1 = reg.promote_adapter("prom_demo", "accepted", actor="owner", reason="qa ok")
    assert p1["ok"] is True
    # Production requires stage approval: request and approve
    req = reg.request_stage_change(
        adapter_key="prom_demo",
        action="promote",
        target_stage="production",
        requested_by="owner",
    )
    assert req["ok"] is True
    app = reg.approve_stage_change(req["approval_id"], approver="owner", reason="release")
    assert app["ok"] is True
    row = reg.list_adapters(limit=1)[0]
    assert row["adapter_stage"] == "production"
    # Rollback requires stage approval
    req_rb = reg.request_stage_change(
        adapter_key="prom_demo",
        action="rollback",
        requested_by="owner",
    )
    assert req_rb["ok"] is True
    rb = reg.approve_stage_change(req_rb["approval_id"], approver="owner", reason="issue")
    assert rb["ok"] is True
    row2 = reg.list_adapters(limit=1)[0]
    assert row2["adapter_stage"] in {"accepted", "staging"}
    hist = reg.list_release_history(adapter_key="prom_demo", limit=10)
    assert hist
    ok_bundle, reason = reg.verify_release_bundle(hist[0])
    assert ok_bundle is True
    assert reason == "bundle_ok"


def test_tooling_registry_key_rotation_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_CONTRACT_KEYS", "k1:s1,k2:s2")
    monkeypatch.setattr(settings, "TOOLING_CONTRACT_ACTIVE_KEY_ID", "k1")
    monkeypatch.setattr(settings, "TOOLING_RELEASE_KEYS", "r1:x1,r2:x2")
    monkeypatch.setattr(settings, "TOOLING_RELEASE_ACTIVE_KEY_ID", "r1")
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    out = reg.upsert_adapter(
        adapter_key="rot_keys",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    assert out["ok"] is True
    assert out["contract_key_id"] == "k1"
    req = reg.request_signature_key_rotation(
        key_type="contract",
        requested_key_id="k2",
        requested_by="owner",
    )
    assert req["ok"] is True
    ok = reg.approve_signature_key_rotation(req["rotation_id"], approver="owner")
    assert ok["ok"] is True
    out2 = reg.upsert_adapter(
        adapter_key="rot_keys_2",
        protocol="openapi",
        endpoint="https://example.com/openapi-v2.json",
        schema={"openapi": "3.0.0", "paths": {}},
    )
    assert out2["ok"] is True
    assert out2["contract_key_id"] == "k2"
    policy = reg.get_signature_policy()
    assert policy["contract_active_key_id"] == "k2"


def test_tooling_registry_governance_report(tmp_path):
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    reg.upsert_adapter(
        adapter_key="gov_demo",
        protocol="openapi",
        endpoint="https://example.com/openapi.json",
        schema={"openapi": "3.0.0", "paths": {}},
        adapter_stage="accepted",
    )
    req = reg.request_stage_change(
        adapter_key="gov_demo",
        action="promote",
        target_stage="production",
        requested_by="owner",
    )
    assert req["ok"] is True
    rep = reg.build_governance_report(days=7)
    assert rep["adapters_total"] >= 1
    assert "contract_integrity" in rep
    assert rep["pending_stage_changes"] >= 1
    assert isinstance(rep["remediations"], list)


def test_tooling_registry_governance_rotation_cadence_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_KEY_ROTATION_MAX_DAYS", 30)
    monkeypatch.setattr(settings, "TOOLING_KEY_ROTATION_WARN_DAYS", 7)
    db = str(tmp_path / "tools.db")
    reg = ToolingRegistry(sqlite_path=db)
    conn = reg._get_conn()
    try:
        conn.execute(
            """
            UPDATE tooling_signature_policy
            SET updated_at = datetime('now', '-45 day')
            WHERE id = 1
            """
        )
        conn.commit()
    finally:
        conn.close()
    rep = reg.build_governance_report(days=7)
    health = rep.get("key_rotation_health", {})
    assert int(health.get("max_days") or 0) == 30
    assert isinstance(health.get("alerts"), list)
    assert health.get("alerts")
    assert any("Rotate signature keys" in r for r in rep.get("remediations", []))
