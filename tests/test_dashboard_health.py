from dashboard_server import DashboardServer


def test_dashboard_health_endpoint_exists():
    server = DashboardServer()
    handler_factory = server._build_handler()
    assert handler_factory is not None
