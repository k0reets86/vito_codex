import os

from modules.sandbox_manager import SandboxManager


def test_sandbox_manager_sanitizes_env(monkeypatch, tmp_path):
    monkeypatch.setenv('PATH', '/usr/bin')
    monkeypatch.setenv('HOME', '/tmp/home')
    monkeypatch.setenv('SECRET_TOKEN', 'topsecret')
    monkeypatch.setenv('EVOLUTION_SANDBOX_ALLOWED_ENV', 'PATH,HOME')
    mgr = SandboxManager(base_path=tmp_path, sandbox_root=tmp_path / 'sandboxes')
    env = mgr._build_subprocess_env()
    assert env['PATH'] == '/usr/bin'
    assert env['HOME'] == '/tmp/home'
    assert 'SECRET_TOKEN' not in env
