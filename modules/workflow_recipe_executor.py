"""Executable workflow recipe runner over PublisherQueue with acceptance gate."""

from __future__ import annotations

from typing import Any

from modules.platform_publish_quality import validate_platform_publish_quality
from modules.workflow_recipes import get_workflow_recipe


class WorkflowRecipeExecutor:
    def __init__(self, publisher_queue):
        self.publisher_queue = publisher_queue

    @staticmethod
    def _get_nested(payload: dict[str, Any], dotted: str) -> Any:
        cur: Any = payload
        for part in str(dotted or "").split("."):
            if not part:
                continue
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    @staticmethod
    def _evidence_value(result: dict[str, Any], key: str) -> str:
        alias_map = {
            "screenshot": ("screenshot", "screenshot_path"),
            "path": ("path", "file_path"),
            "id": ("id", "listing_id", "product_id", "tweet_id", "post_id"),
            "url": ("url", "public_url", "product_url", "post_url", "tweet_url"),
        }
        for alias in alias_map.get(str(key or "").strip(), (str(key or "").strip(),)):
            direct = str(result.get(alias) or "").strip()
            if direct:
                return direct
        ev = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        for alias in alias_map.get(str(key or "").strip(), (str(key or "").strip(),)):
            val = str(ev.get(alias) or "").strip()
            if val:
                return val
        return ""

    @staticmethod
    def _has_required_evidence(result: dict[str, Any], required_keys: list[str]) -> bool:
        if not isinstance(result, dict):
            return False
        for key in (required_keys or []):
            if WorkflowRecipeExecutor._evidence_value(result, key):
                continue
            return False
        return True

    @staticmethod
    def _validate_acceptance(result: dict[str, Any], recipe: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(result, dict):
            return False, "result_not_dict"
        status = str(result.get("status") or "").strip().lower()
        dry_run = bool((payload or {}).get("dry_run"))
        if dry_run:
            return True, ""

        accepted_statuses = [str(x).strip().lower() for x in (recipe.get("accepted_statuses") or []) if str(x).strip()]
        if accepted_statuses and status not in accepted_statuses:
            return False, f"status_not_accepted:{status}"

        required_evidence = [str(x).strip() for x in (recipe.get("required_evidence") or []) if str(x).strip()]
        if required_evidence and not WorkflowRecipeExecutor._has_required_evidence(result, required_evidence):
            return False, "acceptance_gate_missing_required_evidence"

        url = WorkflowRecipeExecutor._evidence_value(result, "url").lower()
        for bad in (recipe.get("forbidden_url_contains") or []):
            token = str(bad or "").strip().lower()
            if token and token in url:
                return False, f"url_forbidden_token:{token}"
        required_url_tokens = [str(x).strip().lower() for x in (recipe.get("required_url_contains") or []) if str(x).strip()]
        if required_url_tokens and not any(tok in url for tok in required_url_tokens):
            return False, "url_missing_required_token"

        numeric_paths = [str(x).strip() for x in (recipe.get("required_numeric_gt_zero") or []) if str(x).strip()]
        for path in numeric_paths:
            val = WorkflowRecipeExecutor._get_nested(result, path)
            try:
                if float(val or 0) <= 0:
                    return False, f"numeric_not_gt_zero:{path}"
            except Exception:
                return False, f"numeric_invalid:{path}"
        quality_ok, quality_errors = validate_platform_publish_quality(
            str(recipe.get("platform") or ""),
            result or {},
            payload or {},
        )
        if not quality_ok:
            return False, f"publish_quality_gate_failed:{','.join(quality_errors)}"
        return True, ""

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
                if st == "done":
                    return {
                        "status": "failed",
                        "job_id": job_id,
                        "platform": platform,
                        "error": "queue_done_without_result_payload",
                    }
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
        ok, reason = self._validate_acceptance(result, rec, payload or {})
        if not ok:
            return {
                "status": "failed",
                "job_id": job_id,
                "platform": platform,
                "error": reason or "acceptance_gate_failed",
                "result": result,
            }
        return {
            "status": "accepted",
            "job_id": job_id,
            "platform": platform,
            "recipe": recipe_name,
            "result": result,
        }
