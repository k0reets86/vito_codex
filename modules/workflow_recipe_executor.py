"""Executable workflow recipe runner over PublisherQueue with acceptance gate."""

from __future__ import annotations

from typing import Any

from modules.workflow_recipes import get_workflow_recipe


class WorkflowRecipeExecutor:
    def __init__(self, publisher_queue):
        self.publisher_queue = publisher_queue

    @staticmethod
    def _has_required_evidence(result: dict[str, Any], required_keys: list[str]) -> bool:
        if not isinstance(result, dict):
            return False
        for key in (required_keys or []):
            if str(result.get(key) or "").strip():
                continue
            # nested evidence object fallback
            ev = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
            if str(ev.get(key) or "").strip():
                continue
            return False
        return True

    async def run_once(self, recipe_name: str, payload: dict[str, Any], trace_id: str = "") -> dict[str, Any]:
        if not self.publisher_queue:
            return {"status": "error", "error": "publisher_queue_missing"}
        rec = get_workflow_recipe(recipe_name)
        if not rec:
            return {"status": "error", "error": "recipe_not_found", "recipe": recipe_name}
        platform = str(rec.get("platform") or "").strip().lower()
        if not platform:
            return {"status": "error", "error": "recipe_platform_missing", "recipe": recipe_name}

        job_id = int(self.publisher_queue.enqueue(platform=platform, payload=payload or {}, max_attempts=1, trace_id=trace_id))
        out = await self.publisher_queue.process_once()
        if not isinstance(out, dict) or int(out.get("job_id") or 0) != job_id:
            # queue can process different item if prefilled; fallback by lookup
            rows = self.publisher_queue.list_jobs(limit=20)
            row = next((r for r in rows if int(r.get("id") or 0) == job_id), None)
            if row:
                st = str(row.get("status") or "")
                evidence = str(row.get("evidence") or "")
                if st == "done" and evidence:
                    return {"status": "accepted", "job_id": job_id, "platform": platform, "evidence": evidence}
                return {"status": "failed", "job_id": job_id, "platform": platform, "error": str(row.get("last_error") or st)}
            return {"status": "failed", "job_id": job_id, "platform": platform, "error": "job_not_found_after_process"}

        if str(out.get("status") or "").lower() != "done":
            return {
                "status": "failed",
                "job_id": job_id,
                "platform": platform,
                "error": str(out.get("error") or "recipe_execution_failed"),
                "result": out,
            }
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        required = [str(x) for x in (rec.get("required_evidence") or []) if str(x).strip()]
        if not self._has_required_evidence(result, required):
            return {
                "status": "failed",
                "job_id": job_id,
                "platform": platform,
                "error": "acceptance_gate_missing_required_evidence",
                "required": required,
                "result": result,
            }
        return {
            "status": "accepted",
            "job_id": job_id,
            "platform": platform,
            "recipe": recipe_name,
            "result": result,
        }

