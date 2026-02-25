"""Simple dashboard server for VITO (no external deps).

Provides:
- /         HTML dashboard
- /api/status
- /api/agents
- /api/goals
- /api/finance
- /api/schedules
- /api/prefs
- /api/memory_policy
- /api/platforms
- /api/config (GET/POST)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from config.settings import settings
from memory.memory_manager import MemoryManager
from modules.operator_policy import OperatorPolicy
from modules.owner_preference_model import OwnerPreferenceModel
from modules.owner_pref_metrics import OwnerPreferenceMetrics
from modules.self_learning import SelfLearningEngine



class DashboardServer:
    def __init__(self, goal_engine=None, decision_loop=None, finance=None, registry=None, schedule_manager=None, platform_registry=None, llm_router=None, publisher_queue=None, comms=None):
        self.goal_engine = goal_engine
        self.decision_loop = decision_loop
        self.finance = finance
        self.registry = registry
        self.schedule_manager = schedule_manager
        self.platform_registry = platform_registry
        self.llm_router = llm_router
        self.publisher_queue = publisher_queue
        self.comms = comms
        self._server = None
        self._thread = None

    def _auth_ok(self, query: dict, headers: dict) -> bool:
        token = getattr(settings, "DASHBOARD_TOKEN", "")
        if not token:
            return True
        qtoken = query.get("token", [""])[0]
        htoken = headers.get("X-Auth-Token", "")
        return qtoken == token or htoken == token

    def _build_handler(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, payload: dict, code: int = 200):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _text(self, text: str, code: int = 200):
                body = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _html(self, html: str, code: int = 200):
                body = html.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not parent._auth_ok(query, self.headers):
                    self._text("Unauthorized", 401)
                    return

                if parsed.path == "/api/status":
                    payload = {}
                    if parent.decision_loop:
                        payload["decision_loop"] = parent.decision_loop.get_status()
                    if parent.goal_engine:
                        payload["goals"] = parent.goal_engine.get_stats()
                    self._json(payload)
                    return
                if parsed.path == "/api/network":
                    try:
                        from modules.network_utils import basic_net_report
                        report = basic_net_report(["api.telegram.org", "gumroad.com", "google.com"])
                    except Exception:
                        report = {"ok": False, "reason": "net_check_failed"}
                    self._json({"network": report})
                    return

                if parsed.path == "/api/agents":
                    agents = []
                    if parent.registry:
                        for a in parent.registry.list_agents():
                            agents.append(a.get_status())
                    self._json({"agents": agents})
                    return

                if parsed.path == "/api/goals":
                    goals = []
                    if parent.goal_engine:
                        try:
                            parent.goal_engine.reload_goals()
                        except Exception:
                            pass
                        for g in parent.goal_engine.get_all_goals():
                            goals.append({
                                "goal_id": g.goal_id,
                                "title": g.title,
                                "status": g.status.value,
                                "priority": g.priority.name,
                                "estimated_cost": g.estimated_cost_usd,
                            })
                    self._json({"goals": goals})
                    return

                if parsed.path == "/api/finance":
                    if parent.finance:
                        payload = parent.finance.get_summary()
                    else:
                        payload = {}
                    self._json(payload)
                    return

                if parsed.path == "/api/schedules":
                    tasks = []
                    if parent.schedule_manager:
                        for t in parent.schedule_manager.list_tasks():
                            tasks.append(t.__dict__)
                    self._json({"tasks": tasks})
                    return
                if parsed.path == "/api/prefs":
                    try:
                        prefs = OwnerPreferenceModel().list_preferences(limit=50)
                    except Exception:
                        prefs = []
                    self._json({"preferences": prefs})
                    return
                if parsed.path == "/api/prefs_metrics":
                    try:
                        metrics = OwnerPreferenceMetrics().summary()
                    except Exception:
                        metrics = {}
                    self._json({"metrics": metrics})
                    return
                if parsed.path == "/api/capability_packs":
                    try:
                        from pathlib import Path
                        root = Path(__file__).resolve().parent / "capability_packs"
                        items = []
                        for spec in root.glob("*/spec.json"):
                            try:
                                data = json.loads(spec.read_text(encoding="utf-8"))
                            except Exception:
                                continue
                            items.append({
                                "name": data.get("name") or spec.parent.name,
                                "category": data.get("category", ""),
                                "status": data.get("acceptance_status", "pending"),
                                "risk": data.get("risk_score", 0),
                            })
                    except Exception:
                        items = []
                    self._json({"packs": items})
                    return
                if parsed.path == "/api/skills":
                    try:
                        from modules.skill_registry import SkillRegistry
                        skills = SkillRegistry().list_skills(limit=200)
                    except Exception:
                        skills = []
                    self._json({"skills": skills})
                    return
                if parsed.path == "/api/operator_policy":
                    try:
                        op = OperatorPolicy()
                        tools = op.list_tool_policies(limit=200)
                        budgets = op.list_budget_policies(limit=200)
                    except Exception:
                        tools, budgets = [], []
                    self._json({"tools": tools, "budgets": budgets})
                    return
                if parsed.path == "/api/self_learning":
                    try:
                        sl = SelfLearningEngine()
                        lessons = sl.list_lessons(limit=100)
                        candidates = sl.list_candidates(limit=100)
                    except Exception:
                        lessons, candidates = [], []
                    self._json({"lessons": lessons, "candidates": candidates})
                    return
                if parsed.path == "/api/memory_policy":
                    try:
                        action = (query.get("action", [""])[0] or "").strip()
                        limit = int(query.get("limit", ["100"])[0] or 100)
                        days = int(query.get("days", ["30"])[0] or 30)
                        audit = MemoryManager().get_memory_policy_audit(limit=limit, action=action)
                        summary = MemoryManager().get_memory_policy_summary(days=days)
                    except Exception:
                        audit = []
                        summary = {}
                    self._json({"audit": audit, "summary": summary})
                    return
                if parsed.path == "/api/workflow_threads":
                    try:
                        from modules.workflow_threads import WorkflowThreads
                        limit = int(query.get("limit", ["50"])[0] or 50)
                        threads = WorkflowThreads().list_threads(limit=limit)
                    except Exception:
                        threads = []
                    self._json({"threads": threads})
                    return
                if parsed.path == "/api/workflow_interrupts":
                    try:
                        from modules.workflow_interrupts import WorkflowInterrupts
                        status = (query.get("status", [""])[0] or "").strip()
                        limit = int(query.get("limit", ["80"])[0] or 80)
                        interrupts = WorkflowInterrupts().list_interrupts(status=status, limit=limit)
                    except Exception:
                        interrupts = []
                    self._json({"interrupts": interrupts})
                    return

                if parsed.path == "/api/platforms":
                    rows = []
                    if parent.platform_registry:
                        rows = parent.platform_registry.list_platforms()
                    self._json({"platforms": rows})
                    return
                if parsed.path == "/api/publish_queue":
                    try:
                        st = parent.publisher_queue.stats() if parent.publisher_queue else {}
                        jobs = parent.publisher_queue.list_jobs(limit=50) if parent.publisher_queue else []
                    except Exception:
                        st = {}
                        jobs = []
                    self._json({"stats": st, "jobs": jobs})
                    return
                if parsed.path == "/api/platform_scorecard":
                    try:
                        from modules.platform_scorecard import PlatformScorecard
                        rows = PlatformScorecard().score(["gumroad", "etsy", "wordpress", "twitter", "kofi", "printful"], days=30)
                    except Exception:
                        rows = []
                    self._json({"scorecard": rows})
                    return
                if parsed.path == "/api/final_scorecard":
                    try:
                        from modules.final_scorecard import FinalScorecard
                        data = FinalScorecard().calculate()
                    except Exception:
                        data = {}
                    self._json({"final_scorecard": data})
                    return
                if parsed.path == "/api/rss":
                    try:
                        from modules.rss_registry import RSSRegistry
                        rows = RSSRegistry().list_sources()
                    except Exception:
                        rows = []
                    self._json({"sources": rows})
                    return
                if parsed.path == "/api/kpi":
                    try:
                        from modules.data_lake import DataLake
                        dl = DataLake()
                        stats = dl.agent_stats(days=30)
                        summary = dl.kpi_summary(days=30)
                    except Exception:
                        stats = []
                        summary = {}
                    self._json({"agent_kpi": stats, "summary": summary})
                    return
                if parsed.path == "/api/kpi_trend":
                    try:
                        from modules.data_lake import DataLake
                        trend = DataLake().kpi_daily(days=30)
                    except Exception:
                        trend = []
                    self._json({"trend": trend})
                    return
                if parsed.path == "/api/models":
                    disabled = getattr(settings, "LLM_DISABLED_MODELS", "")
                    enabled = getattr(settings, "LLM_ENABLED_MODELS", "")
                    active_profile = getattr(settings, "MODEL_ACTIVE_PROFILE", "balanced")
                    try:
                        from modules.model_profiles import ModelProfiles
                        profiles = ModelProfiles().list_profiles(limit=100)
                    except Exception:
                        profiles = []
                    self._json({
                        "disabled": disabled,
                        "enabled": enabled,
                        "default": getattr(settings, "OPENROUTER_DEFAULT_MODEL", ""),
                        "active_profile": active_profile,
                        "profiles": profiles,
                    })
                    return
                if parsed.path == "/api/secrets_status":
                    keys = [
                        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                        "PERPLEXITY_API_KEY", "OPENROUTER_API_KEY",
                        "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID",
                        "GUMROAD_API_KEY", "GUMROAD_OAUTH_TOKEN", "GUMROAD_APP_ID", "GUMROAD_APP_SECRET",
                        "ETSY_KEYSTRING", "ETSY_SHARED_SECRET", "KOFI_API_KEY", "KOFI_PAGE_ID",
                        "REPLICATE_API_TOKEN", "ANTICAPTCHA_KEY",
                        "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
                        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
                        "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "TIKTOK_ACCESS_TOKEN",
                    ]
                    statuses = []
                    for key in keys:
                        raw = str(getattr(settings, key, "") or "")
                        statuses.append({
                            "key": key,
                            "present": bool(raw.strip()),
                            "preview": (raw[-4:] if raw.strip() else ""),
                        })
                    self._json({"secrets": statuses})
                    return
                if parsed.path == "/api/llm_policy":
                    try:
                        report = parent.llm_router.get_policy_report(days=1) if parent.llm_router else {}
                    except Exception:
                        report = {}
                    self._json({"policy": report})
                    return
                if parsed.path == "/api/guardrails":
                    try:
                        from modules.llm_guardrails import LLMGuardrails
                        gr = LLMGuardrails()
                        summary = gr.summary(days=7)
                        events = gr.recent_events(limit=50)
                    except Exception:
                        summary, events = {}, []
                    self._json({"summary": summary, "events": events})
                    return
                if parsed.path == "/api/llm_evals":
                    try:
                        from modules.llm_evals import LLMEvals
                        ev = LLMEvals()
                        current = ev.compute()
                        runs = ev.recent_runs(limit=20)
                    except Exception:
                        current, runs = {}, []
                    self._json({"current": current, "runs": runs})
                    return
                if parsed.path == "/api/tooling_registry":
                    try:
                        from modules.tooling_registry import ToolingRegistry
                        reg = ToolingRegistry()
                        rows = reg.list_adapters(limit=200)
                        approvals = reg.list_contract_approvals(status="pending", limit=100)
                        stage_approvals = reg.list_stage_approvals(status="pending", limit=100)
                        key_rotations = reg.list_signature_key_rotations(status="pending", limit=100)
                        history = reg.list_release_history(limit=100)
                        governance = reg.build_governance_report(days=7)
                        signature_policy = reg.get_signature_policy()
                    except Exception:
                        rows = []
                        approvals = []
                        stage_approvals = []
                        key_rotations = []
                        history = []
                        governance = {}
                        signature_policy = {}
                    self._json({
                        "adapters": rows,
                        "approvals": approvals,
                        "stage_approvals": stage_approvals,
                        "key_rotations": key_rotations,
                        "history": history,
                        "governance": governance,
                        "signature_policy": signature_policy,
                    })
                    return
                if parsed.path == "/api/events":
                    try:
                        from modules.data_lake import DataLake
                        events = DataLake().recent_events(limit=50)
                    except Exception:
                        events = []
                    self._json({"events": events})
                    return
                if parsed.path == "/api/handoffs":
                    try:
                        from modules.data_lake import DataLake
                        dl = DataLake()
                        rows = dl.recent_handoffs(limit=100)
                        summary = dl.handoff_summary(days=7)
                    except Exception:
                        rows = []
                        summary = []
                    self._json({"handoffs": rows, "summary": summary})
                    return
                if parsed.path == "/api/workflow_health":
                    try:
                        from modules.workflow_state_machine import WorkflowStateMachine
                        health = WorkflowStateMachine().health()
                    except Exception:
                        health = {}
                    self._json({"workflow": health})
                    return
                if parsed.path == "/api/workflow_events":
                    try:
                        from modules.workflow_state_machine import WorkflowStateMachine
                        wf = WorkflowStateMachine()
                        goal_id = (query.get("goal_id", [""])[0] or "").strip()
                        limit = int(query.get("limit", ["50"])[0] or 50)
                        if goal_id:
                            events = wf.recent_events(goal_id, limit=limit)
                        else:
                            events = wf.recent_events_all(limit=limit)
                    except Exception:
                        events = []
                    self._json({"events": events})
                    return
                if parsed.path == "/api/execution_facts":
                    try:
                        from modules.execution_facts import ExecutionFacts
                        facts = ExecutionFacts().recent_facts(limit=20)
                        facts_out = [f.__dict__ for f in facts]
                    except Exception:
                        facts_out = []
                    self._json({"facts": facts_out})
                    return
                if parsed.path == "/api/approvals":
                    pending = []
                    try:
                        if parent.comms:
                            pending = parent.comms.pending_approvals_list()
                    except Exception:
                        pending = []
                    self._json({"pending": pending, "count": len(pending)})
                    return
                if parsed.path == "/api/decisions":
                    try:
                        from modules.data_lake import DataLake
                        decisions = DataLake().decision_stats(limit=50)
                    except Exception:
                        decisions = []
                    self._json({"decisions": decisions})
                    return
                if parsed.path == "/api/budget":
                    try:
                        from modules.data_lake import DataLake
                        budget = DataLake().budget_stats(days=30)
                    except Exception:
                        budget = []
                    self._json({"budget": budget})
                    return

                if parsed.path == "/api/config":
                    allowed = [
                        "PROACTIVE_ENABLED",
                        "BRAINSTORM_WEEKLY",
                        "NOTIFY_MODE",
                        "DAILY_LIMIT_USD",
                        "OPERATION_NOTIFY_USD",
                        "OPERATION_APPROVE_USD",
                        "OPERATION_MAX_USD",
                        "OWNER_INBOX_ENABLED",
                        "CALENDAR_UPDATE_LLM",
                        "LLM_DISABLED_MODELS",
                        "LLM_ENABLED_MODELS",
                        "SELF_LEARNING_ENABLED",
                        "SELF_LEARNING_SKILL_SCORE_MIN",
                        "GUARDRAILS_ENABLED",
                        "GUARDRAILS_BLOCK_ON_INJECTION",
                        "LLM_ALERTS_ENABLED",
                        "TOOLING_RUN_LIVE_ENABLED",
                        "TOOLING_LIVE_REQUIRED_STAGE",
                        "TOOLING_REQUIRE_PRODUCTION_APPROVAL",
                        "TOOLING_REQUIRE_ROLLBACK_APPROVAL",
                        "TOOLING_HTTP_TIMEOUT_SEC",
                        "TOOLING_MCP_TIMEOUT_SEC",
                        "TOOLING_MCP_MAX_OUTPUT_BYTES",
                        "TOOLING_BLOCK_WITH_PENDING_ROTATION",
                    ]
                    data = {k: getattr(settings, k, None) for k in allowed}
                    self._json({"config": data})
                    return

                if parsed.path == "/":
                    html = """
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>VITO Dashboard</title>
  <style>
    :root{--bg:#0f1216;--fg:#e6e6e6;--mut:#9aa0a6;--card:#161b22;--acc:#2dd4bf;}
    body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--fg);} 
    .wrap{max-width:1100px;margin:24px auto;padding:0 16px;}
    .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}
    .card{background:var(--card);border:1px solid #242b36;border-radius:12px;padding:12px;}
    h1{font-size:22px;margin:0 0 12px 0;}
    .mut{color:var(--mut);} .acc{color:var(--acc);} 
    pre{white-space:pre-wrap;word-wrap:break-word;}
    table{width:100%;border-collapse:collapse;font-size:12px;}
    th,td{border-bottom:1px solid #242b36;padding:6px 4px;text-align:left;}
    th{color:var(--mut);font-weight:600;}
    @media(max-width:900px){.grid{grid-template-columns:1fr;}}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>VITO Dashboard</h1>
    <div class=\"grid\">
      <div class=\"card\"><div class=\"mut\">Status</div><div id=\"status\"></div></div>
      <div class=\"card\"><div class=\"mut\">Loop Control</div><div id=\"loop_ctrl\"></div>
        <div style=\"margin-top:8px\">
          <button onclick=\"loopAction('stop')\">Stop Loop</button>
          <button onclick=\"loopAction('start')\">Start Loop</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Agents</div><div id=\"agents\"></div></div>
      <div class=\"card\"><div class=\"mut\">Finance</div><div id=\"finance\"></div></div>
      <div class=\"card\"><div class=\"mut\">Goals</div><div id=\"goals\"></div></div>
      <div class=\"card\"><div class=\"mut\">Goal Control</div><div id=\"goal_ctrl\"></div>
        <div style=\"margin-top:8px\">
          <input id=\"goal_id_action\" placeholder=\"goal_id\" style=\"width:45%\"/>
          <button onclick=\"goalAction('delete')\">Delete</button>
          <button onclick=\"goalAction('fail')\">Fail</button>
        </div>
        <div style=\"margin-top:8px\">
          <button onclick=\"goalAction('clear_all')\">Clear All Goals</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Schedules</div><div id=\"schedules\"></div></div>
      <div class=\"card\"><div class=\"mut\">Schedule Control</div><div id=\"schedule_ctrl\"></div>
        <div style=\"margin-top:8px\">
          <input id=\"schedule_id_action\" placeholder=\"task_id\" style=\"width:45%\"/>
          <button onclick=\"scheduleAction('delete')\">Delete Task</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Network</div><div id=\"network\"></div></div>
      <div class=\"card\"><div class=\"mut\">Platforms</div><div id=\"platforms\"></div></div>
      <div class=\"card\"><div class=\"mut\">KPI</div><div id=\"kpi\"></div></div>
      <div class=\"card\"><div class=\"mut\">KPI Trend (30d)</div><div id=\"kpi_trend\"></div></div>
      <div class=\"card\"><div class=\"mut\">Models</div><div id=\"models\"></div></div>
      <div class=\"card\"><div class=\"mut\">Model Controls</div>
        <div style=\"margin-top:8px\">\n
          <input id=\"mdl_default\" placeholder=\"OPENROUTER_DEFAULT_MODEL\" style=\"width:62%\"/>
          <button onclick=\"setModelPolicy()\">Set</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"mdl_enabled\" placeholder=\"LLM_ENABLED_MODELS (csv)\" style=\"width:80%\"/>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"mdl_disabled\" placeholder=\"LLM_DISABLED_MODELS (csv)\" style=\"width:80%\"/>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"mdl_profile\" placeholder=\"profile name\" style=\"width:28%\"/>
          <button onclick=\"applyModelProfile()\">Apply Profile</button>
          <button onclick=\"saveModelProfile()\">Save Profile</button>
          <button onclick=\"deleteModelProfile()\">Delete Profile</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Execution Facts</div><div id=\"facts\"></div></div>
      <div class=\"card\"><div class=\"mut\">Pending Approvals</div><div id=\"approvals\"></div></div>
      <div class=\"card\"><div class=\"mut\">Recent Events</div><div id=\"events\"></div></div>
      <div class=\"card\"><div class=\"mut\">Workflow Events</div>
        <div style=\"margin-top:6px\">
          <input id=\"wf_goal\" placeholder=\"goal_id (optional)\" style=\"width:70%\"/>
          <button onclick=\"loadWorkflowEvents()\">Load</button>
        </div>
        <div id=\"workflow_events\" style=\"margin-top:8px\"></div>
      </div>
      <div class=\"card\"><div class=\"mut\">Decisions</div><div id=\"decisions\"></div></div>
      <div class=\"card\"><div class=\"mut\">Budget (30d)</div><div id=\"budget\"></div></div>
      <div class=\"card\"><div class=\"mut\">Config</div><div id=\"config\"></div>
        <div style=\"margin-top:8px\">\n
          <input id=\"cfg_key\" placeholder=\"KEY\" style=\"width:45%\"/>
          <input id=\"cfg_val\" placeholder=\"VALUE\" style=\"width:45%\"/>
          <button onclick=\"setConfig()\">Set</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Owner Prefs</div><div id=\"prefs\"></div></div>
      <div class=\"card\"><div class=\"mut\">Pref Controls</div>
        <div style=\"margin-top:8px\">\n
          <input id=\"pref_key\" placeholder=\"pref_key\" style=\"width:40%\"/>
          <input id=\"pref_val\" placeholder=\"value\" style=\"width:45%\"/>
          <button onclick=\"setPref()\">Set</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"pref_del_key\" placeholder=\"pref_key to deactivate\" style=\"width:60%\"/>
          <button onclick=\"delPref()\">Deactivate</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Pref Metrics</div><div id=\"prefs_metrics\"></div></div>
      <div class=\"card\"><div class=\"mut\">Capability Packs</div><div id=\"capability_packs\"></div></div>
      <div class=\"card\"><div class=\"mut\">Skills</div><div id=\"skills\"></div></div>
      <div class=\"card\"><div class=\"mut\">Operator Policy</div><div id=\"operator_policy\"></div></div>
      <div class=\"card\"><div class=\"mut\">Policy Controls</div>
        <div style=\"margin-top:8px\">\n
          <input id=\"pol_tool_key\" placeholder=\"capability:research\" style=\"width:52%\"/>
          <input id=\"pol_tool_enabled\" placeholder=\"1/0\" style=\"width:15%\"/>
          <button onclick=\"setToolPolicy()\">Set Tool</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"pol_budget_actor\" placeholder=\"capability:research\" style=\"width:40%\"/>
          <input id=\"pol_budget_limit\" placeholder=\"daily usd\" style=\"width:20%\"/>
          <input id=\"pol_budget_hard\" placeholder=\"hard 1/0\" style=\"width:18%\"/>
          <button onclick=\"setBudgetPolicy()\">Set Budget</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Self Learning</div><div id=\"self_learning\"></div></div>
      <div class=\"card\"><div class=\"mut\">Tooling Registry</div><div id=\"tooling_registry\"></div></div>
      <div class=\"card\"><div class=\"mut\">Tooling Controls</div>
        <div style=\"margin-top:8px\">\n
          <input id=\"tool_key\" placeholder=\"adapter_key\" style=\"width:32%\"/>
          <input id=\"tool_proto\" placeholder=\"mcp/openapi\" style=\"width:18%\"/>
          <input id=\"tool_ep\" placeholder=\"endpoint\" style=\"width:40%\"/>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_auth\" placeholder=\"auth_type\" style=\"width:22%\"/>
          <input id=\"tool_enabled\" placeholder=\"enabled 1/0\" style=\"width:18%\"/>
          <button onclick=\"setToolingAdapter()\">Upsert</button>
          <button onclick=\"runToolingAdapter()\">Dry Run</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_ver\" placeholder=\"version\" style=\"width:20%\"/>
          <button onclick=\"requestToolingRotation()\">Request Rotation</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_appr_id\" placeholder=\"approval_id\" style=\"width:22%\"/>
          <button onclick=\"approveToolingRotation()\">Approve</button>
          <button onclick=\"rejectToolingRotation()\">Reject</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_stage\" placeholder=\"stage\" style=\"width:20%\"/>
          <button onclick=\"requestPromoteToolingStage()\">Request Promote</button>
          <button onclick=\"requestRollbackToolingStage()\">Request Rollback</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_stage_appr_id\" placeholder=\"stage_approval_id\" style=\"width:24%\"/>
          <button onclick=\"approveStageToolingChange()\">Approve Stage</button>
          <button onclick=\"rejectStageToolingChange()\">Reject Stage</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_key_type\" placeholder=\"key_type contract/release\" style=\"width:30%\"/>
          <input id=\"tool_key_id\" placeholder=\"requested_key_id\" style=\"width:28%\"/>
          <button onclick=\"requestToolingKeyRotation()\">Request Key Rotate</button>
        </div>
        <div style=\"margin-top:6px\">\n
          <input id=\"tool_key_rot_id\" placeholder=\"key_rotation_id\" style=\"width:24%\"/>
          <button onclick=\"approveToolingKeyRotation()\">Approve Key</button>
          <button onclick=\"rejectToolingKeyRotation()\">Reject Key</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Memory Policy Audit</div><div id=\"memory_policy\"></div></div>
      <div class=\"card\"><div class=\"mut\">Memory Controls</div>
        <div style=\"margin-top:8px\">\n
          <input id=\"mem_doc_id\" placeholder=\"doc_id\" style=\"width:45%\"/>
          <input id=\"mem_reason\" placeholder=\"reason\" style=\"width:40%\"/>
          <button onclick=\"forgetMemory()\">Forget</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">Workflow Threads</div><div id=\"workflow_threads\"></div></div>
      <div class=\"card\"><div class=\"mut\">Workflow Interrupts</div><div id=\"workflow_interrupts\"></div></div>
      <div class=\"card\"><div class=\"mut\">Secrets</div>
        <div class=\"mut\" style=\"font-size:12px\">Keys are write‑only here.</div>
        <div id=\"secrets_status\" style=\"margin-top:6px\"></div>
        <div style=\"margin-top:8px\">\n
          <input id=\"sec_key\" placeholder=\"KEY\" style=\"width:45%\"/>
          <input id=\"sec_val\" placeholder=\"VALUE\" style=\"width:45%\"/>
          <button onclick=\"setSecret()\">Set</button>
        </div>
      </div>
      <div class=\"card\"><div class=\"mut\">RSS Sources</div><div id=\"rss\"></div>
        <div style=\"margin-top:8px\">\n
          <input id=\"rss_name\" placeholder=\"Name\" style=\"width:30%\"/>
          <input id=\"rss_url\" placeholder=\"URL\" style=\"width:55%\"/>
          <button onclick=\"addRss()\">Add</button>
        </div>
      </div>
    </div>
  </div>
<script>
async function load(){
  const endpoints = {
    status:'/api/status', network:'/api/network', agents:'/api/agents', finance:'/api/finance',
    goals:'/api/goals', schedules:'/api/schedules', config:'/api/config',
    platforms:'/api/platforms', platform_scorecard:'/api/platform_scorecard', rss:'/api/rss', kpi:'/api/kpi', kpi_trend:'/api/kpi_trend', models:'/api/models', llm_policy:'/api/llm_policy', guardrails:'/api/guardrails', llm_evals:'/api/llm_evals', tooling_registry:'/api/tooling_registry', prefs:'/api/prefs', prefs_metrics:'/api/prefs_metrics', capability_packs:'/api/capability_packs', skills:'/api/skills', operator_policy:'/api/operator_policy', self_learning:'/api/self_learning', memory_policy:'/api/memory_policy?limit=80', workflow_threads:'/api/workflow_threads', workflow_interrupts:'/api/workflow_interrupts', secrets_status:'/api/secrets_status',
    facts:'/api/execution_facts', approvals:'/api/approvals', events:'/api/events', decisions:'/api/decisions', budget:'/api/budget', workflow_events:'/api/workflow_events'
  };
  for (const [k,url] of Object.entries(endpoints)){
    const r = await fetch(url); const j = await r.json();
    if (k === 'rss') renderRss(j.sources||[]);
    else if (k === 'agents') renderAgents(j.agents||[]);
    else if (k === 'goals') renderGoals(j.goals||[]);
    else if (k === 'platforms') renderPlatforms(j.platforms||[]);
    else if (k === 'platform_scorecard') renderPlatformScorecard(j.scorecard||[]);
    else if (k === 'kpi') renderKpi(j.agent_kpi||[]);
    else if (k === 'kpi_trend') renderKpiTrend(j.trend||[]);
    else if (k === 'facts') renderFacts(j.facts||[]);
    else if (k === 'approvals') renderApprovals(j);
    else if (k === 'events') renderEvents(j.events||[]);
    else if (k === 'workflow_events') renderWorkflowEvents(j.events||[]);
    else if (k === 'decisions') renderDecisions(j.decisions||[]);
    else if (k === 'budget') renderBudget(j.budget||[]);
    else if (k === 'status') renderStatus(j);
    else if (k === 'network') renderNetwork(j.network||{});
    else if (k === 'finance') renderFinance(j);
    else if (k === 'schedules') renderSchedules(j.tasks||[]);
    else if (k === 'config') renderConfig(j.config||j);
    else if (k === 'prefs') renderPrefs(j.preferences||[]);
    else if (k === 'prefs_metrics') renderPrefsMetrics(j.metrics||{});
    else if (k === 'capability_packs') renderCapabilityPacks(j.packs||[]);
    else if (k === 'skills') renderSkills(j.skills||[]);
    else if (k === 'operator_policy') renderOperatorPolicy(j);
    else if (k === 'self_learning') renderSelfLearning(j);
    else if (k === 'memory_policy') renderMemoryPolicy(j.audit||[], j.summary||{});
    else if (k === 'workflow_threads') renderWorkflowThreads(j.threads||[]);
    else if (k === 'workflow_interrupts') renderWorkflowInterrupts(j.interrupts||[]);
    else if (k === 'secrets_status') renderSecretsStatus(j.secrets||[]);
    else if (k === 'models') renderModels(j);
    else if (k === 'llm_policy') renderLlmPolicy(j.policy||{});
    else if (k === 'guardrails') renderGuardrails(j);
    else if (k === 'llm_evals') renderLlmEvals(j);
    else if (k === 'tooling_registry') renderToolingRegistry(j.adapters||[], j.approvals||[], j.stage_approvals||[], j.key_rotations||[], j.history||[], j.governance||{}, j.signature_policy||{});
  }
}
function renderPrefs(prefs){
  const el = document.getElementById('prefs');
  if (!prefs.length){ el.innerHTML = '<div class=\"mut\">No prefs</div>'; return; }
  const rows = prefs.map(p => `<div style=\"margin:4px 0\"><code>${p.pref_key}</code>: ${JSON.stringify(p.value)} <span class=\"mut\">(conf=${(p.confidence||0).toFixed(2)})</span></div>`);
  el.innerHTML = rows.join('');
}
function renderPrefsMetrics(m){
  const el = document.getElementById('prefs_metrics');
  const rows = Object.entries(m||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderCapabilityPacks(packs){
  const el = document.getElementById('capability_packs');
  if (!packs.length){ el.innerHTML = '<div class=\"mut\">No packs</div>'; return; }
  const rows = packs.map(p => `<div style=\"margin:4px 0\"><code>${p.name}</code> ${p.category} <span class=\"mut\">(${p.status})</span></div>`);
  el.innerHTML = rows.join('');
}
function renderSkills(skills){
  const el = document.getElementById('skills');
  if (!skills.length){ el.innerHTML = '<div class=\"mut\">No skills</div>'; return; }
  const rows = skills.map(s => `<div style=\"margin:4px 0\"><code>${s.name}</code> ${s.category} <span class=\"mut\">(${s.acceptance_status})</span></div>`);
  el.innerHTML = rows.join('');
}
function renderOperatorPolicy(j){
  const el = document.getElementById('operator_policy');
  const tools = j.tools || [];
  const budgets = j.budgets || [];
  const trows = tools.map(t => `<tr><td>${t.tool_key}</td><td>${t.enabled?1:0}</td><td>${t.notes||''}</td></tr>`).join('');
  const brows = budgets.map(b => `<tr><td>${b.actor_key}</td><td>${b.daily_limit_usd}</td><td>${b.hard_block?1:0}</td><td>${b.notes||''}</td></tr>`).join('');
  el.innerHTML =
    `<div class=\"mut\">Tools</div><table><thead><tr><th>Key</th><th>On</th><th>Notes</th></tr></thead><tbody>${trows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Budgets</div><table><thead><tr><th>Actor</th><th>Daily</th><th>Hard</th><th>Notes</th></tr></thead><tbody>${brows}</tbody></table>`;
}
function renderSelfLearning(j){
  const el = document.getElementById('self_learning');
  const lessons = (j && j.lessons) ? j.lessons : [];
  const candidates = (j && j.candidates) ? j.candidates : [];
  const lrows = lessons.slice(0,8).map(r => `<tr><td>${r.goal_id||''}</td><td>${r.status||''}</td><td>${(r.score||0).toFixed? (r.score||0).toFixed(2):r.score}</td><td>${(r.lesson||'').slice(0,80)}</td></tr>`).join('');
  const crows = candidates.slice(0,8).map(r => `<tr><td>${r.skill_name}</td><td>${r.confidence}</td><td>${r.status}</td></tr>`).join('');
  el.innerHTML =
    `<div class=\"mut\">Lessons</div><table><thead><tr><th>Goal</th><th>Status</th><th>Score</th><th>Lesson</th></tr></thead><tbody>${lrows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Candidates</div><table><thead><tr><th>Skill</th><th>Confidence</th><th>Status</th></tr></thead><tbody>${crows}</tbody></table>`;
}
function renderToolingRegistry(items, approvals, stageApprovals, keyRotations, history, governance, signaturePolicy){
  const el = document.getElementById('tooling_registry');
  const app = approvals || [];
  const sapp = stageApprovals || [];
  const krot = keyRotations || [];
  const hist = history || [];
  const gov = governance || {};
  const policy = signaturePolicy || {};
  const rem = (gov.remediations || []).slice(0, 6).map(r => `<li>${r}</li>`).join('');
  const govRows = Object.entries(gov).filter(([k,_]) => k !== 'remediations').map(([k,v]) => `<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const keyRows = krot.map(a => `<tr><td>${a.id}</td><td>${a.key_type}</td><td>${a.requested_key_id}</td><td>${a.requested_by}</td></tr>`).join('');
  const keySummary = `<div class=\"mut\" style=\"margin-top:8px\">Active Keys: contract=<code>${policy.contract_active_key_id||''}</code>, release=<code>${policy.release_active_key_id||''}</code></div>`;
  if (!items.length){
    const prow0 = app.map(a => `<tr><td>${a.id}</td><td>${a.adapter_key}</td><td>${a.proposed_version}</td><td>${a.requested_by}</td></tr>`).join('');
    const s0 = sapp.map(a => `<tr><td>${a.id}</td><td>${a.adapter_key}</td><td>${a.action}</td><td>${a.target_stage||''}</td><td>${a.requested_by}</td></tr>`).join('');
    const k0 = keyRows;
    const h0 = hist.slice(0,6).map(h => `<tr><td>${h.adapter_key}</td><td>${h.from_stage}</td><td>${h.to_stage}</td><td>${h.created_at||''}</td></tr>`).join('');
    el.innerHTML = `<div class=\"mut\">No adapters</div><table><thead><tr><th>ID</th><th>Adapter</th><th>Version</th><th>By</th></tr></thead><tbody>${prow0}</tbody></table>` +
      `<div class=\"mut\" style=\"margin-top:8px\">Pending Stage Changes</div><table><thead><tr><th>ID</th><th>Adapter</th><th>Action</th><th>Target</th><th>By</th></tr></thead><tbody>${s0}</tbody></table>` +
      `<div class=\"mut\" style=\"margin-top:8px\">Pending Key Rotations</div><table><thead><tr><th>ID</th><th>Type</th><th>Key ID</th><th>By</th></tr></thead><tbody>${k0}</tbody></table>` +
      `<div class=\"mut\" style=\"margin-top:8px\">Release History</div><table><thead><tr><th>Adapter</th><th>From</th><th>To</th><th>Time</th></tr></thead><tbody>${h0}</tbody></table>`;
    return;
  }
  const rows = items.map(a => `<tr><td>${a.adapter_key}</td><td>${a.adapter_version||''}</td><td>${a.adapter_stage||''}</td><td>${a.protocol}</td><td>${a.endpoint}</td><td>${a.enabled?1:0}</td></tr>`).join('');
  const prows = app.map(a => `<tr><td>${a.id}</td><td>${a.adapter_key}</td><td>${a.proposed_version}</td><td>${a.requested_by}</td></tr>`).join('');
  const srows = sapp.map(a => `<tr><td>${a.id}</td><td>${a.adapter_key}</td><td>${a.action}</td><td>${a.target_stage||''}</td><td>${a.requested_by}</td></tr>`).join('');
  const hrows = hist.slice(0,8).map(h => `<tr><td>${h.adapter_key}</td><td>${h.from_stage}</td><td>${h.to_stage}</td><td>${h.actor}</td><td>${h.created_at||''}</td></tr>`).join('');
  el.innerHTML =
    `<table><thead><tr><th>Key</th><th>Version</th><th>Stage</th><th>Protocol</th><th>Endpoint</th><th>On</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Pending Rotations</div>` +
    `<table><thead><tr><th>ID</th><th>Adapter</th><th>Version</th><th>By</th></tr></thead><tbody>${prows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Pending Stage Changes</div>` +
    `<table><thead><tr><th>ID</th><th>Adapter</th><th>Action</th><th>Target</th><th>By</th></tr></thead><tbody>${srows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Pending Key Rotations</div>` +
    `<table><thead><tr><th>ID</th><th>Type</th><th>Key ID</th><th>By</th></tr></thead><tbody>${keyRows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Release History</div>` +
    `<table><thead><tr><th>Adapter</th><th>From</th><th>To</th><th>Actor</th><th>Time</th></tr></thead><tbody>${hrows}</tbody></table>` +
    keySummary +
    `<div class=\"mut\" style=\"margin-top:8px\">Governance</div><table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>${govRows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Remediations</div><ul>${rem}</ul>`;
}
function renderMemoryPolicy(items, summary){
  const el = document.getElementById('memory_policy');
  const sm = summary || {};
  const srows = Object.entries(sm).filter(([k,_]) => k !== 'retention_classes' && k !== 'saved_by_retention' && k !== 'top_forget_reasons').map(([k,v]) => `<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const rr = Object.entries(sm.retention_classes || {}).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  const sb = (sm.saved_by_retention || []).map(x => {
    const key = Object.keys(x)[0] || '';
    const val = x[key];
    return `<tr><td>${key}</td><td>${val}</td></tr>`;
  }).join('');
  const fr = (sm.top_forget_reasons || []).map(x => {
    const key = Object.keys(x)[0] || '';
    const val = x[key];
    return `<tr><td>${key}</td><td>${val}</td></tr>`;
  }).join('');
  if (!items.length){
    el.innerHTML =
      `<div class=\"mut\">No audit events</div>` +
      `<div class=\"mut\" style=\"margin-top:8px\">Summary</div><table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>${srows}</tbody></table>` +
      `<div class=\"mut\" style=\"margin-top:8px\">Retention Classes</div><table><thead><tr><th>Class</th><th>TTL days</th></tr></thead><tbody>${rr}</tbody></table>`;
    return;
  }
  const rows = items.map(a => `<tr><td>${a.created_at||''}</td><td>${a.doc_id||''}</td><td>${a.action||''}</td><td>${a.reason||''}</td><td>${a.memory_type||''}</td></tr>`).join('');
  el.innerHTML =
    `<div class=\"mut\">Summary</div><table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>${srows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Retention Classes</div><table><thead><tr><th>Class</th><th>TTL days</th></tr></thead><tbody>${rr}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Saved by Retention</div><table><thead><tr><th>Class</th><th>Count</th></tr></thead><tbody>${sb}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Top Forget Reasons</div><table><thead><tr><th>Reason</th><th>Count</th></tr></thead><tbody>${fr}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Audit Events</div><table><thead><tr><th>Time</th><th>Doc</th><th>Action</th><th>Reason</th><th>Type</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderWorkflowThreads(threads){
  const el = document.getElementById('workflow_threads');
  if (!threads.length){ el.innerHTML = '<div class=\"mut\">No threads</div>'; return; }
  const rows = threads.map(t => `<tr><td>${t.thread_id}</td><td>${t.goal_id||''}</td><td>${t.status}</td><td>${t.last_node}</td><td>${t.updated_at||''}</td></tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>Thread</th><th>Goal</th><th>Status</th><th>Last</th><th>Updated</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderWorkflowInterrupts(items){
  const el = document.getElementById('workflow_interrupts');
  if (!items.length){ el.innerHTML = '<div class=\"mut\">No interrupts</div>'; return; }
  const rows = items.slice(0,50).map(i => `<tr><td>${i.goal_id||''}</td><td>${i.step_num||0}</td><td>${i.interrupt_type||''}</td><td>${i.status||''}</td><td>${(i.reason||'').slice(0,80)}</td><td>${i.created_at||''}</td></tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>Goal</th><th>Step</th><th>Type</th><th>Status</th><th>Reason</th><th>Created</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderRss(sources){
  const el = document.getElementById('rss');
  el.innerHTML = sources.map(s => {
    const btn = s.enabled ? 'Disable' : 'Enable';
    return `<div style=\"margin:4px 0\">\n
      <code>${s.id}</code> ${s.name} — ${s.url} [${s.enabled?'on':'off'}]\n
      <button onclick=\"toggleRss(${s.id}, ${s.enabled?0:1})\">${btn}</button>
      <button onclick=\"removeRss(${s.id})\">Remove</button>
    </div>`;
  }).join('') || '<div class=\"mut\">No sources</div>';
}
function renderStatus(j){
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('status').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
  const loop = (j && j.decision_loop) ? j.decision_loop : {};
  document.getElementById('loop_ctrl').innerHTML = `<table><thead><tr><th>Loop</th><th>Value</th></tr></thead><tbody>
    <tr><td>running</td><td>${loop.running}</td></tr>
    <tr><td>tick_count</td><td>${loop.tick_count||0}</td></tr>
    <tr><td>daily_spend</td><td>${loop.daily_spend||0}</td></tr>
    <tr><td>pending_approvals</td><td>${loop.pending_approvals||0}</td></tr>
  </tbody></table>`;
}
function renderNetwork(j){
  const hosts = j.hosts || {};
  const rows = Object.entries(hosts).map(([h,v])=>`<tr><td>${h}</td><td>${v?'ok':'fail'}</td></tr>`).join('');
  document.getElementById('network').innerHTML =
    `<div class="mut">ok=${j.ok} reason=${j.reason||''}</div>` +
    `<table><thead><tr><th>Host</th><th>DNS</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderFinance(j){
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('finance').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderModels(j){
  const rows = Object.entries(j||{}).filter(([k,_]) => k !== 'profiles').map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const profiles = (j && j.profiles) ? j.profiles : [];
  const prows = profiles.map(p => `<tr><td>${p.profile_name}</td><td>${p.default_model||''}</td><td>${p.enabled_models||''}</td><td>${p.disabled_models||''}</td><td>${p.notes||''}</td></tr>`).join('');
  document.getElementById('models').innerHTML =
    `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Profiles</div>` +
    `<table><thead><tr><th>Name</th><th>Default</th><th>Enabled</th><th>Disabled</th><th>Notes</th></tr></thead><tbody>${prows}</tbody></table>`;
}
function renderSecretsStatus(items){
  const el = document.getElementById('secrets_status');
  if (!el) return;
  if (!items.length){ el.innerHTML = '<div class=\"mut\">No secrets tracked</div>'; return; }
  const rows = items.map(s => `<tr><td>${s.key}</td><td>${s.present?1:0}</td><td>${s.preview||''}</td></tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>Key</th><th>Set</th><th>Tail</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderLlmPolicy(j){
  const rows = Object.entries(j||{}).filter(([k,_]) => k !== 'providers' && k !== 'top').map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const prov = Object.entries(j.providers||{}).map(([k,v])=>`<tr><td>${k}</td><td>${v.calls||0}</td><td>${(v.cost_usd||0).toFixed? v.cost_usd.toFixed(4):v.cost_usd}</td></tr>`).join('');
  const top = (j.top||[]).map(r=>`<tr><td>${r.model}</td><td>${r.task_type}</td><td>${r.calls}</td><td>${r.total_cost}</td></tr>`).join('');
  document.getElementById('models').innerHTML =
    `<table><thead><tr><th>Policy</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Providers</div>` +
    `<table><thead><tr><th>Provider</th><th>Calls</th><th>Cost</th></tr></thead><tbody>${prov}</tbody></table>` +
    `<div class=\"mut\" style=\"margin-top:8px\">Top spend</div>` +
    `<table><thead><tr><th>Model</th><th>Task</th><th>Calls</th><th>Cost</th></tr></thead><tbody>${top}</tbody></table>`;
}
function renderGuardrails(j){
  const summary = (j && j.summary) ? j.summary : {};
  const events = (j && j.events) ? j.events : [];
  const rows = Object.entries(summary).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const erows = events.slice(0,10).map(e=>`<tr><td>${e.created_at||''}</td><td>${e.task_type||''}</td><td>${e.reason||''}</td><td>${e.blocked?1:0}</td></tr>`).join('');
  document.getElementById('models').innerHTML +=
    `<div class=\"mut\" style=\"margin-top:8px\">Guardrails</div>` +
    `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<table><thead><tr><th>Time</th><th>Task</th><th>Reason</th><th>Blocked</th></tr></thead><tbody>${erows}</tbody></table>`;
}
function renderLlmEvals(j){
  const current = (j && j.current) ? j.current : {};
  const runs = (j && j.runs) ? j.runs : [];
  const rows = Object.entries(current).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  const hrows = runs.slice(0,8).map(r=>`<tr><td>${r.created_at||''}</td><td>${r.score}</td><td>${r.fail_rate}</td><td>${r.daily_cost}</td><td>${r.anomaly?1:0}</td></tr>`).join('');
  document.getElementById('models').innerHTML +=
    `<div class=\"mut\" style=\"margin-top:8px\">LLM Evals</div>` +
    `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<table><thead><tr><th>Time</th><th>Score</th><th>Fail</th><th>Cost</th><th>Anomaly</th></tr></thead><tbody>${hrows}</tbody></table>`;
}
function renderConfig(j){
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('config').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderAgents(items){
  const rows = items.map(a=>`<tr><td>${a.name}</td><td>${a.status}</td><td>${a.tasks_completed}</td><td>${a.tasks_failed}</td><td>${(a.total_cost||0).toFixed? (a.total_cost||0).toFixed(2):a.total_cost}</td></tr>`).join('');
  document.getElementById('agents').innerHTML = `<table><thead><tr><th>Agent</th><th>Status</th><th>Done</th><th>Fail</th><th>Cost</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderGoals(items){
  const rows = items.map(g=>`<tr><td>${g.goal_id}</td><td>${g.title}</td><td>${g.status}</td><td>${g.priority}</td><td>${g.estimated_cost}</td></tr>`).join('');
  document.getElementById('goals').innerHTML = `<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Priority</th><th>Cost</th></tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById('goal_ctrl').innerHTML = `<div class="mut">Rows: ${items.length}</div>`;
}
function renderPlatforms(items){
  const rows = items.map(p=>`<tr><td>${p.name}</td><td>${p.type}</td><td>${p.capabilities}</td><td>${p.configured?'yes':'no'}</td></tr>`).join('');
  document.getElementById('platforms').innerHTML = `<table><thead><tr><th>Platform</th><th>Type</th><th>Caps</th><th>Configured</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderPlatformScorecard(items){
  const rows = items.map(s=>`<tr><td>${s.platform}</td><td>${s.configured?'yes':'no'}</td><td>${s.success_count_30d}</td><td>${s.evidence_count_30d}</td><td>${s.fail_count_30d}</td><td>${s.readiness_score}</td><td>${s.note}</td></tr>`).join('');
  const extra = `<div class=\"mut\" style=\"margin-top:8px\">Production readiness (30d)</div>
    <table><thead><tr><th>Platform</th><th>Configured</th><th>Success</th><th>Evidence</th><th>Fail</th><th>Score</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById('platforms').innerHTML += extra;
}
function renderKpi(items){
  const rows = items.map(k=>`<tr><td>${k.agent}</td><td>${k.ok}</td><td>${k.fail}</td><td>${k.total}</td></tr>`).join('');
  document.getElementById('kpi').innerHTML = `<table><thead><tr><th>Agent</th><th>OK</th><th>Fail</th><th>Total</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderKpiTrend(items){
  const rows = items.map(t=>`<tr><td>${t.date}</td><td>${t.ok}</td><td>${t.fail}</td><td>${t.total}</td><td>${Math.round((t.success_rate||0)*100)}%</td></tr>`).join('');
  document.getElementById('kpi_trend').innerHTML = `<table><thead><tr><th>Date</th><th>OK</th><th>Fail</th><th>Total</th><th>SR</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderFacts(items){
  const rows = items.map(f=>`<tr><td>${f.action}</td><td>${f.status}</td><td>${f.evidence||''}</td><td>${f.created_at}</td></tr>`).join('');
  document.getElementById('facts').innerHTML = `<table><thead><tr><th>Action</th><th>Status</th><th>Evidence</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderApprovals(j){
  const pending = (j && j.pending) ? j.pending : [];
  if (!pending.length){
    document.getElementById('approvals').innerHTML = '<div class=\"mut\">None</div>';
    return;
  }
  const rows = pending.map(p=>`<tr><td>${p}</td></tr>`).join('');
  document.getElementById('approvals').innerHTML = `<table><thead><tr><th>Request ID</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderEvents(items){
  const rows = items.map(e=>`<tr><td>${e.agent}</td><td>${e.task_type}</td><td>${e.status}</td><td>${e.created_at}</td></tr>`).join('');
  document.getElementById('events').innerHTML = `<table><thead><tr><th>Agent</th><th>Task</th><th>Status</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderWorkflowEvents(items){
  const rows = items.map(e=>`<tr><td>${e.created_at||''}</td><td>${e.goal_id||''}</td><td>${e.from_state||''} → ${e.to_state||''}</td><td>${e.reason||''}</td><td>${(e.detail||'').toString().slice(0,120)}</td></tr>`).join('');
  document.getElementById('workflow_events').innerHTML =
    `<table><thead><tr><th>Time</th><th>Goal</th><th>Transition</th><th>Reason</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderDecisions(items){
  const rows = items.map(d=>`<tr><td>${d.actor}</td><td>${d.decision}</td><td>${d.created_at}</td></tr>`).join('');
  document.getElementById('decisions').innerHTML = `<table><thead><tr><th>Actor</th><th>Decision</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderBudget(items){
  const rows = items.map(b=>`<tr><td>${b.agent}</td><td>${b.total}</td></tr>`).join('');
  document.getElementById('budget').innerHTML = `<table><thead><tr><th>Agent</th><th>Total</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderSchedules(items){
  const rows = items.map(s=>`<tr><td>${s.id}</td><td>${s.title}</td><td>${s.schedule_type}</td><td>${s.next_run||''}</td><td>${s.status}</td></tr>`).join('');
  document.getElementById('schedules').innerHTML = `<table><thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Next</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById('schedule_ctrl').innerHTML = `<div class="mut">Rows: ${items.length}</div>`;
}
async function loadWorkflowEvents(){
  const goal = document.getElementById('wf_goal').value || '';
  const url = goal ? `/api/workflow_events?goal_id=${encodeURIComponent(goal)}` : '/api/workflow_events';
  const r = await fetch(url); const j = await r.json();
  renderWorkflowEvents(j.events||[]);
}
async function setConfig(){
  const k = document.getElementById('cfg_key').value.trim();
  const v = document.getElementById('cfg_val').value.trim();
  if (!k) return;
  await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({[k]: v})});
  await load();
}
async function setModelPolicy(){
  const OPENROUTER_DEFAULT_MODEL = document.getElementById('mdl_default').value.trim();
  const LLM_ENABLED_MODELS = document.getElementById('mdl_enabled').value.trim();
  const LLM_DISABLED_MODELS = document.getElementById('mdl_disabled').value.trim();
  const payload = {};
  if (OPENROUTER_DEFAULT_MODEL) payload.OPENROUTER_DEFAULT_MODEL = OPENROUTER_DEFAULT_MODEL;
  payload.LLM_ENABLED_MODELS = LLM_ENABLED_MODELS;
  payload.LLM_DISABLED_MODELS = LLM_DISABLED_MODELS;
  await fetch('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  await load();
}
async function applyModelProfile(){
  const profile_name = document.getElementById('mdl_profile').value.trim();
  if (!profile_name) return;
  await fetch('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'apply_profile', profile_name})});
  await load();
}
async function saveModelProfile(){
  const profile_name = document.getElementById('mdl_profile').value.trim();
  const OPENROUTER_DEFAULT_MODEL = document.getElementById('mdl_default').value.trim();
  const LLM_ENABLED_MODELS = document.getElementById('mdl_enabled').value.trim();
  const LLM_DISABLED_MODELS = document.getElementById('mdl_disabled').value.trim();
  if (!profile_name) return;
  await fetch('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    action:'save_profile',
    profile_name,
    OPENROUTER_DEFAULT_MODEL,
    LLM_ENABLED_MODELS,
    LLM_DISABLED_MODELS,
  })});
  await load();
}
async function deleteModelProfile(){
  const profile_name = document.getElementById('mdl_profile').value.trim();
  if (!profile_name) return;
  await fetch('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'delete_profile', profile_name})});
  await load();
}
async function addRss(){
  const name = document.getElementById('rss_name').value.trim() || 'source';
  const url = document.getElementById('rss_url').value.trim();
  if (!url) return;
  await fetch('/api/rss', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'add', name, url})});
  await load();
}
async function setPref(){
  const key = document.getElementById('pref_key').value.trim();
  const val = document.getElementById('pref_val').value.trim();
  if (!key) return;
  await fetch('/api/prefs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'set', key, value: val})});
  await load();
}
async function delPref(){
  const key = document.getElementById('pref_del_key').value.trim();
  if (!key) return;
  await fetch('/api/prefs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'deactivate', key})});
  await load();
}
async function forgetMemory(){
  const doc_id = document.getElementById('mem_doc_id').value.trim();
  const reason = document.getElementById('mem_reason').value.trim() || 'dashboard_forget';
  if (!doc_id) return;
  await fetch('/api/memory_policy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'forget', doc_id, reason})});
  await load();
}
async function setToolPolicy(){
  const tool_key = document.getElementById('pol_tool_key').value.trim();
  const enabled = (document.getElementById('pol_tool_enabled').value.trim() || '1') !== '0';
  if (!tool_key) return;
  await fetch('/api/operator_policy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'set_tool', tool_key, enabled})});
  await load();
}
async function setBudgetPolicy(){
  const actor_key = document.getElementById('pol_budget_actor').value.trim();
  const daily_limit_usd = parseFloat(document.getElementById('pol_budget_limit').value.trim() || '0');
  const hard_block = (document.getElementById('pol_budget_hard').value.trim() || '0') === '1';
  if (!actor_key) return;
  await fetch('/api/operator_policy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'set_budget', actor_key, daily_limit_usd, hard_block})});
  await load();
}
async function setToolingAdapter(){
  const adapter_key = document.getElementById('tool_key').value.trim();
  const protocol = document.getElementById('tool_proto').value.trim();
  const endpoint = document.getElementById('tool_ep').value.trim();
  const auth_type = document.getElementById('tool_auth').value.trim() || 'none';
  const enabled = (document.getElementById('tool_enabled').value.trim() || '1') !== '0';
  const adapter_version = document.getElementById('tool_ver').value.trim() || '1.0.0';
  const adapter_stage = document.getElementById('tool_stage').value.trim() || 'accepted';
  if (!adapter_key || !protocol || !endpoint) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'upsert', adapter_key, adapter_version, adapter_stage, protocol, endpoint, auth_type, enabled})});
  await load();
}
async function runToolingAdapter(){
  const adapter_key = document.getElementById('tool_key').value.trim();
  if (!adapter_key) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'run', adapter_key, dry_run:true})});
  await load();
}
async function requestToolingRotation(){
  const adapter_key = document.getElementById('tool_key').value.trim();
  const protocol = document.getElementById('tool_proto').value.trim();
  const endpoint = document.getElementById('tool_ep').value.trim();
  const auth_type = document.getElementById('tool_auth').value.trim() || 'none';
  const enabled = (document.getElementById('tool_enabled').value.trim() || '1') !== '0';
  const adapter_version = document.getElementById('tool_ver').value.trim() || '1.0.0';
  if (!adapter_key || !protocol || !endpoint) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'request_rotation', adapter_key, protocol, endpoint, auth_type, enabled, adapter_version, requested_by:'dashboard'})});
  await load();
}
async function approveToolingRotation(){
  const approval_id = parseInt((document.getElementById('tool_appr_id').value||'0').trim(), 10);
  if (!approval_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'approve_rotation', approval_id, approver:'dashboard'})});
  await load();
}
async function rejectToolingRotation(){
  const approval_id = parseInt((document.getElementById('tool_appr_id').value||'0').trim(), 10);
  if (!approval_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'reject_rotation', approval_id, approver:'dashboard'})});
  await load();
}
async function requestPromoteToolingStage(){
  const adapter_key = document.getElementById('tool_key').value.trim();
  const to_stage = document.getElementById('tool_stage').value.trim();
  if (!adapter_key || !to_stage) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'request_stage_change', adapter_key, change_action:'promote', target_stage:to_stage, requested_by:'dashboard'})});
  await load();
}
async function requestRollbackToolingStage(){
  const adapter_key = document.getElementById('tool_key').value.trim();
  if (!adapter_key) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'request_stage_change', adapter_key, change_action:'rollback', requested_by:'dashboard'})});
  await load();
}
async function approveStageToolingChange(){
  const approval_id = parseInt((document.getElementById('tool_stage_appr_id').value||'0').trim(), 10);
  if (!approval_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'approve_stage_change', approval_id, approver:'dashboard'})});
  await load();
}
async function rejectStageToolingChange(){
  const approval_id = parseInt((document.getElementById('tool_stage_appr_id').value||'0').trim(), 10);
  if (!approval_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'reject_stage_change', approval_id, approver:'dashboard'})});
  await load();
}
async function requestToolingKeyRotation(){
  const key_type = (document.getElementById('tool_key_type').value || '').trim();
  const requested_key_id = (document.getElementById('tool_key_id').value || '').trim();
  if (!key_type || !requested_key_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'request_key_rotation', key_type, requested_key_id, requested_by:'dashboard'})});
  await load();
}
async function approveToolingKeyRotation(){
  const rotation_id = parseInt((document.getElementById('tool_key_rot_id').value||'0').trim(), 10);
  if (!rotation_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'approve_key_rotation', rotation_id, approver:'dashboard'})});
  await load();
}
async function rejectToolingKeyRotation(){
  const rotation_id = parseInt((document.getElementById('tool_key_rot_id').value||'0').trim(), 10);
  if (!rotation_id) return;
  await fetch('/api/tooling_registry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'reject_key_rotation', rotation_id, approver:'dashboard'})});
  await load();
}
async function setSecret(){
  const k = document.getElementById('sec_key').value.trim();
  const v = document.getElementById('sec_val').value.trim();
  if (!k) return;
  await fetch('/api/secrets', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({[k]: v})});
  document.getElementById('sec_key').value = '';
  document.getElementById('sec_val').value = '';
}
async function toggleRss(id, enabled){
  await fetch('/api/rss', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'toggle', id, enabled})});
  await load();
}
async function removeRss(id){
  await fetch('/api/rss', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'remove', id})});
  await load();
}
async function goalAction(action){
  const goal_id = (document.getElementById('goal_id_action').value||'').trim();
  await fetch('/api/goals/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, goal_id})});
  await load();
}
async function scheduleAction(action){
  const id = parseInt((document.getElementById('schedule_id_action').value||'0').trim(), 10);
  await fetch('/api/schedules/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, id})});
  await load();
}
async function loopAction(action){
  await fetch('/api/loop/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action})});
  await load();
}
load();
</script>
</body>
</html>
"""
                    self._html(html)
                    return

                self._text("Not Found", 404)

            def do_POST(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not parent._auth_ok(query, self.headers):
                    self._text("Unauthorized", 401)
                    return
                if parsed.path == "/api/config":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    allowed = {
                        "PROACTIVE_ENABLED",
                        "BRAINSTORM_WEEKLY",
                        "NOTIFY_MODE",
                        "DAILY_LIMIT_USD",
                        "OPERATION_NOTIFY_USD",
                        "OPERATION_APPROVE_USD",
                        "OPERATION_MAX_USD",
                        "OWNER_INBOX_ENABLED",
                        "CALENDAR_UPDATE_LLM",
                        "LLM_DISABLED_MODELS",
                        "LLM_ENABLED_MODELS",
                        "OPENROUTER_DEFAULT_MODEL",
                        "SELF_LEARNING_ENABLED",
                        "SELF_LEARNING_SKILL_SCORE_MIN",
                        "GUARDRAILS_ENABLED",
                        "GUARDRAILS_BLOCK_ON_INJECTION",
                        "LLM_ALERTS_ENABLED",
                        "TOOLING_RUN_LIVE_ENABLED",
                        "TOOLING_LIVE_REQUIRED_STAGE",
                        "TOOLING_REQUIRE_PRODUCTION_APPROVAL",
                        "TOOLING_REQUIRE_ROLLBACK_APPROVAL",
                        "TOOLING_HTTP_TIMEOUT_SEC",
                        "TOOLING_MCP_TIMEOUT_SEC",
                        "TOOLING_MCP_MAX_OUTPUT_BYTES",
                        "TOOLING_BLOCK_WITH_PENDING_ROTATION",
                    }
                    updated = {}
                    bool_keys = {"PROACTIVE_ENABLED", "BRAINSTORM_WEEKLY", "OWNER_INBOX_ENABLED", "CALENDAR_UPDATE_LLM", "SELF_LEARNING_ENABLED", "GUARDRAILS_ENABLED", "GUARDRAILS_BLOCK_ON_INJECTION", "LLM_ALERTS_ENABLED", "TOOLING_RUN_LIVE_ENABLED", "TOOLING_BLOCK_WITH_PENDING_ROTATION", "TOOLING_REQUIRE_PRODUCTION_APPROVAL", "TOOLING_REQUIRE_ROLLBACK_APPROVAL"}
                    num_keys = {"DAILY_LIMIT_USD", "OPERATION_NOTIFY_USD", "OPERATION_APPROVE_USD", "OPERATION_MAX_USD", "SELF_LEARNING_SKILL_SCORE_MIN", "TOOLING_HTTP_TIMEOUT_SEC", "TOOLING_MCP_TIMEOUT_SEC", "TOOLING_MCP_MAX_OUTPUT_BYTES"}
                    for k,v in payload.items():
                        if k in allowed:
                            if k in bool_keys:
                                vv = str(v).strip().lower() in ("1", "true", "yes", "on")
                                out_v = "true" if vv else "false"
                            elif k in num_keys:
                                try:
                                    fv = float(v)
                                except Exception:
                                    continue
                                if fv < 0:
                                    continue
                                out_v = str(fv)
                            else:
                                out_v = str(v)
                            updated[k] = out_v
                            try:
                                import os
                                os.environ[k] = out_v
                                if hasattr(settings, k):
                                    setattr(settings, k, out_v)
                            except Exception:
                                pass
                    # write to .env
                    try:
                        from pathlib import Path
                        import re
                        env_path = Path("/home/vito/vito-agent/.env")
                        text = env_path.read_text() if env_path.exists() else ""
                        for k,v in updated.items():
                            if re.search(rf"^{k}=.*$", text, flags=re.M):
                                text = re.sub(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
                            else:
                                if text and not text.endswith("\n"):
                                    text += "\n"
                                text += f"{k}={v}\n"
                        env_path.write_text(text)
                    except Exception:
                        pass
                    try:
                        if updated:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(
                                actor="dashboard",
                                decision="config_update",
                                rationale=", ".join(sorted(updated.keys()))[:1000],
                            )
                    except Exception:
                        pass
                    self._json({"updated": updated})
                    return
                if parsed.path == "/api/models":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    allowed = {"OPENROUTER_DEFAULT_MODEL", "LLM_ENABLED_MODELS", "LLM_DISABLED_MODELS", "MODEL_ACTIVE_PROFILE"}
                    updated = {}
                    model_chars_ok = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/:,")
                    def _clean_csv_models(value: str) -> str:
                        cleaned = []
                        for part in str(value or "").split(","):
                            token = part.strip()
                            if not token:
                                continue
                            if all(c in model_chars_ok for c in token):
                                cleaned.append(token)
                        return ",".join(cleaned)
                    if action in {"apply_profile", "save_profile", "delete_profile"}:
                        try:
                            from modules.model_profiles import ModelProfiles
                            prof = ModelProfiles()
                            profile_name = str(payload.get("profile_name", "")).strip().lower()
                            if action == "apply_profile":
                                updates = prof.profile_updates(profile_name)
                                if updates:
                                    updates["MODEL_ACTIVE_PROFILE"] = profile_name
                                    payload = updates
                            elif action == "save_profile":
                                prof.save_profile(
                                    profile_name=profile_name,
                                    default_model=str(payload.get("OPENROUTER_DEFAULT_MODEL", "")).strip(),
                                    enabled_models=_clean_csv_models(payload.get("LLM_ENABLED_MODELS", "")),
                                    disabled_models=_clean_csv_models(payload.get("LLM_DISABLED_MODELS", "")),
                                    notes=str(payload.get("notes", "dashboard profile")).strip(),
                                )
                            elif action == "delete_profile":
                                prof.delete_profile(profile_name)
                        except Exception:
                            pass
                    for k, v in payload.items():
                        if k not in allowed:
                            continue
                        val = str(v or "").strip()
                        if k == "OPENROUTER_DEFAULT_MODEL":
                            if not val or not all(c in model_chars_ok for c in val):
                                continue
                        if k in {"LLM_ENABLED_MODELS", "LLM_DISABLED_MODELS"}:
                            val = _clean_csv_models(val)
                        updated[k] = val
                        try:
                            import os
                            os.environ[k] = val
                            if hasattr(settings, k):
                                setattr(settings, k, val)
                        except Exception:
                            pass
                    try:
                        from pathlib import Path
                        import re
                        env_path = Path("/home/vito/vito-agent/.env")
                        text = env_path.read_text() if env_path.exists() else ""
                        for k, v in updated.items():
                            if re.search(rf"^{k}=.*$", text, flags=re.M):
                                text = re.sub(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
                            else:
                                if text and not text.endswith("\n"):
                                    text += "\n"
                                text += f"{k}={v}\n"
                        env_path.write_text(text)
                    except Exception:
                        pass
                    try:
                        if updated:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(actor="dashboard", decision="models_update", rationale=",".join(sorted(updated.keys())))
                    except Exception:
                        pass
                    self._json({"updated": updated})
                    return
                if parsed.path == "/api/prefs":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    key = str(payload.get("key", "")).strip()
                    updated = False
                    if key:
                        try:
                            pref = OwnerPreferenceModel()
                            if action == "set":
                                val = payload.get("value", "")
                                if isinstance(val, str):
                                    v = val.strip()
                                    if (v.startswith("{") and v.endswith("}")) or (v.startswith("[") and v.endswith("]")):
                                        try:
                                            val = json.loads(v)
                                        except Exception:
                                            val = v
                                    elif v.lower() in ("true", "false"):
                                        val = v.lower() == "true"
                                    elif v.lower() in ("null", "none"):
                                        val = None
                                    else:
                                        val = v
                                pref.set_preference(key=key, value=val, source="dashboard", confidence=1.0, notes="dashboard_set")
                                updated = True
                            elif action == "deactivate":
                                pref.deactivate_preference(key, notes="dashboard_deactivate")
                                updated = True
                        except Exception:
                            updated = False
                    if updated:
                        try:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(actor="dashboard", decision="prefs_update", rationale=f"{action}:{key}")
                        except Exception:
                            pass
                    self._json({"updated": updated, "action": action, "key": key})
                    return
                if parsed.path == "/api/operator_policy":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    ok = False
                    try:
                        op = OperatorPolicy()
                        if action == "set_tool":
                            tool_key = str(payload.get("tool_key", "")).strip()
                            if tool_key:
                                op.set_tool_policy(tool_key=tool_key, enabled=bool(payload.get("enabled", True)), notes=str(payload.get("notes", "")))
                                ok = True
                        elif action == "delete_tool":
                            tool_key = str(payload.get("tool_key", "")).strip()
                            if tool_key:
                                op.delete_tool_policy(tool_key)
                                ok = True
                        elif action == "set_budget":
                            actor_key = str(payload.get("actor_key", "")).strip()
                            if actor_key:
                                op.set_budget_policy(
                                    actor_key=actor_key,
                                    daily_limit_usd=float(payload.get("daily_limit_usd", 0) or 0),
                                    hard_block=bool(payload.get("hard_block", False)),
                                    notes=str(payload.get("notes", "")),
                                )
                                ok = True
                        elif action == "delete_budget":
                            actor_key = str(payload.get("actor_key", "")).strip()
                            if actor_key:
                                op.delete_budget_policy(actor_key)
                                ok = True
                    except Exception:
                        ok = False
                    if ok:
                        try:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(actor="dashboard", decision="operator_policy_update", rationale=action)
                        except Exception:
                            pass
                    self._json({"ok": ok, "action": action})
                    return
                if parsed.path == "/api/memory_policy":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    doc_id = str(payload.get("doc_id", "")).strip()
                    reason = str(payload.get("reason", "")).strip() or "dashboard_forget"
                    ok = False
                    if action == "forget" and doc_id:
                        try:
                            ok = bool(MemoryManager().forget_knowledge(doc_id=doc_id, reason=reason, metadata={"source": "dashboard"}))
                        except Exception:
                            ok = False
                    if ok:
                        try:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(actor="dashboard", decision="memory_forget", rationale=f"{doc_id}:{reason}"[:1000])
                        except Exception:
                            pass
                    self._json({"ok": ok, "action": action, "doc_id": doc_id, "reason": reason})
                    return
                if parsed.path == "/api/tooling_registry":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    ok = False
                    errors = []
                    run_result = {}
                    try:
                        from modules.tooling_registry import ToolingRegistry
                        reg = ToolingRegistry()
                        if action == "upsert":
                            result = reg.upsert_adapter(
                                adapter_key=str(payload.get("adapter_key", "")).strip(),
                                adapter_version=str(payload.get("adapter_version", "1.0.0")).strip() or "1.0.0",
                                adapter_stage=str(payload.get("adapter_stage", "accepted")).strip() or "accepted",
                                protocol=str(payload.get("protocol", "")).strip().lower(),
                                endpoint=str(payload.get("endpoint", "")).strip(),
                                auth_type=str(payload.get("auth_type", "none")).strip(),
                                enabled=bool(payload.get("enabled", True)),
                                schema=payload.get("schema", {}) if isinstance(payload.get("schema", {}), dict) else {},
                                notes=str(payload.get("notes", "")),
                            )
                            ok = bool(result.get("ok"))
                            errors = result.get("errors", [])
                            run_result = result
                        elif action == "delete":
                            key = str(payload.get("adapter_key", "")).strip()
                            if key:
                                reg.delete_adapter(key)
                                ok = True
                        elif action == "request_rotation":
                            result = reg.request_contract_rotation(
                                adapter_key=str(payload.get("adapter_key", "")).strip(),
                                adapter_version=str(payload.get("adapter_version", "1.0.0")).strip() or "1.0.0",
                                protocol=str(payload.get("protocol", "")).strip().lower(),
                                endpoint=str(payload.get("endpoint", "")).strip(),
                                auth_type=str(payload.get("auth_type", "none")).strip(),
                                enabled=bool(payload.get("enabled", True)),
                                schema=payload.get("schema", {}) if isinstance(payload.get("schema", {}), dict) else {},
                                notes=str(payload.get("notes", "")),
                                requested_by=str(payload.get("requested_by", "dashboard")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = result.get("errors", []) or [str(result.get("error", "request_failed"))]
                            run_result = result
                        elif action == "approve_rotation":
                            result = reg.approve_contract_rotation(
                                approval_id=int(payload.get("approval_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "approve_failed"))]
                            run_result = result
                        elif action == "reject_rotation":
                            result = reg.reject_contract_rotation(
                                approval_id=int(payload.get("approval_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "reject_failed"))]
                            run_result = result
                        elif action == "promote_stage":
                            result = reg.promote_adapter(
                                adapter_key=str(payload.get("adapter_key", "")).strip(),
                                to_stage=str(payload.get("to_stage", "")).strip(),
                                actor=str(payload.get("actor", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "promote_failed"))]
                            run_result = result
                        elif action == "rollback_stage":
                            result = reg.rollback_adapter(
                                adapter_key=str(payload.get("adapter_key", "")).strip(),
                                actor=str(payload.get("actor", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "rollback_failed"))]
                            run_result = result
                        elif action == "request_stage_change":
                            result = reg.request_stage_change(
                                adapter_key=str(payload.get("adapter_key", "")).strip(),
                                action=str(payload.get("change_action", "")).strip().lower(),
                                target_stage=str(payload.get("target_stage", "")).strip(),
                                requested_by=str(payload.get("requested_by", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "request_stage_failed"))]
                            run_result = result
                        elif action == "approve_stage_change":
                            result = reg.approve_stage_change(
                                approval_id=int(payload.get("approval_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "approve_stage_failed"))]
                            run_result = result
                        elif action == "reject_stage_change":
                            result = reg.reject_stage_change(
                                approval_id=int(payload.get("approval_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "reject_stage_failed"))]
                            run_result = result
                        elif action == "request_key_rotation":
                            result = reg.request_signature_key_rotation(
                                key_type=str(payload.get("key_type", "")).strip().lower(),
                                requested_key_id=str(payload.get("requested_key_id", "")).strip(),
                                requested_by=str(payload.get("requested_by", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "request_key_rotation_failed"))]
                            run_result = result
                        elif action == "approve_key_rotation":
                            result = reg.approve_signature_key_rotation(
                                rotation_id=int(payload.get("rotation_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "approve_key_rotation_failed"))]
                            run_result = result
                        elif action == "reject_key_rotation":
                            result = reg.reject_signature_key_rotation(
                                rotation_id=int(payload.get("rotation_id", 0) or 0),
                                approver=str(payload.get("approver", "dashboard")),
                                reason=str(payload.get("reason", "")),
                            )
                            ok = bool(result.get("ok"))
                            if not ok:
                                errors = [str(result.get("error", "reject_key_rotation_failed"))]
                            run_result = result
                        elif action == "run":
                            from modules.tooling_runner import ToolingRunner
                            adapter_key = str(payload.get("adapter_key", "")).strip()
                            run_result = ToolingRunner().run(
                                adapter_key=adapter_key,
                                input_data=payload.get("input", {}) if isinstance(payload.get("input", {}), dict) else {},
                                dry_run=bool(payload.get("dry_run", True)),
                            )
                            ok = run_result.get("status") in {"dry_run", "prepared", "ok"}
                            if not ok:
                                errors = [str(run_result.get("error", "run_failed"))]
                    except Exception:
                        ok = False
                    if ok:
                        try:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(actor="dashboard", decision="tooling_registry_update", rationale=action)
                        except Exception:
                            pass
                    self._json({"ok": ok, "action": action, "errors": errors, "result": run_result})
                    return
                if parsed.path == "/api/secrets":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    allowed = {
                        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                        "PERPLEXITY_API_KEY", "OPENROUTER_API_KEY",
                        "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID",
                        "GUMROAD_API_KEY", "GUMROAD_OAUTH_TOKEN", "GUMROAD_APP_ID", "GUMROAD_APP_SECRET",
                        "ETSY_KEYSTRING", "ETSY_SHARED_SECRET", "KOFI_API_KEY", "KOFI_PAGE_ID",
                        "REPLICATE_API_TOKEN", "ANTICAPTCHA_KEY",
                        "TWITTER_BEARER_TOKEN", "TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET",
                        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
                        "OPENROUTER_DEFAULT_MODEL",
                    }
                    updated = {}
                    for k,v in payload.items():
                        if k in allowed:
                            updated[k] = "set"
                            try:
                                import os
                                os.environ[k] = str(v)
                                if hasattr(settings, k):
                                    setattr(settings, k, v if not isinstance(v, str) else v)
                            except Exception:
                                pass
                    # write to .env
                    try:
                        from pathlib import Path
                        import re
                        env_path = Path("/home/vito/vito-agent/.env")
                        text = env_path.read_text() if env_path.exists() else ""
                        for k,v in payload.items():
                            if k not in allowed:
                                continue
                            if re.search(rf"^{k}=.*$", text, flags=re.M):
                                text = re.sub(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
                            else:
                                if text and not text.endswith("\n"):
                                    text += "\n"
                                text += f"{k}={v}\n"
                        env_path.write_text(text)
                    except Exception:
                        pass
                    try:
                        if updated:
                            from modules.data_lake import DataLake
                            DataLake().record_decision(
                                actor="dashboard",
                                decision="secrets_update",
                                rationale=", ".join(sorted(updated.keys()))[:1000],
                            )
                    except Exception:
                        pass
                    self._json({"updated": updated})
                    return
                if parsed.path == "/api/rss":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = payload.get("action", "")
                    try:
                        from modules.rss_registry import RSSRegistry
                        reg = RSSRegistry()
                        if action == "add":
                            name = payload.get("name", "source")
                            url = payload.get("url", "")
                            if url:
                                reg.add_source(name=name, url=url)
                        elif action == "toggle":
                            reg.toggle_source(int(payload.get("id")), bool(payload.get("enabled")))
                        elif action == "remove":
                            reg.remove_source(int(payload.get("id")))
                    except Exception:
                        pass
                    try:
                        from modules.data_lake import DataLake
                        DataLake().record_decision(
                            actor="dashboard",
                            decision="rss_update",
                            rationale=f"action={action}",
                        )
                    except Exception:
                        pass
                    self._json({"ok": True})
                    return
                if parsed.path == "/api/goals/action":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    goal_id = str(payload.get("goal_id", "")).strip()
                    ok = False
                    details = ""
                    try:
                        if parent.goal_engine:
                            if action == "delete" and goal_id:
                                ok = bool(parent.goal_engine.delete_goal(goal_id))
                                details = f"delete:{goal_id}"
                            elif action == "fail" and goal_id:
                                parent.goal_engine.fail_goal(goal_id, "manual_fail_from_dashboard")
                                ok = True
                                details = f"fail:{goal_id}"
                            elif action == "clear_all":
                                cnt = parent.goal_engine.clear_all_goals()
                                ok = True
                                details = f"clear_all:{cnt}"
                            parent.goal_engine.reload_goals()
                        from modules.data_lake import DataLake
                        DataLake().record_decision(actor="dashboard", decision="goals_action", rationale=f"{action} {details}")
                    except Exception:
                        ok = False
                    self._json({"ok": ok, "action": action, "details": details})
                    return
                if parsed.path == "/api/schedules/action":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    task_id = int(payload.get("id", 0) or 0)
                    ok = False
                    try:
                        if parent.schedule_manager and action == "delete" and task_id > 0:
                            parent.schedule_manager.delete_task(task_id)
                            ok = True
                        from modules.data_lake import DataLake
                        DataLake().record_decision(actor="dashboard", decision="schedule_action", rationale=f"{action} {task_id}")
                    except Exception:
                        ok = False
                    self._json({"ok": ok, "action": action, "id": task_id})
                    return
                if parsed.path == "/api/loop/action":
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    ok = False
                    try:
                        if parent.decision_loop:
                            if action == "stop":
                                parent.decision_loop.stop()
                                ok = True
                            elif action == "start":
                                import asyncio as _asyncio
                                if not getattr(parent.decision_loop, "running", False):
                                    _asyncio.create_task(parent.decision_loop.run())
                                    ok = True
                                else:
                                    ok = True
                        from modules.data_lake import DataLake
                        DataLake().record_decision(actor="dashboard", decision="loop_action", rationale=action)
                    except Exception:
                        ok = False
                    self._json({"ok": ok, "action": action})
                    return
                self._text("Not Found", 404)

        return Handler

    def start(self) -> None:
        if not getattr(settings, "DASHBOARD_ENABLED", True):
            return
        host = getattr(settings, "DASHBOARD_HOST", "0.0.0.0")
        port = int(getattr(settings, "DASHBOARD_PORT", 8787))
        handler = self._build_handler()
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
