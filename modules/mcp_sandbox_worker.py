"""Sandboxed MCP stdio worker with allowlist and timeout."""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any

from config.settings import settings


class MCPSandboxWorker:
    def __init__(self):
        allow = str(getattr(settings, "TOOLING_MCP_ALLOW_CMDS", "") or "")
        self.allowed_cmds = {x.strip() for x in allow.split(",") if x.strip()}
        self.timeout_sec = max(1, int(getattr(settings, "TOOLING_MCP_TIMEOUT_SEC", 12) or 12))
        self.max_output_bytes = max(1024, int(getattr(settings, "TOOLING_MCP_MAX_OUTPUT_BYTES", 32768) or 32768))

    def run(self, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if not endpoint.startswith("stdio://"):
            return {"status": "failed", "error": "unsupported_mcp_endpoint"}
        cmd_text = endpoint.replace("stdio://", "", 1).strip()
        if not cmd_text:
            return {"status": "failed", "error": "empty_mcp_command"}
        try:
            argv = shlex.split(cmd_text)
        except Exception as e:
            return {"status": "failed", "error": f"mcp_command_parse_failed:{e}"}
        if not argv:
            return {"status": "failed", "error": "empty_mcp_argv"}
        cmd = argv[0]
        if self.allowed_cmds and cmd not in self.allowed_cmds:
            return {"status": "failed", "error": f"mcp_command_not_allowed:{cmd}"}
        # no shell; stdio only
        try:
            raw_in = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            proc = subprocess.run(
                argv,
                input=raw_in,
                capture_output=True,
                timeout=self.timeout_sec,
                check=False,
            )
            out = (proc.stdout or b"")[: self.max_output_bytes]
            err = (proc.stderr or b"")[:4096].decode("utf-8", errors="ignore")
            if proc.returncode != 0:
                return {"status": "failed", "error": f"mcp_exit_{proc.returncode}:{err[:300]}"}
            text = out.decode("utf-8", errors="ignore").strip()
            if not text:
                return {"status": "failed", "error": "mcp_empty_output"}
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = {"raw_output": text[:1000]}
            return {"status": "ok", "output": parsed}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "mcp_timeout"}
        except Exception as e:
            return {"status": "failed", "error": f"mcp_run_failed:{e}"}
