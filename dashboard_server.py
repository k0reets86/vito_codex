"""Simple dashboard server for VITO (no external deps).

Provides:
- /         HTML dashboard
- /api/status
- /api/agents
- /api/goals
- /api/finance
- /api/schedules
- /api/platforms
- /api/config (GET/POST)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from config.settings import settings


class DashboardServer:
    def __init__(self, goal_engine=None, decision_loop=None, finance=None, registry=None, schedule_manager=None, platform_registry=None):
        self.goal_engine = goal_engine
        self.decision_loop = decision_loop
        self.finance = finance
        self.registry = registry
        self.schedule_manager = schedule_manager
        self.platform_registry = platform_registry
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

                if parsed.path == "/api/platforms":
                    rows = []
                    if parent.platform_registry:
                        rows = parent.platform_registry.list_platforms()
                    self._json({"platforms": rows})
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
                        stats = DataLake().agent_stats(days=30)
                    except Exception:
                        stats = []
                    self._json({"agent_kpi": stats})
                    return
                if parsed.path == "/api/models":
                    disabled = getattr(settings, "LLM_DISABLED_MODELS", "")
                    enabled = getattr(settings, "LLM_ENABLED_MODELS", "")
                    self._json({
                        "disabled": disabled,
                        "enabled": enabled,
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
      <div class=\"card\"><div class=\"mut\">Agents</div><div id=\"agents\"></div></div>
      <div class=\"card\"><div class=\"mut\">Finance</div><div id=\"finance\"></div></div>
      <div class=\"card\"><div class=\"mut\">Goals</div><div id=\"goals\"></div></div>
      <div class=\"card\"><div class=\"mut\">Schedules</div><div id=\"schedules\"></div></div>
      <div class=\"card\"><div class=\"mut\">Platforms</div><div id=\"platforms\"></div></div>
      <div class=\"card\"><div class=\"mut\">KPI</div><div id=\"kpi\"></div></div>
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
    status:'/api/status', agents:'/api/agents', finance:'/api/finance',
    goals:'/api/goals', schedules:'/api/schedules', config:'/api/config',
    platforms:'/api/platforms', rss:'/api/rss', kpi:'/api/kpi', models:'/api/models',
    facts:'/api/execution_facts', events:'/api/events', decisions:'/api/decisions', budget:'/api/budget'
  };
  for (const [k,url] of Object.entries(endpoints)){
    const r = await fetch(url); const j = await r.json();
    if (k === 'rss') renderRss(j.sources||[]);
    else if (k === 'agents') renderAgents(j.agents||[]);
    else if (k === 'goals') renderGoals(j.goals||[]);
    else if (k === 'platforms') renderPlatforms(j.platforms||[]);
    else if (k === 'kpi') renderKpi(j.agent_kpi||[]);
    else if (k === 'facts') renderFacts(j.facts||[]);
    else if (k === 'events') renderEvents(j.events||[]);
    else if (k === 'decisions') renderDecisions(j.decisions||[]);
    else if (k === 'budget') renderBudget(j.budget||[]);
    else if (k === 'status') renderStatus(j);
    else if (k === 'finance') renderFinance(j);
    else if (k === 'schedules') renderSchedules(j.tasks||[]);
    else if (k === 'config') renderConfig(j.config||j);
    else if (k === 'models') renderModels(j);
  }
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
}
function renderFinance(j){
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('finance').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderModels(j){
  const rows = Object.entries(j||{}).map(([k,v])=>`<tr><td>${k}</td><td>${JSON.stringify(v)}</td></tr>`).join('');
  document.getElementById('models').innerHTML = `<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
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
}
function renderPlatforms(items){
  const rows = items.map(p=>`<tr><td>${p.name}</td><td>${p.type}</td><td>${p.capabilities}</td><td>${p.configured?'yes':'no'}</td></tr>`).join('');
  document.getElementById('platforms').innerHTML = `<table><thead><tr><th>Platform</th><th>Type</th><th>Caps</th><th>Configured</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderKpi(items){
  const rows = items.map(k=>`<tr><td>${k.agent}</td><td>${k.ok}</td><td>${k.fail}</td><td>${k.total}</td></tr>`).join('');
  document.getElementById('kpi').innerHTML = `<table><thead><tr><th>Agent</th><th>OK</th><th>Fail</th><th>Total</th></tr></thead><tbody>${rows}</tbody></table>`;
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
                    for k,v in payload.items():
                        if k in allowed:
                            updated[k] = str(v)
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
                    self._json({"ok": True})
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
