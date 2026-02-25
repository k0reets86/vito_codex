"""Web Operator Pack: reusable registration/form scenarios for BrowserAgent."""

from __future__ import annotations

from typing import Any

from modules.execution_facts import ExecutionFacts


SCENARIOS: dict[str, dict[str, Any]] = {
    # Generic template for email+code signup verification.
    "generic_email_signup": {
        "task_type": "register_with_email",
        "url": "",
        "form": {
            "input[type='email']": "{email}",
            "input[type='password']": "{password}",
        },
        "submit_selector": "button[type='submit']",
        "code_selector": "input[name='code']",
        "code_submit_selector": "button[type='submit']",
        "from_filter": "",
        "subject_filter": "",
        "prefer_link": False,
        "timeout_sec": 180,
        "verify_selectors": ["a[href*='dashboard']", "button[aria-label*='profile']"],
        "require_verify": False,
        "screenshot_path": "/tmp/webop_generic_signup.png",
    },
}


class WebOperatorPack:
    def __init__(self, agent_registry):
        self.registry = agent_registry
        self.facts = ExecutionFacts()

    def list_scenarios(self) -> list[str]:
        return sorted(SCENARIOS.keys())

    async def run(self, name: str, overrides: dict | None = None) -> dict:
        if name not in SCENARIOS:
            return {"status": "error", "error": f"unknown_scenario:{name}"}
        scenario = dict(SCENARIOS[name])
        if overrides:
            for k, v in overrides.items():
                if isinstance(v, dict) and isinstance(scenario.get(k), dict):
                    merged = dict(scenario[k])
                    merged.update(v)
                    scenario[k] = merged
                else:
                    scenario[k] = v
        task_type = scenario.pop("task_type", "register_with_email")
        result = await self.registry.dispatch(task_type, **scenario)
        ok = bool(result and result.success)
        out = result.output if result else {}
        err = getattr(result, "error", "") if result else "dispatch_failed"
        evidence = ""
        if isinstance(out, dict):
            evidence = str(out.get("screenshot_path") or out.get("url") or "")
        self.facts.record(
            action="webop:scenario",
            status="success" if ok else "failed",
            detail=f"{name} task={task_type}",
            evidence=evidence,
            source="web_operator_pack",
            evidence_dict={"scenario": name, "output": out if isinstance(out, dict) else {"value": str(out)[:200]}},
        )
        return {
            "status": "success" if ok else "failed",
            "scenario": name,
            "task_type": task_type,
            "output": out,
            "error": err,
        }
