"""Process-wide display bootstrap for browser automation (Xvfb)."""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import time
from pathlib import Path

_XVFB_PROC: subprocess.Popen | None = None
_XVFB_DISPLAY: str = ""


def _display_alive(display: str) -> bool:
    if not display:
        return False
    checker = shutil.which("xdpyinfo")
    if not checker:
        return bool(os.environ.get("DISPLAY"))
    try:
        res = subprocess.run(
            [checker, "-display", display],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _pick_display() -> str:
    for n in range(95, 130):
        if not Path(f"/tmp/.X{n}-lock").exists() and not Path(f"/tmp/.X11-unix/X{n}").exists():
            return f":{n}"
    return ":99"


def _stop() -> None:
    global _XVFB_PROC, _XVFB_DISPLAY
    try:
        if _XVFB_PROC is not None:
            _XVFB_PROC.terminate()
            try:
                _XVFB_PROC.wait(timeout=2)
            except Exception:
                _XVFB_PROC.kill()
    except Exception:
        pass
    finally:
        _XVFB_PROC = None
        _XVFB_DISPLAY = ""


def ensure_display() -> str:
    """Ensure DISPLAY is available for headed Playwright sessions."""
    global _XVFB_PROC, _XVFB_DISPLAY
    cur = str(os.getenv("DISPLAY", "")).strip()
    if cur and _display_alive(cur):
        return cur
    if _XVFB_PROC is not None and _XVFB_PROC.poll() is None and _XVFB_DISPLAY:
        os.environ["DISPLAY"] = _XVFB_DISPLAY
        return _XVFB_DISPLAY
    if shutil.which("Xvfb") is None:
        return ""
    display = _pick_display()
    try:
        proc = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1366x900x24", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        time.sleep(1.0)
        if proc.poll() is None and _display_alive(display):
            _XVFB_PROC = proc
            _XVFB_DISPLAY = display
            os.environ["DISPLAY"] = display
            atexit.register(_stop)
            return display
        try:
            proc.terminate()
        except Exception:
            pass
    except Exception:
        return ""
    return ""
