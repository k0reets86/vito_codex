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
from datetime import datetime, timezone
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


def _status_dot(status: str) -> str:
    s = (status or "").lower()
    if s in {"active", "running", "ok"}:
        return "good"
    if s in {"failed", "inactive", "error"}:
        return "bad"
    return "warn"


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


def _schedules_list():
    if not DB_PATH:
        return []
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = []
    try:
        cur.execute(
            "SELECT id,title,schedule_type,next_run,status FROM scheduled_tasks ORDER BY id DESC LIMIT 100"
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    con.close()
    return rows


def _network_status():
    hosts = ["api.telegram.org", "gumroad.com", "google.com"]
    out = []
    for h in hosts:
        ok = not _run(["getent", "hosts", h]).startswith("ERROR:")
        out.append([h, "ok" if ok else "fail"])
    return out


def _goal_delete(goal_id: str) -> bool:
    if not DB_PATH or not goal_id:
        return False
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("DELETE FROM goals WHERE goal_id = ?", (goal_id,))
        con.commit()
        return cur.rowcount > 0
    except Exception:
        return False
    finally:
        con.close()


def _goal_clear_all() -> int:
    if not DB_PATH:
        return 0
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("DELETE FROM goals")
        con.commit()
        return int(cur.rowcount or 0)
    except Exception:
        return 0
    finally:
        con.close()


def _schedule_delete(task_id: int) -> bool:
    if not DB_PATH or task_id <= 0:
        return False
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        con.commit()
        return cur.rowcount > 0
    except Exception:
        return False
    finally:
        con.close()


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


def _finance_summary(kpi_rows: list[tuple]) -> dict:
    spent = 0.0
    for row in kpi_rows:
        try:
            spent += float(row[1] or 0)
        except Exception:
            pass
    env = _read_env()
    try:
        limit = float(env.get("DAILY_LIMIT_USD", "3") or 3)
    except Exception:
        limit = 3.0
    earned = 0.0
    total = earned - spent
    pct = min(100.0, (spent / limit) * 100.0) if limit > 0 else 0.0
    return {"spent": spent, "earned": earned, "total": total, "limit": limit, "pct": pct}


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


def _format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    v = float(size)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            return f"{v:.1f}{u}"
        v /= 1024.0
    return f"{size}B"


def _module_status(name: str) -> str:
    lower = name.lower()
    if "core" in lower or "decision" in lower or "memory" in lower or "router" in lower:
        return "active"
    if "error" in lower or "fail" in lower:
        return "error"
    return "idle"


def _platform_meta(filename: str) -> tuple[str, str]:
    name = filename.replace(".py", "").lower()
    mapping = [
        ("gumroad", "🛒"),
        ("etsy", "🧶"),
        ("shopify", "🛍️"),
        ("amazon", "📚"),
        ("kdp", "📚"),
        ("youtube", "▶️"),
        ("wordpress", "📰"),
        ("medium", "✍️"),
        ("twitter", "🐦"),
        ("kofi", "☕"),
        ("threads", "🧵"),
        ("instagram", "📸"),
        ("linkedin", "💼"),
        ("pinterest", "📌"),
    ]
    for key, icon in mapping:
        if key in name:
            return icon, key
    return "🌐", name


HTML_TEMPLATE = Template(r"""
<!doctype html>
<html lang="ru">
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
    .metrics { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin-bottom:10px; }
    .metric {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #10151c;
    }
    .metric .k { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
    .metric .v { font-size: 16px; font-weight: 700; margin-top: 4px; }
    .cards { display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; }
    .mini-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #10151c;
    }
    .mini-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
    .mini-title { font-weight: 700; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
    .mini-value { font-size: 22px; font-weight: 800; }
    .agent-grid { display:grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin-bottom: 10px; }
    .agent-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px;
      background: #10151c;
    }
    .agent-card .name { font-weight: 700; font-size: 13px; word-break: break-word; }
    .agent-card .meta { color: var(--muted); font-size: 11px; margin-top: 4px; }
    .task {
      border: 1px solid #2f3f57;
      border-radius: 8px;
      padding: 10px;
      background: #112033;
      margin-bottom: 10px;
    }
    .progress { width: 100%; background: #0b0e12; border:1px solid var(--border); border-radius: 999px; height: 8px; overflow: hidden; }
    .progress > div { height: 100%; background: linear-gradient(90deg,#00ff88,#1fbf8f); }
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
      .metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }
      .cards { grid-template-columns: 1fr; }
      .agent-grid { grid-template-columns: 1fr; }
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
        <a class="active" href="#status">Статус</a>
        <a href="#agents">Агенты</a>
        <a href="#goals">Цели</a>
        <a href="#schedules">Расписание</a>
        <a href="#network">Сеть</a>
        <a href="#platforms">Платформы</a>
        <a href="#finance">Финансы</a>
        <a href="#events">События</a>
        <a href="#config">Конфиг</a>
        <a href="#output">Файлы</a>
      </nav>
    </aside>
    <main class="main">
      <div class="header">
        <div class="title">VITO Dashboard</div>
        <div class="meta">Обновлено: $updated · Автообновление через <span id="countdown">30s</span></div>
      </div>

      <div class="grid">
        <section id="status" class="card section">
          <div class="card-header">
            <div class="card-title">✅ Состояние системы</div>
            <div class="badge"><span class="dot $status_dot"></span> $status_badge</div>
          </div>
          $status_metrics
          $current_task
          $system_status
        </section>

        <section id="agents" class="card section">
          <div class="card-header">
            <div class="card-title">🤖 Агенты</div>
            <div class="badge">$agents_count модулей</div>
          </div>
          $agents_cards
          $agents_status
        </section>

        <section id="goals" class="card section">
          <div class="card-header">
            <div class="card-title">🎯 Активные цели</div>
            <div class="badge">$goals_count</div>
          </div>
          $goals
          <form method="POST" action="/goals_action" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="goal_id" placeholder="goal_id" style="flex:1; min-width:160px;" />
            <button type="submit" name="action" value="delete">Удалить цель</button>
            <button type="submit" name="action" value="clear_all">Очистить все цели</button>
          </form>
        </section>

        <section id="schedules" class="card section">
          <div class="card-header">
            <div class="card-title">🗓️ Расписание</div>
            <div class="badge">$schedules_count</div>
          </div>
          $schedules
          <form method="POST" action="/schedules_action" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="task_id" placeholder="task_id" style="flex:1; min-width:160px;" />
            <button type="submit" name="action" value="delete">Удалить задачу</button>
          </form>
        </section>

        <section id="network" class="card section">
          <div class="card-header">
            <div class="card-title">🌐 Сеть</div>
            <div class="badge">DNS health</div>
          </div>
          $network
          <form method="POST" action="/service_action" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
            <button type="submit" name="action" value="restart_vito">Restart VITO</button>
            <button type="submit" name="action" value="restart_dashboard">Restart Dashboard</button>
          </form>
        </section>

        <section id="platforms" class="card section">
          <div class="card-header">
            <div class="card-title">📋 Платформы</div>
            <div class="badge">$platforms_count</div>
          </div>
          $platform_cards
          $platforms
        </section>

        <section id="finance" class="card section">
          <div class="card-header">
            <div class="card-title">💰 KPI / Финансы</div>
            <div class="badge">последние 7 дней</div>
          </div>
          $finance_cards
          $kpi
        </section>

        <section id="events" class="card section">
          <div class="card-header">
            <div class="card-title">⚠️ Последние события</div>
            <div class="badge">последние 50</div>
          </div>
          <pre>$events</pre>
        </section>

        <section id="config" class="card section">
          <div class="card-header">
            <div class="card-title">⚙️ Конфиг (.env)</div>
            <div class="badge">безопасная запись</div>
          </div>
          $config
          <form method="POST" action="/config" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="key" placeholder="KEY" style="flex:1; min-width:160px;" />
            <input name="value" placeholder="VALUE" style="flex:1; min-width:160px;" />
            <button type="submit">Сохранить</button>
          </form>
          <div style="margin-top:8px; font-size:11px; color:var(--muted)">Секреты ниже отображаются как write-only.</div>
          <form method="POST" action="/secrets" style="margin-top:6px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="key" placeholder="KEY" style="flex:1; min-width:160px;" />
            <input name="value" placeholder="VALUE" style="flex:1; min-width:160px;" />
            <button type="submit">Сохранить</button>
          </form>
          <form method="POST" action="/toggle" style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
            <input name="key" placeholder="Toggle KEY (e.g. PROACTIVE_ENABLED)" style="flex:1; min-width:220px;" />
            <button type="submit">Toggle</button>
          </form>
        </section>

        <section id="output" class="card section">
          <div class="card-header">
            <div class="card-title">📁 Файлы output</div>
            <div class="badge">$output_count</div>
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

        goals_rows = _goals_active()
        schedules_rows = _schedules_list()
        network_rows = _network_status()
        agents_rows = _agents_status()
        platform_rows = _platforms_list()
        kpi_rows = _finance_kpi()
        output_rows = _output_list()

        cpu, mem, etime = ("-", "-", "-")
        raw_cpu_mem = (sys.get("cpu_mem") or "").split()
        if len(raw_cpu_mem) >= 3:
            cpu, mem, etime = raw_cpu_mem[0], raw_cpu_mem[1], raw_cpu_mem[2]

        status_metrics = (
            '<div class="metrics">'
            f'<div class="metric"><div class="k">CPU</div><div class="v">{html.escape(cpu)}</div></div>'
            f'<div class="metric"><div class="k">RAM</div><div class="v">{html.escape(mem)}</div></div>'
            f'<div class="metric"><div class="k">Uptime</div><div class="v">{html.escape(etime)}</div></div>'
            f'<div class="metric"><div class="k">PID</div><div class="v">{html.escape(sys.get("pid", "-"))}</div></div>'
            "</div>"
        )
        current_task_html = "<div class='task'><div class='k'>Текущая задача</div><div class='v'>Нет активной цели</div></div>"
        if goals_rows:
            current_task_html = (
                "<div class='task'>"
                "<div class='k' style='color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em'>Текущая задача</div>"
                f"<div class='v' style='margin-top:6px;font-weight:700'>{html.escape(str(goals_rows[0][1]))}</div>"
                "</div>"
            )

        agent_cards = ["<div class='agent-grid'>"]
        for name, modified in agents_rows:
            st = _module_status(name)
            dot = _status_dot(st)
            label = "Активен" if st == "active" else ("Ошибка" if st == "error" else "Простой")
            agent_cards.append(
                "<div class='agent-card'>"
                f"<div class='name'>{html.escape(name.replace('.py',''))}</div>"
                f"<div class='meta'>{html.escape(modified)}</div>"
                f"<div class='meta'><span class='dot {dot}'></span> {label}</div>"
                "</div>"
            )
        agent_cards.append("</div>")
        agents_cards_html = "".join(agent_cards)

        platform_cards = ["<div class='cards'>"]
        env = _read_env()
        for (fname,) in platform_rows:
            icon, key = _platform_meta(fname)
            connected = any(k.startswith(key.upper()) and env.get(k) for k in env.keys())
            dot = "good" if connected else "warn"
            txt = "подключена" if connected else "без ключа"
            platform_cards.append(
                "<div class='mini-card'>"
                f"<div class='mini-head'><div class='mini-title'>{icon} {html.escape(fname.replace('.py',''))}</div><span class='dot {dot}'></span></div>"
                f"<div class='meta'>{txt}</div>"
                "</div>"
            )
        platform_cards.append("</div>")
        platform_cards_html = "".join(platform_cards)

        summary = _finance_summary(kpi_rows)
        finance_cards_html = (
            "<div class='cards'>"
            f"<div class='mini-card'><div class='mini-title'>Потрачено</div><div class='mini-value'>${summary['spent']:.2f}</div></div>"
            f"<div class='mini-card'><div class='mini-title'>Заработано</div><div class='mini-value'>${summary['earned']:.2f}</div></div>"
            f"<div class='mini-card'><div class='mini-title'>Итог</div><div class='mini-value'>${summary['total']:.2f}</div></div>"
            "</div>"
            "<div style='margin-top:8px'>"
            f"<div class='meta'>Лимит дня: ${summary['limit']:.2f}</div>"
            f"<div class='progress'><div style='width:{summary['pct']:.1f}%'></div></div>"
            "</div>"
        )

        system_table = _html_table(["Key", "Value"], list(sys.items()))
        agents_table = _html_table(["Module", "Last Modified"], agents_rows)
        platforms_table = _html_table(["File"], platform_rows)
        goals_table = _html_table(["ID", "Title", "Status", "Priority", "Cost", "Created"], goals_rows)
        schedules_table = _html_table(["ID", "Title", "Type", "Next run", "Status"], schedules_rows)
        network_table = _html_table(["Host", "DNS"], network_rows)
        kpi_table = _html_table(["Date", "Spend"], kpi_rows)
        output_table = _html_table(["File", "Size", "Modified"], output_rows)
        env = _read_env()
        cfg_rows = [(k, _mask_value(k, v)) for k, v in env.items()]
        cfg_table = _html_table(["Key", "Value"], cfg_rows)
        events = "\n".join(_recent_events())

        html_out = HTML_TEMPLATE.safe_substitute(
            updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            status_badge=status_badge,
            status_dot=status_dot,
            status_metrics=status_metrics,
            current_task=current_task_html,
            system_status=system_table,
            agents_count=len(agents_rows),
            goals_count=len(goals_rows),
            schedules_count=len(schedules_rows),
            platforms_count=len(platform_rows),
            output_count=len(output_rows),
            agents_cards=agents_cards_html,
            platform_cards=platform_cards_html,
            finance_cards=finance_cards_html,
            agents_status=agents_table,
            platforms=platforms_table,
            goals=goals_table,
            schedules=schedules_table,
            network=network_table,
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
        if urlparse(self.path).path == "/toggle":
            env = _read_env()
            cur = str(env.get(key, "false")).strip().lower()
            env[key] = "false" if cur in ("1", "true", "yes", "on") else "true"
            lines = [f"{k}={v}" for k, v in env.items()]
            ENV_PATH.write_text("\n".join(lines) + "\n")
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if urlparse(self.path).path == "/goals_action":
            action = params.get("action", [""])[0].strip()
            goal_id = params.get("goal_id", [""])[0].strip()
            if action == "delete" and goal_id:
                _goal_delete(goal_id)
            elif action == "clear_all":
                _goal_clear_all()
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/#goals")
            self.end_headers()
            return
        if urlparse(self.path).path == "/schedules_action":
            action = params.get("action", [""])[0].strip()
            task_id_raw = params.get("task_id", ["0"])[0].strip()
            try:
                task_id = int(task_id_raw)
            except Exception:
                task_id = 0
            if action == "delete" and task_id > 0:
                _schedule_delete(task_id)
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/#schedules")
            self.end_headers()
            return
        if urlparse(self.path).path == "/service_action":
            action = params.get("action", [""])[0].strip()
            if action == "restart_vito":
                _run(["systemctl", "restart", "vito"])
            elif action == "restart_dashboard":
                _run(["systemctl", "restart", "vito-dashboard"])
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/#network")
            self.end_headers()
            return
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
