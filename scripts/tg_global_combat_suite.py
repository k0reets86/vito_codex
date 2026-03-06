#!/usr/bin/env python3
"""Global combat suite: TG-owner flows + live platform verification.

Runs:
1) Local owner-simulator TG flows (through Comms handlers)
2) Live publish matrix
3) Live agent->platform audit
4) Social live probe
Produces one consolidated report with pass/fail summary.
"""

from __future__ import annotations

import json
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], timeout: int = 420) -> tuple[int, str, bool]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        merged = (out + ("\n" + err if err else "")).strip()
        return int(p.returncode), merged, False
    except subprocess.TimeoutExpired as e:
        tail = str((e.stdout or "")[-3000:] if isinstance(e.stdout, str) else "")
        etail = str((e.stderr or "")[-3000:] if isinstance(e.stderr, str) else "")
        merged = (
            f"timeout after {timeout}s\n"
            + (tail or "")
            + (("\n" + etail) if etail else "")
        ).strip()
        return 124, merged, True


def _find_report_path(output: str) -> str:
    for line in reversed((output or "").splitlines()):
        s = line.strip()
        if "/reports/" in s and s.endswith(".json"):
            return s
    return ""


def _load_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="Output report path")
    ap.add_argument("--timeout", type=int, default=420, help="Per-command timeout in seconds")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    report_path = Path(args.out) if args.out else (ROOT / "reports" / f"VITO_TG_GLOBAL_COMBAT_{ts}.json")

    steps: list[dict[str, Any]] = []

    commands = [
        ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "smoke"],
        ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "platform_context"],
        ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "phase_platform_e2e"],
        ["python3", "scripts/live_publish_matrix.py", "--live"],
        ["python3", "scripts/live_agent_platform_audit.py"],
        ["python3", "scripts/social_live_probe.py"],
    ]

    for cmd in commands:
        rc, output, timed_out = _run(cmd, timeout=max(30, int(args.timeout or 420)))
        rpath = _find_report_path(output)
        payload = _load_json(rpath)
        steps.append(
            {
                "cmd": " ".join(cmd),
                "rc": rc,
                "timeout": bool(timed_out),
                "report_path": rpath,
                "stdout_tail": "\n".join(output.splitlines()[-30:]),
                "payload": payload,
            }
        )

    summary = {
        "tg_smoke_passed": False,
        "tg_platform_context_passed": False,
        "tg_platform_e2e_passed": False,
        "publish_matrix_ready": {},
        "agent_audit_responding_percent": 0.0,
        "social_auth": {},
        "timeouts": 0,
    }

    # Parse TG scenarios
    for st in steps:
        if st.get("timeout"):
            summary["timeouts"] += 1
        p = st.get("payload") or {}
        scenario = str(p.get("scenario") or "")
        sm = p.get("summary") or {}
        if scenario == "smoke":
            summary["tg_smoke_passed"] = bool(sm.get("failed", 1) == 0)
        if scenario == "platform_context":
            summary["tg_platform_context_passed"] = bool(sm.get("failed", 1) == 0)
        if scenario == "phase_platform_e2e":
            summary["tg_platform_e2e_passed"] = bool(sm.get("failed", 1) == 0)

    # Parse publish matrix
    for st in steps:
        p = st.get("payload") or {}
        if p.get("mode") != "live" or "results" not in p:
            continue
        for row in p.get("results") or []:
            plat = str(row.get("platform") or "")
            pub = row.get("publish") or {}
            summary["publish_matrix_ready"][plat] = {
                "auth_ok": bool(row.get("auth_ok")),
                "status": str(pub.get("status") or ""),
                "error": str(pub.get("error") or ""),
            }

    # Parse agent audit
    for st in steps:
        p = st.get("payload") or {}
        if p.get("mode") == "live_agent_platform_audit":
            summary["agent_audit_responding_percent"] = float((p.get("summary") or {}).get("responding_percent") or 0.0)

    # Parse social probe
    for st in steps:
        p = st.get("payload") or {}
        if "steps" in p and isinstance(p.get("steps"), list):
            social_auth = {}
            for row in p.get("steps") or []:
                name = str(row.get("platform") or "")
                if not name:
                    continue
                social_auth[name] = {
                    "auth_ok": bool(row.get("auth_ok", False)),
                    "skipped": bool(row.get("skipped", False)),
                }
            if social_auth:
                summary["social_auth"] = social_auth

    final = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "tg_global_combat_suite",
        "steps": steps,
        "summary": summary,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report_path))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
