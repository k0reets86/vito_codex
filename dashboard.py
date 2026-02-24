#!/usr/bin/env python3
"""VITO Dashboard (stdlib-only, modern UI).
Auth: ?token=vito2026 or cookie vito_auth=1
Port: 8787
"""

import html
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlparse

ROOT = Path("/home/vito/vito-agent")
MEMORY_DIR = ROOT / "memory"
DB_PATH = next(MEMORY_DIR.glob("*.db"), None)
LOG_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
MODULES_DIR = ROOT / "modules"
PLATFORMS_DIR = ROOT / "platforms"
ENV_PATH = ROOT / ".env"

PORT = 8787
AUTH_TOKEN = "vito2026"


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=5)
        return out.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"ERROR: {e}"


def _read_env() -> dict:
    data = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def _mask_value(k: str, v: str) -> str:
    if any(x in k.lower() for x in ["key", "token", "secret", "password"]):
        return "***"
    return v


def _html_table(headers, rows) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    tr = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def _system_status():
    status = _run(["systemctl", "is-active", "vito"]).strip()
    uptime = _run(["systemctl", "show", "vito", "-p", "ActiveEnterTimestamp"]).replace("ActiveEnterTimestamp=", "")
    pid = _run(["systemctl", "show", "vito", "-p", "MainPID"]).replace("MainPID=", "")
    cpu_mem = ""
    if pid and pid.isdigit():
        cpu_mem = _run(["ps", "-p", pid, "-o", "%cpu,%mem,etime", "--no-headers"])
    return {
        "status": status,
        "uptime": uptime,
        "pid": pid,
        "cpu_mem": cpu_mem,
    }


def _agents_status():
    rows = []
    for p in sorted(MODULES_DIR.glob("*.py")):
        ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        rows.append([p.name, ts])
    return rows


def _platforms_list():
    rows = []
    for p in sorted(PLATFORMS_DIR.glob("*.py")):
        rows.append([p.name])
    return rows


def _output_list():
    rows = []
    if OUTPUT_DIR.exists():
        for p in sorted(OUTPUT_DIR.rglob("*")):
            if p.is_file():
                size = p.stat().st_size
                ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                rows.append([str(p.relative_to(OUTPUT_DIR)), size, ts])
    return rows


def _goals_active():
    rows = []
    if not DB_PATH:
        return rows
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT goal_id,title,status,priority,estimated_cost_usd,created_at FROM goals "
        "WHERE status IN ('pending','executing','waiting_approval','planning') ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    con.close()
    return rows


def _finance_kpi():
    if not DB_PATH:
        return []
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = []
    try:
        cur.execute("SELECT date, SUM(cost_usd) FROM spend_log GROUP BY date ORDER BY date DESC LIMIT 7")
        rows = cur.fetchall()
    except Exception:
        rows = []
    con.close()
    return rows


def _recent_events():
    lines = []
    if LOG_DIR.exists():
        for p in sorted(LOG_DIR.glob("*.log")):
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    lines += [f"{p.name}: {ln.strip()}" for ln in f.readlines()[-10:]]
            except Exception:
                pass
    if not lines:
        out = _run(["journalctl", "-u", "vito", "-n", "50", "--no-pager"])
        lines = out.splitlines()[-50:]
    return lines[-50:]


