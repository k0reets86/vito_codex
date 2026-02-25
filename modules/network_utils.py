import os
import socket
import time


def _seccomp_mode() -> int:
    try:
        with open(f"/proc/{os.getpid()}/status", "r") as f:
            for line in f:
                if line.startswith("Seccomp:"):
                    return int(line.split(":", 1)[1].strip())
    except Exception:
        return 0
    return 0


def network_blocked_reason() -> str | None:
    # Seccomp mode 2 indicates a filter is active; likely blocking sockets.
    if _seccomp_mode() == 2:
        return "seccomp_filter"
    return None


def dns_ok(host: str, timeout_sec: float = 2.0) -> bool:
    start = time.time()
    try:
        socket.setdefaulttimeout(timeout_sec)
        socket.gethostbyname(host)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(None)
        _ = time.time() - start


def network_available(hosts: list[str] | None = None) -> bool:
    if network_blocked_reason():
        return False
    hosts = hosts or ["api.telegram.org", "gumroad.com", "api.gumroad.com", "google.com"]
    for h in hosts:
        if dns_ok(h):
            return True
    return False


def network_status(hosts: list[str] | None = None) -> dict:
    reason = network_blocked_reason()
    if reason:
        return {"ok": False, "reason": reason}
    hosts = hosts or ["api.telegram.org", "gumroad.com", "api.gumroad.com", "google.com"]
    ok = any(dns_ok(h) for h in hosts)
    return {"ok": ok, "reason": None if ok else "dns_unavailable"}


def basic_net_report(hosts: list[str] | None = None) -> dict:
    """Lightweight report for comms: no external HTTP, just DNS reachability."""
    hosts = hosts or ["api.telegram.org", "gumroad.com", "api.gumroad.com", "google.com"]
    seccomp = network_blocked_reason()
    results = {h: dns_ok(h) for h in hosts} if not seccomp else {h: False for h in hosts}
    return {
        "seccomp": seccomp,
        "dns": results,
        "ok": any(results.values()) and not seccomp,
    }
