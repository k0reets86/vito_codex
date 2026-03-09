#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str, bool]:
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        merged = (out + (("\n" + err) if err else "")).strip()
        return p.returncode, merged, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        merged = (out + (("\n" + err) if err else "")).strip()
        return 124, f"timeout after {timeout}s\n{merged}".strip(), True


def _find_json_path(output: str) -> str:
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
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    out = Path(args.out) if args.out else ROOT / "reports" / f"VITO_PHASE_H_COMBAT_VALIDATION_{ts}.json"

    steps: list[dict[str, Any]] = []
    commands: list[tuple[str, list[str], int]] = [
        (
            "safe_regression_pack",
            ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "phase_owner_stress_safe", "--stub-owner-flow"],
            240,
        ),
        (
            "noisy_tg_pack",
            ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "phase_owner_stress_noisy", "--stub-owner-flow"],
            240,
        ),
        (
            "live_owner_platform_pack",
            ["python3", "scripts/telegram_owner_simulator.py", "--scenario", "phase_platform_live_verify_safe"],
            240,
        ),
        (
            "duplicate_protection_pack",
            [
                "pytest", "-q", "-c", "/dev/null",
                "tests/test_comms_agent.py",
                "tests/test_platform_gumroad_policy.py",
                "tests/test_platform_etsy.py",
                "-k", "protected or duplicate or working_target or draft_only or quality_gate",
            ],
            240,
        ),
        (
            "protected_object_pack",
            [
                "pytest", "-q", "-c", "/dev/null",
                "tests/test_comms_agent.py",
                "tests/test_memory_manager.py",
                "-k", "protected or task_root_id or protected_object_registry",
            ],
            240,
        ),
        (
            "agent_benchmark_audit",
            ["python3", "scripts/mega_agent_audit.py"],
            600,
        ),
        (
            "capability_pack_validation",
            ["pytest", "-q", "-c", "/dev/null", "tests/test_capability_pack_validation.py"],
            120,
        ),
    ]

    for name, cmd, timeout in commands:
        rc, output, timed_out = _run(cmd, timeout=min(timeout, args.timeout))
        report_path = _find_json_path(output)
        payload = _load_json(report_path)
        steps.append({
            "name": name,
            "cmd": " ".join(cmd),
            "rc": rc,
            "timeout": timed_out,
            "report_path": report_path,
            "payload": payload,
            "stdout_tail": "\n".join((output or "").splitlines()[-40:]),
        })

    summary: dict[str, Any] = {
        "safe_regression_pack": False,
        "noisy_tg_pack": False,
        "live_owner_platform_pack": False,
        "duplicate_protection_pack": False,
        "protected_object_pack": False,
        "agent_benchmark_audit": False,
        "capability_pack_validation": False,
        "timeouts": sum(1 for s in steps if s["timeout"]),
        "phase_h_complete": False,
    }

    for step in steps:
        name = step["name"]
        payload = step.get("payload") or {}
        rc = int(step["rc"])
        if name in {"safe_regression_pack", "noisy_tg_pack", "live_owner_platform_pack"}:
            sm = payload.get("summary") or {}
            summary[name] = bool(rc == 0 and int(sm.get("failed", 1)) == 0 and int(sm.get("passed", 0)) == int(sm.get("total", -1)))
        elif name == "agent_benchmark_audit":
            summary[name] = bool(
                rc == 0
                and int(payload.get("combat_ready_agents", -1)) == int(payload.get("total_agents", -2))
                and int(payload.get("total_agents", 0)) >= 23
            )
        else:
            summary[name] = bool(rc == 0)

    summary["phase_h_complete"] = all(bool(v) for k, v in summary.items() if k not in {"timeouts", "phase_h_complete"})

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "phase_h_combat_validation",
        "steps": steps,
        "summary": summary,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["phase_h_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
