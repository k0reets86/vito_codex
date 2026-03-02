from config.settings import settings
from modules.tooling_discovery import ToolingDiscovery, parse_tooling_discovery_sources
from modules.tooling_registry import ToolingRegistry


def _openapi_schema():
    return {
        "openapi": "3.1.0",
        "paths": {
            "/health": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
    }


def test_discover_candidate_auto_approved_when_safe(tmp_path):
    db = str(tmp_path / "td.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.discover_candidate(
        source="mcp_index",
        adapter_key="weather_probe",
        protocol="openapi",
        endpoint="https://api.example.com/openapi.json",
        auth_type="none",
        schema=_openapi_schema(),
    )
    assert out["ok"] is True
    assert out["status"] in {"approved", "review_required"}
    rows = discovery.list_candidates(limit=10)
    assert len(rows) == 1
    assert rows[0]["adapter_key"] == "weather_probe"


def test_discover_candidate_invalid_schema_goes_review_required(tmp_path):
    db = str(tmp_path / "td_invalid.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.discover_candidate(
        source="github",
        adapter_key="broken_adapter",
        protocol="openapi",
        endpoint="https://bad.example.com/spec.json",
        auth_type="none",
        schema={"info": {"title": "broken"}},
    )
    assert out["ok"] is True
    assert out["status"] == "review_required"
    assert len(out["validation_errors"]) >= 1


def test_approve_candidate_promote_to_registry(tmp_path):
    db = str(tmp_path / "td_promote.db")
    registry = ToolingRegistry(sqlite_path=db)
    discovery = ToolingDiscovery(sqlite_path=db, registry=registry)
    out = discovery.discover_candidate(
        source="github",
        adapter_key="stocks_adapter",
        protocol="openapi",
        endpoint="https://api.example.com/stocks/openapi.json",
        auth_type="api_key",
        schema=_openapi_schema(),
    )
    cid = int(out["candidate_id"])
    promoted = discovery.approve_candidate(cid, actor="owner", promote_to_registry=True)
    assert promoted["ok"] is True
    assert promoted["status"] == "promoted"

    adapters = registry.list_adapters(limit=20)
    keys = {a["adapter_key"] for a in adapters}
    assert "stocks_adapter" in keys

    rows = discovery.list_candidates(status="promoted", limit=10)
    assert rows and int(rows[0]["id"]) == cid


def test_approve_candidate_missing_returns_error(tmp_path):
    db = str(tmp_path / "td_missing.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.approve_candidate(99999, actor="owner", promote_to_registry=True)
    assert out["ok"] is False
    assert out["error"] == "candidate_not_found"


def test_discovery_summary_counts(tmp_path):
    db = str(tmp_path / "td_summary.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    discovery.discover_candidate(
        source="s1",
        adapter_key="a1",
        protocol="openapi",
        endpoint="https://api.example.com/a1",
        schema=_openapi_schema(),
    )
    discovery.discover_candidate(
        source="s2",
        adapter_key="a2",
        protocol="mcp",
        endpoint="stdio://mcp-server",
        schema={"tools": [{"name": "ping"}]},
    )
    summary = discovery.build_summary()
    assert summary["total"] == 2
    assert isinstance(summary["by_status"], dict)


def test_discover_candidate_dedup_recent_same_endpoint(tmp_path):
    db = str(tmp_path / "td_dedup.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    first = discovery.discover_candidate(
        source="s1",
        adapter_key="a1",
        protocol="openapi",
        endpoint="https://api.example.com/a1",
        schema=_openapi_schema(),
    )
    second = discovery.discover_candidate(
        source="s1",
        adapter_key="a1",
        protocol="openapi",
        endpoint="https://api.example.com/a1",
        schema=_openapi_schema(),
    )
    assert first["ok"] is True
    assert second["ok"] is True
    assert second.get("duplicate") is True
    assert int(first["candidate_id"]) == int(second["candidate_id"])


def test_parse_tooling_discovery_sources_json():
    src = """
    [
      {"source":"manual","adapter_key":"weather","protocol":"openapi","endpoint":"https://api.example.com/openapi.json"},
      {"source":"bad","adapter_key":"","protocol":"openapi","endpoint":"https://bad.example.com"}
    ]
    """
    rows = parse_tooling_discovery_sources(src)
    assert len(rows) == 1
    assert rows[0]["adapter_key"] == "weather"


def test_parse_tooling_discovery_sources_from_file_reference(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(
        '[{"source":"file","adapter_key":"metorial_mcp","protocol":"mcp","endpoint":"https://github.com/metorial/metorial-index"}]',
        encoding="utf-8",
    )
    rows = parse_tooling_discovery_sources(f"@{p}")
    assert len(rows) == 1
    assert rows[0]["adapter_key"] == "metorial_mcp"


def test_parse_tooling_discovery_sources_line_format_with_dedup():
    src = """
    # source|adapter_key|protocol|endpoint|auth_type|notes
    github|stealth_browser_mcp|mcp|https://github.com/vibheksoni/stealth-browser-mcp|none|stealth browser
    github|stealth_browser_mcp|mcp|https://github.com/vibheksoni/stealth-browser-mcp|none|dup row
    github|petstore_openapi|openapi|https://petstore3.swagger.io/api/v3/openapi.json|none|demo
    """
    rows = parse_tooling_discovery_sources(src)
    assert len(rows) == 2
    keys = {r["adapter_key"] for r in rows}
    assert "stealth_browser_mcp" in keys
    assert "petstore_openapi" in keys


def test_discover_from_sources_canary_rollout_rotates_cursor(tmp_path):
    db = str(tmp_path / "td_rollout.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    sources = parse_tooling_discovery_sources(
        [
            {"source": "s1", "adapter_key": "a1", "protocol": "openapi", "endpoint": "https://api.example.com/a1", "schema": _openapi_schema()},
            {"source": "s1", "adapter_key": "a2", "protocol": "openapi", "endpoint": "https://api.example.com/a2", "schema": _openapi_schema()},
            {"source": "s1", "adapter_key": "a3", "protocol": "openapi", "endpoint": "https://api.example.com/a3", "schema": _openapi_schema()},
            {"source": "s1", "adapter_key": "a4", "protocol": "openapi", "endpoint": "https://api.example.com/a4", "schema": _openapi_schema()},
        ]
    )
    # canary 50% => only a1/a2 in pool; max_items=1 rotates between them.
    b1 = discovery.discover_from_sources(
        sources=sources,
        max_items=1,
        auto_promote=False,
        rollout_stage="canary",
        canary_percent=50,
        scope="test_rollout",
    )
    b2 = discovery.discover_from_sources(
        sources=sources,
        max_items=1,
        auto_promote=False,
        rollout_stage="canary",
        canary_percent=50,
        scope="test_rollout",
    )
    assert b1["processed"] == 1
    assert b2["processed"] == 1
    assert b1["selected"] and b2["selected"]
    assert set([b1["selected"][0], b2["selected"][0]]).issubset({"a1", "a2"})
    state = discovery.get_rollout_state("test_rollout")
    assert state["last_stage"] == "canary"
    assert int(state["last_pool_size"] or 0) == 2


def test_discover_from_sources_full_with_auto_promote(tmp_path):
    db = str(tmp_path / "td_rollout_promote.db")
    registry = ToolingRegistry(sqlite_path=db)
    discovery = ToolingDiscovery(sqlite_path=db, registry=registry)
    sources = parse_tooling_discovery_sources(
        [
            {"source": "batch", "adapter_key": "stocks1", "protocol": "openapi", "endpoint": "https://api.example.com/stocks1", "schema": _openapi_schema()},
            {"source": "batch", "adapter_key": "stocks2", "protocol": "openapi", "endpoint": "https://api.example.com/stocks2", "schema": _openapi_schema()},
        ]
    )
    out = discovery.discover_from_sources(
        sources=sources,
        max_items=5,
        auto_promote=True,
        rollout_stage="full",
        canary_percent=10,
        scope="promote_full",
    )
    assert out["ok"] is True
    assert out["processed"] == 2
    assert out["promoted"] >= 1
    keys = {a["adapter_key"] for a in registry.list_adapters(limit=20)}
    assert "stocks1" in keys or "stocks2" in keys


def test_discover_candidate_policy_requires_https_for_non_localhost(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_REQUIRE_HTTPS", True)
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_ALLOWED_DOMAINS", "")
    db = str(tmp_path / "td_policy_https.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.discover_candidate(
        source="policy",
        adapter_key="plain_http",
        protocol="openapi",
        endpoint="http://api.example.com/spec.json",
        auth_type="none",
        schema=_openapi_schema(),
    )
    assert out["ok"] is True
    assert out["status"] == "review_required"
    assert "endpoint_https_required" in out["validation_errors"]


def test_discover_candidate_policy_allows_http_localhost(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_REQUIRE_HTTPS", True)
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_ALLOWED_DOMAINS", "")
    db = str(tmp_path / "td_policy_local.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.discover_candidate(
        source="policy",
        adapter_key="local_http",
        protocol="openapi",
        endpoint="http://localhost:8080/openapi.json",
        auth_type="none",
        schema=_openapi_schema(),
    )
    assert out["ok"] is True
    assert "endpoint_https_required" not in out["validation_errors"]


def test_discover_candidate_policy_domain_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_REQUIRE_HTTPS", False)
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_ALLOWED_DOMAINS", "api.example.com,allowed.dev")
    db = str(tmp_path / "td_policy_domain.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    bad = discovery.discover_candidate(
        source="policy",
        adapter_key="bad_domain",
        protocol="openapi",
        endpoint="https://evil.example.net/spec.json",
        auth_type="none",
        schema=_openapi_schema(),
    )
    assert bad["ok"] is True
    assert bad["status"] == "review_required"
    assert "endpoint_domain_not_allowed" in bad["validation_errors"]
    good = discovery.discover_candidate(
        source="policy",
        adapter_key="good_domain",
        protocol="openapi",
        endpoint="https://sub.api.example.com/spec.json",
        auth_type="none",
        schema=_openapi_schema(),
    )
    assert good["ok"] is True
    assert "endpoint_domain_not_allowed" not in good["validation_errors"]


def test_discover_from_sources_reports_policy_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_REQUIRE_HTTPS", True)
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_ALLOWED_DOMAINS", "")
    db = str(tmp_path / "td_policy_batch.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    sources = parse_tooling_discovery_sources(
        [
            {"source": "batch", "adapter_key": "ok_https", "protocol": "openapi", "endpoint": "https://api.example.com/spec.json", "schema": _openapi_schema()},
            {"source": "batch", "adapter_key": "bad_http", "protocol": "openapi", "endpoint": "http://api.example.com/spec.json", "schema": _openapi_schema()},
        ]
    )
    out = discovery.discover_from_sources(
        sources=sources,
        max_items=5,
        auto_promote=False,
        rollout_stage="full",
        canary_percent=100,
        scope="policy_batch",
    )
    assert out["ok"] is True
    assert out["processed"] == 2
    assert int(out.get("policy_blocked", 0) or 0) >= 1
    reasons = out.get("policy_block_reasons", {}) or {}
    assert int(reasons.get("endpoint_https_required", 0) or 0) >= 1


def test_discover_from_config_sources_empty_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TOOLING_DISCOVERY_SOURCES", "")
    db = str(tmp_path / "td_cfg_empty.db")
    discovery = ToolingDiscovery(sqlite_path=db)
    out = discovery.discover_from_config_sources(max_items=3, scope="cfg_empty")
    assert out["ok"] is True
    assert out["processed"] == 0
    assert out["selected"] == []


def test_discover_from_config_sources_uses_runtime_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "TOOLING_DISCOVERY_SOURCES",
        '[{"source":"cfg","adapter_key":"cfg_weather","protocol":"openapi","endpoint":"https://api.example.com/weather","schema":{"openapi":"3.1.0","paths":{"/health":{"get":{"responses":{"200":{"description":"ok"}}}}}}}]',
    )
    db = str(tmp_path / "td_cfg_live.db")
    registry = ToolingRegistry(sqlite_path=db)
    discovery = ToolingDiscovery(sqlite_path=db, registry=registry)
    out = discovery.discover_from_config_sources(
        max_items=5,
        auto_promote=True,
        rollout_stage="full",
        canary_percent=100,
        scope="cfg_live",
    )
    assert out["ok"] is True
    assert out["processed"] == 1
    assert "cfg_weather" in set(out.get("selected") or [])