HTML_TEMPLATE = Template(r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VITO Dashboard</title>
  <style>
    :root {
      --bg: #0d1117;
      --card: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #9aa0a6;
      --good: #00ff88;
      --bad: #ff4444;
      --warn: #f5c542;
      --shadow: 0 6px 18px rgba(0,0,0,0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .layout {
      display: grid;
      grid-template-columns: 260px 1fr;
      min-height: 100vh;
    }
    .sidebar {
      background: #0b0f14;
      border-right: 1px solid var(--border);
      padding: 18px;
      position: sticky;
      top: 0;
      height: 100vh;
    }
    .logo {
      font-weight: 800;
      font-size: 20px;
      letter-spacing: 0.5px;
      margin-bottom: 18px;
    }
    .nav a {
      display: block;
      padding: 10px 12px;
      border-radius: 8px;
      color: var(--muted);
      text-decoration: none;
      margin-bottom: 6px;
      border: 1px solid transparent;
    }
    .nav a.active {
      background: var(--card);
      color: var(--text);
      border-color: var(--border);
    }
    .main { padding: 18px 22px; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      gap: 12px;
      flex-wrap: wrap;
    }
    .header .title { font-size: 22px; font-weight: 800; }
    .header .meta { font-size: 12px; color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 14px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }
    .card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 700;
    }
    .badge {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      border: 1px solid var(--border);
      color: var(--muted);
    }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
    .dot.good { background: var(--good); }
    .dot.bad { background: var(--bad); }
    .dot.warn { background: var(--warn); }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 8px 6px; border-bottom: 1px solid var(--border); text-align: left; }
    th { color: var(--muted); font-weight: 700; }
    tbody tr:nth-child(even) { background: #10151c; }
    input, button {
      background: #0b0e12;
      color: var(--text);
      border: 1px solid var(--border);
      padding: 6px 8px;
      border-radius: 6px;
    }
    button { cursor: pointer; }
    pre { white-space: pre-wrap; word-wrap: break-word; font-size: 11px; color: var(--muted); }
    .pill { display: inline-flex; align-items: center; gap: 6px; }
    .section { scroll-margin-top: 16px; }
    @media (max-width: 1200px) {
      .grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { display: none; }
    }
  </style>
  <script>
    let countdown = 30;
    function tick() {
      const el = document.getElementById('countdown');
      if (el) el.textContent = countdown + 's';
      countdown -= 1;
      if (countdown < 0) { location.reload(); }
    }
    setInterval(tick, 1000);
    window.addEventListener('load', tick);
    window.addEventListener('hashchange', () => highlightNav());
    function highlightNav() {
      const hash = location.hash || '#status';
      document.querySelectorAll('.nav a').forEach(a => {
        a.classList.toggle('active', a.getAttribute('href') === hash);
      });
    }
    window.addEventListener('load', highlightNav);
  </script>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">VITO</div>
      <nav class="nav">
        <a class="active" href="#status">Status</a>
        <a href="#agents">Agents</a>
        <a href="#goals">Goals</a>
        <a href="#platforms">Platforms</a>
        <a href="#finance">Finance</a>
        <a href="#events">Events</a>
        <a href="#config">Config</a>
        <a href="#output">Output</a>
      </nav>
    </aside>
    <main class="main">
      <div class="header">
        <div class="title">VITO Dashboard</div>
        <div class="meta">Last updated: $updated · Auto-refresh in <span id="countdown">30s</span></div>
      </div>

      <div class="grid">
        <section id="status" class="card section">
          <div class="card-header">
            <div class="card-title">✅ System Status</div>
            <div class="badge"><span class="dot $status_dot"></span> $status_badge</div>
          </div>
          $system_status
        </section>

        <section id="agents" class="card section">
          <div class="card-header">
            <div class="card-title">🤖 Agents Status</div>
            <div class="badge">modules</div>
          </div>
          $agents_status
        </section>

        <section id="goals" class="card section">
          <div class="card-header">
            <div class="card-title">🎯 Goals (active)</div>
            <div class="badge">pipeline</div>
          </div>
          $goals
        </section>

        <section id="platforms" class="card section">
          <div class="card-header">
            <div class="card-title">📋 Platforms</div>
            <div class="badge">registry</div>
          </div>
          $platforms
        </section>

        <section id="finance" class="card section">
          <div class="card-header">
            <div class="card-title">💰 KPI / Finance</div>
            <div class="badge">last 7d</div>
          </div>
          $kpi
        </section>

        <section id="events" class="card section">
          <div class="card-header">
            <div class="card-title">⚠️ Recent Events</div>
            <div class="badge">last 50</div>
          </div>
          <pre>$events</pre>
        </section>

        <section id="config" class="card section">
          <div class="card-header">
            <div class="card-title">⚙️ Config (.env)</div>
            <div class="badge">write safe</div>
          </div>
          $config
          <form method="POST" action="/config" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="key" placeholder="KEY" style="flex:1; min-width:160px;" />
            <input name="value" placeholder="VALUE" style="flex:1; min-width:160px;" />
            <button type="submit">Set</button>
          </form>
          <div style="margin-top:8px; font-size:11px; color:var(--muted)">Secrets are write-only below.</div>
          <form method="POST" action="/secrets" style="margin-top:6px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="key" placeholder="KEY" style="flex:1; min-width:160px;" />
            <input name="value" placeholder="VALUE" style="flex:1; min-width:160px;" />
            <button type="submit">Set</button>
          </form>
        </section>

        <section id="output" class="card section">
          <div class="card-header">
            <div class="card-title">📁 Output Files</div>
            <div class="badge">artifacts</div>
          </div>
          $output
        </section>
      </div>
    </main>
  </div>
</body>
</html>
""")


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if "Cookie" in self.headers and "vito_auth=1" in self.headers["Cookie"]:
            return True
        q = parse_qs(urlparse(self.path).query)
        if q.get("token", [""])[0] == AUTH_TOKEN:
            return True
        return False

    def _set_cookie(self):
        self.send_header("Set-Cookie", "vito_auth=1; Path=/")

    def do_GET(self):
        if not self._authorized():
            q = parse_qs(urlparse(self.path).query)
            if q.get("token", [""])[0] == AUTH_TOKEN:
                self.send_response(HTTPStatus.FOUND)
                self._set_cookie()
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.end_headers()
            self.wfile.write(b"Unauthorized. Add ?token=vito2026")
            return

        sys = _system_status()
        status_badge = sys.get("status", "unknown")
        status_dot = "warn"
        if status_badge == "active":
            status_dot = "good"
        elif status_badge in {"inactive", "failed"}:
            status_dot = "bad"

        system_table = _html_table(["Key", "Value"], list(sys.items()))
        agents_table = _html_table(["Module", "Last Modified"], _agents_status())
        platforms_table = _html_table(["File"], _platforms_list())
        goals_table = _html_table(["ID", "Title", "Status", "Priority", "Cost", "Created"], _goals_active())
        kpi_table = _html_table(["Date", "Spend"], _finance_kpi())
        output_table = _html_table(["File", "Size", "Modified"], _output_list())
        env = _read_env()
        cfg_rows = [(k, _mask_value(k, v)) for k, v in env.items()]
        cfg_table = _html_table(["Key", "Value"], cfg_rows)
        events = "\n".join(_recent_events())

        html_out = HTML_TEMPLATE.safe_substitute(
            updated=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            status_badge=status_badge,
            status_dot=status_dot,
            system_status=system_table,
            agents_status=agents_table,
            platforms=platforms_table,
            goals=goals_table,
            kpi=kpi_table,
            events=html.escape(events),
            output=output_table,
            config=cfg_table,
        )
        data = html_out.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._authorized():
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        params = parse_qs(raw)
        key = params.get("key", [""])[0].strip()
        value = params.get("value", [""])[0].strip()
        if not key:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()
            return
        env = _read_env()
        env[key] = value
        lines = [f"{k}={v}" for k, v in env.items()]
        ENV_PATH.write_text("\n".join(lines) + "\n")
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.end_headers()


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
