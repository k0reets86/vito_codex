"""Simple dashboard server for VITO (no external deps).

Provides:
- /         HTML dashboard
- /api/status
- /api/agents
- /api/goals
- /api/finance
- /api/schedules
- /api/prefs
- /api/platforms
- /api/config (GET/POST)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from config.settings import settings
from modules.owner_preference_model import OwnerPreferenceModel


class DashboardServer:
    def __init__(self, goal_engine=None, decision_loop=None, finance=None, registry=None, schedule_manager=None, platform_registry=None, llm_router=None, publisher_queue=None):
        self.goal_engine = goal_engine
        self.decision_loop = decision_loop
        self.finance = finance
        self.registry = registry
        self.schedule_manager = schedule_manager
        self.platform_registry = platform_registry
        self.llm_router = llm_router
        self.publisher_queue = publisher_queue
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
                    self._json({
                        "disabled": disabled,
                        "enabled": enabled,
                    })
                    return
                if parsed.path == "/api/llm_policy":
                    try:
                        report = parent.llm_router.get_policy_report(days=1) if parent.llm_router else {}
                    except Exception:
                        report = {}
                    self._json({"policy": report})
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
                if parsed.path == "/api/execution_facts":
                    try:
                        from modules.execution_facts import ExecutionFacts
                        facts = ExecutionFacts().recent_facts(limit=20)
                        facts_out = [f.__dict__ for f in facts]
                    except Exception:
                        facts_out = []
                    self._json({"facts": facts_out})
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
      <div class=\"card\"><div class=\"mut\">Execution Facts</div><div id=\"facts\"></div></div>
      <div class=\"card\"><div class=\"mut\">Recent Events</div><div id=\"events\"></div></div>
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
      <div class=\"card\"><div class=\"mut\">Secrets</div>
        <div class=\"mut\" style=\"font-size:12px\">Keys are write‑only here.</div>
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
    platforms:'/api/platforms', platform_scorecard:'/api/platform_scorecard', rss:'/api/rss', kpi:'/api/kpi', kpi_trend:'/api/kpi_trend', models:'/api/models', llm_policy:'/api/llm_policy', prefs:'/api/prefs',
    facts:'/api/execution_facts', events:'/api/events', decisions:'/api/decisions', budget:'/api/budget'
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
    else if (k === 'events') renderEvents(j.events||[]);
    else if (k === 'decisions') renderDecisions(j.decisions||[]);
    else if (k === 'budget') renderBudget(j.budget||[]);
    else if (k === 'status') renderStatus(j);
    else if (k === 'network') renderNetwork(j.network||{});
    else if (k === 'finance') renderFinance(j);
    else if (k === 'schedules') renderSchedules(j.tasks||[]);
    else if (k === 'config') renderConfig(j.config||j);
    else if (k === 'prefs') renderPrefs(j.preferences||[]);
    else if (k === 'models') renderModels(j);
    else if (k === 'llm_policy') renderLlmPolicy(j.policy||{});
  }
}
function renderPrefs(prefs){
  const el = document.getElementById('prefs');
  if (!prefs.length){ el.innerHTML = '<div class=\"mut\">No prefs</div>'; return; }
  const rows = prefs.map(p => `<div style=\"margin:4px 0\"><code>${p.pref_key}</code>: ${JSON.stringify(p.value)} <span class=\"mut\">(conf=${(p.confidence||0).toFixed(2)})</span></div>`);
  el.innerHTML = rows.join('');
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
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('models').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
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
function renderEvents(items){
  const rows = items.map(e=>`<tr><td>${e.agent}</td><td>${e.task_type}</td><td>${e.status}</td><td>${e.created_at}</td></tr>`).join('');
  document.getElementById('events').innerHTML = `<table><thead><tr><th>Agent</th><th>Task</th><th>Status</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
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
async function setConfig(){
  const k = document.getElementById('cfg_key').value.trim();
  const v = document.getElementById('cfg_val').value.trim();
  if (!k) return;
  await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({[k]: v})});
  await load();
}
async function addRss(){
  const name = document.getElementById('rss_name').value.trim() || 'source';
  const url = document.getElementById('rss_url').value.trim();
  if (!url) return;
  await fetch('/api/rss', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'add', name, url})});
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
                    }
                    updated = {}
                    bool_keys = {"PROACTIVE_ENABLED", "BRAINSTORM_WEEKLY", "OWNER_INBOX_ENABLED", "CALENDAR_UPDATE_LLM"}
                    num_keys = {"DAILY_LIMIT_USD", "OPERATION_NOTIFY_USD", "OPERATION_APPROVE_USD", "OPERATION_MAX_USD"}
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
