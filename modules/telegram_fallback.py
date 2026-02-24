"""Telegram fallback sender using curl with --resolve (bypass broken DNS)."""

import subprocess
from typing import Optional


FALLBACK_IPS = [
    "149.154.167.220",
    "149.154.167.221",
    "149.154.167.222",
    "149.154.167.223",
    "149.154.167.224",
]


def _resolve_ip(host: str) -> Optional[str]:
    # Use dig with public resolver (Cloudflare) to bypass local DNS
    try:
        result = subprocess.run(
            ["/usr/bin/dig", "+short", host, "@1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and line[0].isdigit():
                return line
    except Exception:
        return None
    # Fallback to known Telegram API IPs
    for ip in FALLBACK_IPS:
        return ip
    return None


def send_message(token: str, chat_id: str, text: str) -> bool:
    ip = _resolve_ip("api.telegram.org")
    if not ip:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        result = subprocess.run(
            [
                "/usr/bin/curl",
                "-sS",
                "--resolve",
                f"api.telegram.org:443:{ip}",
                url,
                "-d",
                f"chat_id={chat_id}",
                "-d",
                f"text={text}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def send_document(token: str, chat_id: str, file_path: str, caption: str = "") -> bool:
    ip = _resolve_ip("api.telegram.org")
    if not ip:
        return False
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        cmd = [
            "/usr/bin/curl",
            "-sS",
            "--resolve",
            f"api.telegram.org:443:{ip}",
            url,
            "-F",
            f"chat_id={chat_id}",
            "-F",
            f"document=@{file_path}",
        ]
        if caption:
            cmd += ["-F", f"caption={caption}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False
