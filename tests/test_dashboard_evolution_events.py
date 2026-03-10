import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from dashboard_server import DashboardServer
from modules.evolution_events import EvolutionEventStore


def test_dashboard_serves_evolution_events(tmp_path, monkeypatch):
    db = tmp_path / 'dash.db'
    monkeypatch.setattr('config.settings.settings.SQLITE_PATH', str(db), raising=False)
    EvolutionEventStore(sqlite_path=str(db)).record_event(event_type='x', source='t', title='hello')
    dash = DashboardServer()
    handler = dash._build_handler()
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = f'http://127.0.0.1:{server.server_address[1]}/api/evolution_events'
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        assert data['events']
        assert data['events'][0]['event_type'] == 'x'
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=2)
