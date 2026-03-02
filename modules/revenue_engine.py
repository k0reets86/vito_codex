"""Revenue engine v1: Gumroad-first closed-loop (safe, approval-gated)."""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings
from llm_router import TaskType

logger = get_logger("revenue_engine", agent="revenue_engine")


class RevenueEngine:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS revenue_cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT DEFAULT '',
                    platform TEXT DEFAULT 'gumroad',
                    topic TEXT DEFAULT '',
                    stage TEXT DEFAULT 'init',
                    status TEXT DEFAULT 'running',
                    dry_run INTEGER DEFAULT 1,
                    require_approval INTEGER DEFAULT 1,
                    quality_score REAL DEFAULT 0.0,
                    approval_status TEXT DEFAULT 'pending',
                    publish_job_id INTEGER DEFAULT 0,
                    publish_status TEXT DEFAULT '',
                    analysis_json TEXT DEFAULT '{}',
                    cost_usd REAL DEFAULT 0.0,
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS revenue_cycle_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id INTEGER NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT DEFAULT 'ok',
                    detail TEXT DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_revenue_cycles_status
                ON revenue_cycles(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_revenue_steps_cycle
                ON revenue_cycle_steps(cycle_id, id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _create_cycle(self, topic: str, dry_run: bool, require_approval: bool, trace_id: str) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO revenue_cycles
                (trace_id, platform, topic, stage, status, dry_run, require_approval, updated_at)
                VALUES (?, 'gumroad', ?, 'research', 'running', ?, ?, datetime('now'))
                """,
                (
                    str(trace_id or "")[:120],
                    str(topic or "")[:200],
                    1 if dry_run else 0,
                    1 if require_approval else 0,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _set_cycle(
        self,
        cycle_id: int,
        *,
        stage: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        quality_score: float | None = None,
        approval_status: str | None = None,
        publish_job_id: int | None = None,
        publish_status: str | None = None,
        analysis: dict | None = None,
        cost_usd: float | None = None,
        error: str | None = None,
    ) -> None:
        parts: list[str] = []
        vals: list[Any] = []
        if stage is not None:
            parts.append("stage = ?")
            vals.append(str(stage)[:40])
        if status is not None:
            parts.append("status = ?")
            vals.append(str(status)[:40])
        if topic is not None:
            parts.append("topic = ?")
            vals.append(str(topic)[:200])
        if quality_score is not None:
            parts.append("quality_score = ?")
            vals.append(float(quality_score))
        if approval_status is not None:
            parts.append("approval_status = ?")
            vals.append(str(approval_status)[:40])
        if publish_job_id is not None:
            parts.append("publish_job_id = ?")
            vals.append(int(publish_job_id))
        if publish_status is not None:
            parts.append("publish_status = ?")
            vals.append(str(publish_status)[:40])
        if analysis is not None:
            parts.append("analysis_json = ?")
            vals.append(json.dumps(analysis, ensure_ascii=False)[:8000])
        if cost_usd is not None:
            parts.append("cost_usd = ?")
            vals.append(float(cost_usd))
        if error is not None:
            parts.append("error = ?")
            vals.append(str(error)[:500])
        parts.append("updated_at = datetime('now')")
        vals.append(int(cycle_id))
        conn = self._conn()
        try:
            conn.execute(
                f"UPDATE revenue_cycles SET {', '.join(parts)} WHERE id = ?",
                tuple(vals),
            )
            conn.commit()
        finally:
            conn.close()

    def _add_step(self, cycle_id: int, step_name: str, status: str, detail: str = "", payload: dict | None = None) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO revenue_cycle_steps (cycle_id, step_name, status, detail, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(cycle_id),
                    str(step_name)[:80],
                    str(status)[:20],
                    str(detail or "")[:500],
                    json.dumps(payload or {}, ensure_ascii=False)[:5000],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_cycles(self, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM revenue_cycles WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (str(status)[:40], int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM revenue_cycles ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def summarize_cycles(self, days: int = 30) -> dict:
        conn = self._conn()
        try:
            window = f"-{max(1, int(days or 30))} day"
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_cycles,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_cycles,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_cycles,
                    SUM(CASE WHEN approval_status = 'rejected' THEN 1 ELSE 0 END) AS approval_rejections,
                    SUM(CASE WHEN publish_status != 'done' AND stage = 'publish' THEN 1 ELSE 0 END) AS publish_failures,
                    AVG(quality_score) AS avg_quality_score,
                    AVG(cost_usd) AS avg_cost_usd,
                    SUM(cost_usd) AS total_cost_usd
                FROM revenue_cycles
                WHERE created_at >= datetime('now', ?)
                """,
                (window,),
            ).fetchone()
            stats = dict(row or {})
            total_cycles = int(stats.get("total_cycles") or 0)
            completed_cycles = int(stats.get("completed_cycles") or 0)
            completion_rate = (float(completed_cycles) / float(total_cycles)) if total_cycles > 0 else 0.0
            return {
                "window_days": int(days or 30),
                "total_cycles": total_cycles,
                "completed_cycles": completed_cycles,
                "failed_cycles": int(stats.get("failed_cycles") or 0),
                "approval_rejections": int(stats.get("approval_rejections") or 0),
                "publish_failures": int(stats.get("publish_failures") or 0),
                "completion_rate": round(completion_rate, 4),
                "avg_quality_score": round(float(stats.get("avg_quality_score") or 0.0), 4),
                "avg_cost_usd": round(float(stats.get("avg_cost_usd") or 0.0), 6),
                "total_cost_usd": round(float(stats.get("total_cost_usd") or 0.0), 6),
            }
        finally:
            conn.close()

    def get_cycle(self, cycle_id: int) -> dict:
        conn = self._conn()
        try:
            c = conn.execute("SELECT * FROM revenue_cycles WHERE id = ?", (int(cycle_id),)).fetchone()
            steps = conn.execute(
                "SELECT * FROM revenue_cycle_steps WHERE cycle_id = ? ORDER BY id ASC",
                (int(cycle_id),),
            ).fetchall()
            return {
                "cycle": dict(c) if c else {},
                "steps": [dict(s) for s in steps],
            }
        finally:
            conn.close()

    @staticmethod
    def _json_or_empty(raw: Any) -> dict:
        if isinstance(raw, dict):
            return raw
        txt = str(raw or "").strip()
        if not txt:
            return {}
        try:
            parsed = json.loads(txt)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def build_cycle_report(self, cycle_id: int) -> dict:
        data = self.get_cycle(cycle_id)
        cycle = data.get("cycle") or {}
        steps = data.get("steps") or []
        analysis = self._json_or_empty(cycle.get("analysis_json"))
        failed_steps = [s for s in steps if str(s.get("status", "")).lower() not in {"ok", "done", "completed"}]
        report = {
            "cycle_id": int(cycle.get("id") or cycle_id),
            "trace_id": str(cycle.get("trace_id") or ""),
            "platform": str(cycle.get("platform") or "gumroad"),
            "topic": str(cycle.get("topic") or ""),
            "status": str(cycle.get("status") or "unknown"),
            "stage": str(cycle.get("stage") or ""),
            "dry_run": bool(int(cycle.get("dry_run") or 0)),
            "require_approval": bool(int(cycle.get("require_approval") or 0)),
            "quality_score": float(cycle.get("quality_score") or 0.0),
            "approval_status": str(cycle.get("approval_status") or ""),
            "publish_status": str(cycle.get("publish_status") or ""),
            "publish_job_id": int(cycle.get("publish_job_id") or 0),
            "cost_usd": float(cycle.get("cost_usd") or 0.0),
            "error": str(cycle.get("error") or ""),
            "created_at": str(cycle.get("created_at") or ""),
            "updated_at": str(cycle.get("updated_at") or ""),
            "analysis": analysis,
            "steps_total": len(steps),
            "steps_failed": len(failed_steps),
            "failed_steps": [
                {
                    "step_name": str(s.get("step_name") or ""),
                    "status": str(s.get("status") or ""),
                    "detail": str(s.get("detail") or ""),
                    "created_at": str(s.get("created_at") or ""),
                }
                for s in failed_steps
            ][:8],
            "steps": steps,
        }
        return report

    def render_cycle_report_markdown(self, cycle_id: int) -> str:
        report = self.build_cycle_report(cycle_id)
        lines = [
            f"# Revenue Cycle Report #{report['cycle_id']}",
            "",
            f"- Trace: `{report['trace_id']}`",
            f"- Platform: `{report['platform']}`",
            f"- Topic: {report['topic'] or '-'}",
            f"- Status: `{report['status']}` (stage: `{report['stage']}`)",
            f"- Mode: `{'DRY-RUN' if report['dry_run'] else 'LIVE'}`",
            f"- Approval: `{report['approval_status']}` (required: `{report['require_approval']}`)",
            f"- Publish: `{report['publish_status']}` (job: `{report['publish_job_id']}`)",
            f"- Quality score: `{report['quality_score']:.2f}`",
            f"- Cost USD: `{report['cost_usd']:.4f}`",
            f"- Created: `{report['created_at']}`",
            f"- Updated: `{report['updated_at']}`",
        ]
        if report["error"]:
            lines.extend(["", "## Error", f"- {report['error']}"])
        lines.extend(["", "## Steps"])
        for step in report.get("steps", [])[:20]:
            lines.append(
                f"- `{step.get('step_name','')}`: `{step.get('status','')}`"
                + (f" — {str(step.get('detail') or '')}" if step.get("detail") else "")
            )
        analysis = report.get("analysis") or {}
        if analysis:
            lines.extend(["", "## Analysis", "```json", json.dumps(analysis, ensure_ascii=False, indent=2)[:4000], "```"])
        return "\n".join(lines).strip() + "\n"

    def persist_cycle_report(self, cycle_id: int, out_path: str = "") -> dict:
        report = self.build_cycle_report(cycle_id)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_name = f"revenue_cycle_{int(report.get('cycle_id') or cycle_id)}_{ts}.md"
        target = Path(out_path.strip()) if str(out_path or "").strip() else Path("runtime/reports/revenue") / default_name
        target.parent.mkdir(parents=True, exist_ok=True)
        markdown = self.render_cycle_report_markdown(cycle_id)
        target.write_text(markdown, encoding="utf-8")
        return {"ok": True, "path": str(target), "cycle_id": int(report.get("cycle_id") or cycle_id), "status": report.get("status", "")}

    @staticmethod
    def _is_valid_publish_evidence(value: str) -> bool:
        ev = str(value or "").strip()
        if not ev:
            return False
        if ev.startswith(("https://", "http://")):
            return True
        if ev.startswith("/"):
            return Path(ev).exists()
        return False

    @staticmethod
    def _build_iteration_actions(analysis: dict) -> list[str]:
        actions: list[str] = []
        q = analysis.get("queue_stats", {}) if isinstance(analysis, dict) else {}
        publish_status = str(analysis.get("publish_status", "") or "").lower() if isinstance(analysis, dict) else ""
        ev = str(analysis.get("publish_evidence", "") or "").strip() if isinstance(analysis, dict) else ""
        sales = analysis.get("sales", {}) if isinstance(analysis, dict) else {}
        gumroad_sales = 0
        gumroad_revenue = 0.0
        if isinstance(sales, dict):
            g = sales.get("gumroad", sales)
            if isinstance(g, dict):
                gumroad_sales = int(g.get("sales", 0) or 0)
                gumroad_revenue = float(g.get("revenue", 0.0) or 0.0)

        if publish_status != "done":
            actions.append("Investigate publish failure and rerun cycle in DRY-RUN mode first.")
        elif not ev:
            actions.append("Capture missing publish evidence (public URL/screenshot) before next LIVE run.")
        else:
            actions.append("Archive publish evidence and link it to owner report.")

        if gumroad_sales <= 0:
            actions.append("Run low-cost marketing test: 1 Reddit post + 1 X/Twitter post + update Gumroad title copy.")
            actions.append("Prepare one variant of pricing/copy and schedule A/B test in next cycle.")
        else:
            actions.append("Scale winning offer: duplicate listing into a variant pack and keep price anchor.")
            actions.append(f"Track conversion and retention against baseline revenue ${gumroad_revenue:.2f}.")

        failed = int(q.get("failed", 0) or 0)
        queued = int(q.get("queued", 0) or 0)
        if failed > 0 or queued > 0:
            actions.append("Drain failed/queued publish jobs and verify platform auth/session health.")
        return actions[:6]

    @staticmethod
    def _live_publish_precheck() -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not bool(getattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_AUTH", True)):
            return True, issues
        has_auth = bool(
            getattr(settings, "GUMROAD_API_KEY", "")
            or getattr(settings, "GUMROAD_OAUTH_TOKEN", "")
            or (getattr(settings, "GUMROAD_EMAIL", "") and getattr(settings, "GUMROAD_PASSWORD", ""))
        )
        if not has_auth:
            issues.append("gumroad_auth_missing")
        return (len(issues) == 0), issues

    @staticmethod
    def _publish_precheck(*, dry_run: bool, publisher_queue) -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not publisher_queue:
            issues.append("publisher_queue_unavailable")
            return False, issues
        queue_platforms = getattr(publisher_queue, "platforms", None)
        if isinstance(queue_platforms, dict) and "gumroad" not in queue_platforms:
            issues.append("publisher_queue_missing_gumroad_adapter")
        if not dry_run:
            live_ok, live_issues = RevenueEngine._live_publish_precheck()
            if not live_ok:
                issues.extend(live_issues)
            queue_stats = {}
            stats_available = False
            stats_non_dict = False
            try:
                stats_fn = getattr(publisher_queue, "stats", None)
                if callable(stats_fn):
                    raw_stats = stats_fn()
                    if isinstance(raw_stats, dict):
                        queue_stats = raw_stats
                        stats_available = True
                    elif raw_stats is not None:
                        stats_non_dict = True
            except Exception:
                queue_stats = {}
                stats_available = False
            if bool(getattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", True)) and not stats_available:
                issues.append("publisher_queue_stats_unavailable")
            max_failed = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", 0) or 0))
            max_queued = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", 20) or 20))
            max_running = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_RUNNING", 10) or 10))
            max_total = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_TOTAL", 40) or 40))
            max_fail_rate = max(0.0, float(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", 0.0) or 0.0))
            fail_rate_min_total = max(1, int(getattr(settings, "REVENUE_ENGINE_LIVE_FAIL_RATE_MIN_TOTAL", 1) or 1))
            max_queued_age_sec = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_QUEUED_AGE_SEC", 0) or 0))
            max_running_age_sec = max(0, int(getattr(settings, "REVENUE_ENGINE_LIVE_MAX_RUNNING_AGE_SEC", 0) or 0))
            invalid_stats_fields: list[str] = []
            if stats_non_dict:
                invalid_stats_fields.append("stats_non_dict")
            required_stats_keys = ("failed", "queued", "running", "total")
            if stats_available and any(k not in queue_stats for k in required_stats_keys):
                invalid_stats_fields.append("missing_required_keys")

            def _coerce_stat_int(field: str) -> int:
                raw = queue_stats.get(field, 0)
                if raw in (None, ""):
                    return 0
                try:
                    if isinstance(raw, bool):
                        return int(raw)
                    if isinstance(raw, int):
                        return int(raw)
                    if isinstance(raw, float):
                        if not math.isfinite(raw):
                            raise ValueError("non_finite")
                        return int(raw)
                    txt = str(raw).strip()
                    if not txt:
                        return 0
                    parsed = float(txt)
                    if not math.isfinite(parsed):
                        raise ValueError("non_finite")
                    return int(parsed)
                except Exception:
                    invalid_stats_fields.append(f"{field}_parse")
                    return 0

            failed_n = _coerce_stat_int("failed")
            queued_n = _coerce_stat_int("queued")
            running_n = _coerce_stat_int("running")
            done_n = _coerce_stat_int("done")
            total_n = _coerce_stat_int("total")
            oldest_queued_sec = _coerce_stat_int("oldest_queued_sec")
            oldest_running_sec = _coerce_stat_int("oldest_running_sec")
            for key, val in (
                ("failed", failed_n),
                ("queued", queued_n),
                ("running", running_n),
                ("done", done_n),
                ("total", total_n),
                ("oldest_queued_sec", oldest_queued_sec),
                ("oldest_running_sec", oldest_running_sec),
            ):
                if int(val) < 0:
                    invalid_stats_fields.append(key)
            active_n = failed_n + queued_n + running_n
            if total_n > 0 and total_n < active_n:
                invalid_stats_fields.append("total_lt_active")
            accounted_n = failed_n + queued_n + running_n + done_n
            if total_n > 0 and total_n < accounted_n:
                invalid_stats_fields.append("total_lt_accounted")
            if total_n > 0 and accounted_n == 0:
                invalid_stats_fields.append("total_with_zero_counters")
            if total_n == 0 and accounted_n > 0:
                invalid_stats_fields.append("total_zero_with_activity")
            if queued_n == 0 and oldest_queued_sec > 0:
                invalid_stats_fields.append("queued_age_without_queue")
            if running_n == 0 and oldest_running_sec > 0:
                invalid_stats_fields.append("running_age_without_running")
            if invalid_stats_fields:
                issues.append(f"publisher_queue_stats_invalid:{','.join(invalid_stats_fields[:4])}")
            if failed_n > max_failed:
                issues.append(f"publisher_queue_failed_backlog:{failed_n}>{max_failed}")
            if queued_n > max_queued:
                issues.append(f"publisher_queue_queued_backlog:{queued_n}>{max_queued}")
            if running_n > max_running:
                issues.append(f"publisher_queue_running_backlog:{running_n}>{max_running}")
            if total_n > max_total:
                issues.append(f"publisher_queue_total_backlog:{total_n}>{max_total}")
            if max_fail_rate > 0 and total_n >= fail_rate_min_total:
                fail_rate = float(failed_n) / float(total_n)
                if fail_rate > max_fail_rate:
                    issues.append(f"publisher_queue_fail_rate:{fail_rate:.4f}>{max_fail_rate:.4f}")
            if max_queued_age_sec > 0 and oldest_queued_sec > max_queued_age_sec:
                issues.append(f"publisher_queue_queued_age:{oldest_queued_sec}>{max_queued_age_sec}")
            if max_running_age_sec > 0 and oldest_running_sec > max_running_age_sec:
                issues.append(f"publisher_queue_running_age:{oldest_running_sec}>{max_running_age_sec}")
            if bool(getattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", False)):
                adapter = queue_platforms.get("gumroad") if isinstance(queue_platforms, dict) else None
                if not adapter:
                    issues.append("gumroad_browser_adapter_missing")
                elif getattr(adapter, "browser_agent", None) is None:
                    issues.append("gumroad_browser_runtime_unavailable")
            if bool(getattr(settings, "REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", False)):
                cookie_file = Path(str(getattr(settings, "GUMROAD_SESSION_COOKIE_FILE", "/tmp/gumroad_cookie.txt") or "/tmp/gumroad_cookie.txt"))
                try:
                    if (not cookie_file.exists()) or (not cookie_file.read_text(encoding="utf-8").strip()):
                        issues.append("gumroad_session_cookie_missing")
                except Exception:
                    issues.append("gumroad_session_cookie_unreadable")
        return (len(issues) == 0), issues

    @staticmethod
    async def _publish_precheck_async(*, dry_run: bool, publisher_queue) -> tuple[bool, list[str]]:
        ok, issues = RevenueEngine._publish_precheck(dry_run=dry_run, publisher_queue=publisher_queue)
        if dry_run or not publisher_queue:
            return ok, issues
        if not bool(getattr(settings, "REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", True)):
            return ok, issues
        queue_platforms = getattr(publisher_queue, "platforms", None)
        adapter = queue_platforms.get("gumroad") if isinstance(queue_platforms, dict) else None
        if not adapter:
            return ok, issues
        auth_fn = getattr(adapter, "authenticate", None)
        if not callable(auth_fn):
            return ok, issues
        timeout_sec = max(2, int(getattr(settings, "REVENUE_ENGINE_LIVE_AUTH_TIMEOUT_SEC", 12) or 12))
        try:
            auth_ok = bool(await asyncio.wait_for(auth_fn(), timeout=float(timeout_sec)))
        except asyncio.TimeoutError:
            auth_ok = False
            issues.append("gumroad_adapter_auth_timeout")
        except Exception:
            auth_ok = False
            issues.append("gumroad_adapter_auth_error")
        if not auth_ok and "gumroad_adapter_auth_timeout" not in issues and "gumroad_adapter_auth_error" not in issues:
            issues.append("gumroad_adapter_auth_failed")
        return (len(issues) == 0), issues

    async def run_gumroad_cycle(
        self,
        *,
        registry=None,
        llm_router=None,
        comms=None,
        publisher_queue=None,
        topic: str = "",
        dry_run: bool = True,
        require_approval: bool = True,
    ) -> dict:
        trace_id = f"revenue_cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        cycle_id = self._create_cycle(topic=topic, dry_run=dry_run, require_approval=require_approval, trace_id=trace_id)
        cost_usd = 0.0
        try:
            # 1) research
            self._set_cycle(cycle_id, stage="research")
            research_text = ""
            if registry:
                res = await registry.dispatch("niche_research")
                if res and res.success:
                    research_text = str(res.output or "")[:4000]
                else:
                    res2 = await registry.dispatch("trend_scan", keywords=["digital products", "gumroad", "ai templates"])
                    if res2 and res2.success:
                        research_text = str(res2.output or "")[:4000]
            if not research_text and llm_router:
                prompt = (
                    "Suggest one realistic digital product topic for Gumroad (USD 5-25), "
                    "based on low-risk, high-demand evergreen niches. Output 1 short topic line."
                )
                response = await llm_router.call_llm(
                    task_type=TaskType.RESEARCH,
                    prompt=prompt,
                    estimated_tokens=300,
                )
                research_text = str(response or "").strip()[:4000]
                cost_usd += 0.003
            if not research_text:
                self._add_step(cycle_id, "research", "failed", "research_unavailable")
                self._set_cycle(cycle_id, status="failed", error="research_unavailable")
                return {"ok": False, "cycle_id": cycle_id, "error": "research_unavailable"}
            self._add_step(cycle_id, "research", "ok", payload={"sample": research_text[:500]})

            # topic normalization
            normalized_topic = str(topic or "").strip()
            if not normalized_topic:
                first_line = research_text.splitlines()[0].strip()
                normalized_topic = (first_line or "AI Side Hustle Starter Pack")[:120]
            self._set_cycle(cycle_id, topic=normalized_topic)

            # 2) propose
            self._set_cycle(cycle_id, stage="propose")
            proposal = ""
            if registry:
                desc = await registry.dispatch(
                    "product_description",
                    product=normalized_topic,
                    platform="gumroad",
                )
                if desc and desc.success:
                    proposal = str(desc.output or "")[:8000]
            if not proposal and llm_router:
                prompt = (
                    "Create a Gumroad digital product proposal in ENGLISH.\n"
                    f"Topic: {normalized_topic}\n"
                    "Return: title, 5 bullet benefits, short summary, price recommendation (5-25 USD)."
                )
                proposal = str(
                    await llm_router.call_llm(
                        task_type=TaskType.CONTENT,
                        prompt=prompt,
                        estimated_tokens=800,
                    )
                    or ""
                )[:8000]
                cost_usd += 0.006
            if not proposal:
                self._add_step(cycle_id, "propose", "failed", "proposal_unavailable")
                self._set_cycle(cycle_id, status="failed", error="proposal_unavailable")
                return {"ok": False, "cycle_id": cycle_id, "error": "proposal_unavailable"}
            self._add_step(cycle_id, "propose", "ok", payload={"sample": proposal[:500]})

            # 3) quality
            self._set_cycle(cycle_id, stage="quality")
            quality_score = 7.0
            quality_ok = True
            if registry:
                qr = await registry.dispatch(
                    "quality_review",
                    content=proposal,
                    content_type="product_description",
                )
                if qr and qr.success and isinstance(qr.output, dict):
                    quality_score = float(qr.output.get("score", 7) or 7)
                    quality_ok = bool(qr.output.get("approved", quality_score >= 7))
            self._set_cycle(cycle_id, quality_score=quality_score)
            self._add_step(
                cycle_id,
                "quality",
                "ok" if quality_ok else "failed",
                detail=f"score={quality_score:.2f}",
            )
            if not quality_ok:
                self._set_cycle(cycle_id, status="failed", error="quality_below_threshold")
                return {"ok": False, "cycle_id": cycle_id, "error": "quality_below_threshold", "quality_score": quality_score}

            # 4) approval
            self._set_cycle(cycle_id, stage="approval")
            approval_status = "skipped"
            if require_approval:
                approval_status = "pending"
                if not comms:
                    self._add_step(cycle_id, "approval", "failed", "comms_unavailable")
                    self._set_cycle(cycle_id, status="failed", approval_status="failed", error="approval_channel_unavailable")
                    return {"ok": False, "cycle_id": cycle_id, "error": "approval_channel_unavailable"}
                req_id = f"revenue_gumroad_{cycle_id}_{uuid.uuid4().hex[:6]}"
                msg = (
                    "[Revenue Cycle v1] Запрос на шаг create/publish.\n"
                    f"Topic: {normalized_topic}\n"
                    f"Quality score: {quality_score:.2f}\n"
                    f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}\n"
                    "Одобрить запуск пайплайна publish?"
                )
                approved = await comms.request_approval(req_id, msg, timeout_seconds=1800)
                if approved is True:
                    approval_status = "approved"
                elif approved is False:
                    approval_status = "rejected"
                else:
                    approval_status = "timeout"
            self._set_cycle(cycle_id, approval_status=approval_status)
            self._add_step(cycle_id, "approval", "ok" if approval_status in {"approved", "skipped"} else "failed", detail=approval_status)
            if approval_status not in {"approved", "skipped"}:
                self._set_cycle(cycle_id, status="failed", error=f"approval_{approval_status}")
                return {"ok": False, "cycle_id": cycle_id, "error": f"approval_{approval_status}"}

            # 5) create/publish (gumroad-first via durable queue)
            self._set_cycle(cycle_id, stage="publish")
            ok_precheck, precheck_issues = await self._publish_precheck_async(dry_run=bool(dry_run), publisher_queue=publisher_queue)
            if not ok_precheck:
                detail = ",".join(precheck_issues[:6])[:220]
                self._add_step(cycle_id, "publish", "failed", f"publish_precheck_failed:{detail}")
                self._set_cycle(cycle_id, status="failed", error=f"publish_precheck_failed:{detail}")
                return {"ok": False, "cycle_id": cycle_id, "error": f"publish_precheck_failed:{detail}"}
            publish_payload = {
                "name": normalized_topic[:80],
                "description": proposal[:3000],
                "summary": proposal[:220],
                "price": 9,
                "dry_run": bool(dry_run),
            }
            job_id = int(
                publisher_queue.enqueue(
                    "gumroad",
                    publish_payload,
                    max_attempts=1,
                    trace_id=trace_id,
                )
            )
            publish_timeout = max(1, int(getattr(settings, "REVENUE_ENGINE_PUBLISH_TIMEOUT_SEC", 45) or 45))
            try:
                await asyncio.wait_for(publisher_queue.process_all(limit=20), timeout=float(publish_timeout))
            except asyncio.TimeoutError:
                self._add_step(cycle_id, "publish", "failed", f"publisher_queue_timeout:{publish_timeout}s")
                self._set_cycle(cycle_id, status="failed", error=f"publisher_queue_timeout:{publish_timeout}s")
                return {"ok": False, "cycle_id": cycle_id, "error": f"publisher_queue_timeout:{publish_timeout}s", "publish_job_id": job_id}
            jobs = publisher_queue.list_jobs(limit=200)
            job = next((j for j in jobs if int(j.get("id", 0) or 0) == job_id), {})
            pub_status = str(job.get("status", "unknown") or "unknown")
            publish_evidence = str(job.get("evidence", "") or "").strip()
            self._set_cycle(cycle_id, publish_job_id=job_id, publish_status=pub_status)
            self._add_step(
                cycle_id,
                "publish",
                "ok" if pub_status == "done" else "failed",
                detail=f"job={job_id} status={pub_status}",
                payload={"job_id": job_id, "status": pub_status, "evidence": publish_evidence},
            )
            if pub_status != "done":
                self._set_cycle(cycle_id, status="failed", error=f"publish_{pub_status}")
                return {"ok": False, "cycle_id": cycle_id, "error": f"publish_{pub_status}", "publish_job_id": job_id}
            if not dry_run and not publish_evidence:
                self._set_cycle(cycle_id, status="failed", error="publish_missing_evidence")
                return {
                    "ok": False,
                    "cycle_id": cycle_id,
                    "error": "publish_missing_evidence",
                    "publish_job_id": job_id,
                }
            if not dry_run and not self._is_valid_publish_evidence(publish_evidence):
                self._set_cycle(cycle_id, status="failed", error="publish_invalid_evidence")
                return {
                    "ok": False,
                    "cycle_id": cycle_id,
                    "error": "publish_invalid_evidence",
                    "publish_job_id": job_id,
                }

            # 6) analyze
            self._set_cycle(cycle_id, stage="analyze")
            analysis = {
                "publish_job_id": job_id,
                "publish_status": pub_status,
                "publish_evidence": publish_evidence,
                "queue_stats": publisher_queue.stats(),
            }
            if registry:
                sales = await registry.dispatch("sales_check", platform="gumroad")
                if sales and sales.success:
                    analysis["sales"] = sales.output
            analysis["iterate_actions"] = self._build_iteration_actions(analysis)
            self._add_step(cycle_id, "analyze", "ok", payload=analysis)
            self._set_cycle(
                cycle_id,
                status="completed",
                analysis=analysis,
                cost_usd=round(cost_usd, 6),
            )
            report_path = ""
            if bool(getattr(settings, "REVENUE_ENGINE_AUTO_REPORT_ENABLED", True)):
                try:
                    base_dir = str(getattr(settings, "REVENUE_ENGINE_REPORT_DIR", "runtime/reports/revenue") or "runtime/reports/revenue").strip()
                    save = self.persist_cycle_report(cycle_id=cycle_id, out_path=str(Path(base_dir) / f"revenue_cycle_{cycle_id}_latest.md"))
                    report_path = str(save.get("path", "") or "")
                except Exception:
                    report_path = ""
            return {
                "ok": True,
                "cycle_id": cycle_id,
                "status": "completed",
                "topic": normalized_topic,
                "quality_score": quality_score,
                "approval_status": approval_status,
                "publish_job_id": job_id,
                "analysis": analysis,
                "report_path": report_path,
            }
        except Exception as e:
            self._add_step(cycle_id, "runtime", "failed", str(e))
            self._set_cycle(cycle_id, status="failed", error=str(e), cost_usd=round(cost_usd, 6))
            logger.warning(f"Revenue cycle failed: {e}", extra={"event": "revenue_cycle_failed", "context": {"cycle_id": cycle_id}})
            return {"ok": False, "cycle_id": cycle_id, "error": str(e)}
