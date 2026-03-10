from __future__ import annotations

import shlex
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

try:
    import paramiko
except Exception:  # pragma: no cover - optional runtime dependency
    paramiko = None


@dataclass
class LogReaderConfig:
    ssh_host: str
    ssh_user: str
    ssh_key_path: str
    log_path: str


class VITOLogReader:
    def __init__(
        self,
        *,
        ssh_host: str | None = None,
        ssh_user: str | None = None,
        ssh_key_path: str | None = None,
        log_path: str | None = None,
        ssh_client_factory=None,
    ) -> None:
        import os

        self.config = LogReaderConfig(
            ssh_host=ssh_host or os.getenv("SSH_HOST", ""),
            ssh_user=ssh_user or os.getenv("SSH_USER", ""),
            ssh_key_path=ssh_key_path or os.getenv("SSH_KEY_PATH", ""),
            log_path=log_path or os.getenv("VITO_LOG_PATH", "/home/vito/vito-agent/logs/vito.log"),
        )
        self._ssh_client_factory = ssh_client_factory
        self.ssh = None
        self._connected = False

    def _build_client(self):
        if self._ssh_client_factory is not None:
            return self._ssh_client_factory()
        if paramiko is None:
            raise RuntimeError(
                "paramiko is not installed. Install requirements_tester.txt or inject ssh_client_factory."
            )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def connect(self) -> bool:
        if not self.config.ssh_host or not self.config.ssh_user:
            return False
        try:
            self.ssh = self._build_client()
            self.ssh.connect(
                hostname=self.config.ssh_host,
                username=self.config.ssh_user,
                key_filename=self.config.ssh_key_path or None,
                timeout=10,
            )
            self._connected = True
            return True
        except Exception:
            self._connected = False
            self.ssh = None
            return False

    def _exec(self, command: str) -> str:
        if not self._connected or self.ssh is None:
            return ""
        _, stdout, _ = self.ssh.exec_command(command)
        return stdout.read().decode("utf-8", errors="replace")

    def tail_log(self, lines: int = 50) -> str:
        path = shlex.quote(self.config.log_path)
        return self._exec(f"tail -n {int(lines)} {path}")

    def grep_log(self, pattern: str, lines: int = 20) -> str:
        path = shlex.quote(self.config.log_path)
        safe_pattern = shlex.quote(pattern)
        return self._exec(f"grep -i {safe_pattern} {path} | tail -n {int(lines)}")

    def get_error_count(self) -> int:
        path = shlex.quote(self.config.log_path)
        raw = self._exec(f"grep -c 'ERROR\\|CRITICAL' {path} 2>/dev/null || echo 0").strip()
        try:
            return int(raw)
        except Exception:
            return -1

    def close(self) -> None:
        if self._connected and self.ssh is not None:
            self.ssh.close()
        self._connected = False
        self.ssh = None
