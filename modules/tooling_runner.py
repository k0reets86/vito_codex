"""Safe runtime execution for tooling adapters from ToolingRegistry."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from config.settings import settings
from modules.operator_policy import OperatorPolicy
from modules.tooling_registry import ToolingRegistry


class ToolingRunner:
    def __init__(self, sqlite_path: str | None = None):
        self.registry = ToolingRegistry(sqlite_path=sqlite_path)
        self.policy = OperatorPolicy(sqlite_path=sqlite_path)

    def run(self, adapter_key: str, input_data: dict[str, Any] | None = None, dry_run: bool = True) -> dict[str, Any]:
        input_data = input_data or {}
        rows = self.registry.list_adapters(enabled_only=False, limit=500)
        adapter = next((r for r in rows if r.get("adapter_key") == adapter_key), None)
        if not adapter:
            result = {"status": "error", "error": "adapter_not_found", "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result
        if int(adapter.get("enabled", 0) or 0) != 1:
            result = {"status": "error", "error": "adapter_disabled", "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result

        policy_key = f"tooling:{adapter_key}"
        allowed, reason = self.policy.is_tool_allowed(policy_key)
        if not allowed:
            result = {"status": "error", "error": "policy_blocked", "reason": reason, "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result
        budget = self.policy.check_actor_budget(policy_key)
        if not budget.get("allowed", True):
            result = {
                "status": "error",
                "error": "budget_blocked",
                "reason": budget.get("reason", ""),
                "adapter_key": adapter_key,
            }
            self._record_event(adapter_key, result)
            return result

        live_allowed = bool(getattr(settings, "TOOLING_RUN_LIVE_ENABLED", False))
        if dry_run or not live_allowed:
            result = {
                "status": "dry_run",
                "adapter_key": adapter_key,
                "protocol": adapter.get("protocol"),
                "endpoint": adapter.get("endpoint"),
                "auth_type": adapter.get("auth_type"),
                "input_preview": {k: str(v)[:120] for k, v in list(input_data.items())[:20]},
                "reason": "dry_run" if dry_run else "live_disabled",
            }
            self._record_event(adapter_key, result)
            return result

        protocol = str(adapter.get("protocol", "")).strip().lower()
        endpoint = str(adapter.get("endpoint", "")).strip()
        if protocol == "openapi":
            result = self._run_openapi_probe(adapter_key=adapter_key, endpoint=endpoint)
            self._record_event(adapter_key, result)
            return result
        if protocol == "mcp":
            # Explicitly keep MCP live execution disabled in this runner.
            result = {
                "status": "prepared",
                "adapter_key": adapter_key,
                "protocol": protocol,
                "endpoint": endpoint,
                "notes": "mcp live execution requires dedicated sandbox adapter",
            }
            self._record_event(adapter_key, result)
            return result

        # Unknown protocol fallback.
        result = {
            "status": "prepared",
            "adapter_key": adapter_key,
            "protocol": adapter.get("protocol"),
            "endpoint": endpoint,
            "notes": "protocol handler not implemented",
        }
        self._record_event(adapter_key, result)
        return result

    @staticmethod
    def _run_openapi_probe(adapter_key: str, endpoint: str) -> dict[str, Any]:
        req = urllib.request.Request(endpoint, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(settings.TOOLING_HTTP_TIMEOUT_SEC))) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                body = resp.read(16384)
            schema_ok = False
            version = ""
            try:
                data = json.loads(body.decode("utf-8", errors="ignore"))
                schema_ok = bool(isinstance(data, dict) and ("openapi" in data or "paths" in data))
                version = str(data.get("openapi", "")) if isinstance(data, dict) else ""
            except Exception:
                schema_ok = False
            return {
                "status": "ok" if schema_ok else "failed",
                "adapter_key": adapter_key,
                "protocol": "openapi",
                "endpoint": endpoint,
                "http_status": status,
                "schema_ok": schema_ok,
                "openapi_version": version,
            }
        except Exception as e:
            return {
                "status": "failed",
                "adapter_key": adapter_key,
                "protocol": "openapi",
                "endpoint": endpoint,
                "error": f"openapi_probe_failed:{e}",
            }

    @staticmethod
    def _record_event(adapter_key: str, result: dict[str, Any]) -> None:
        try:
            from modules.data_lake import DataLake
            status = "success" if result.get("status") in {"dry_run", "prepared", "ok"} else "failed"
            DataLake().record(
                agent="tooling_runner",
                task_type=f"tooling:{adapter_key}",
                status=status,
                output=result,
                error=str(result.get("error", ""))[:300],
                source="tooling_runner",
            )
        except Exception:
            pass
