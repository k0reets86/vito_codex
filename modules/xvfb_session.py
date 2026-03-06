"""Lightweight Xvfb session helper for headed browser flows on headless servers."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


class XvfbSession:
    def __init__(self, enabled: bool, width: int = 1366, height: int = 900, depth: int = 24) -> None:
        self.enabled = bool(enabled)
        self.width = int(width)
        self.height = int(height)
        self.depth = int(depth)
        self._prev_display = os.environ.get("DISPLAY", "")
        self._proc: subprocess.Popen | None = None
        self.display = ""

    def start(self) -> None:
        if not self.enabled:
            return
        current_display = str(os.environ.get("DISPLAY", "")).strip()
        if current_display:
            checker = shutil.which("xdpyinfo")
            if checker:
                try:
                    ok = subprocess.run(
                        [checker, "-display", current_display],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1.5,
                        check=False,
                    )
                    if ok.returncode == 0:
                        return
                except Exception:
                    pass
                os.environ.pop("DISPLAY", None)
            else:
                return
        if shutil.which("Xvfb") is None:
            return
        for n in range(90, 140):
            disp = f":{n}"
            lock = Path(f"/tmp/.X{n}-lock")
            sock = Path(f"/tmp/.X11-unix/X{n}")
            if lock.exists() or sock.exists():
                continue
            try:
                proc = subprocess.Popen(
                    ["Xvfb", disp, "-screen", "0", f"{self.width}x{self.height}x{self.depth}", "-ac"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                time.sleep(1.0)
                if proc.poll() is None and (lock.exists() or sock.exists()):
                    self._proc = proc
                    self.display = disp
                    os.environ["DISPLAY"] = disp
                    return
                try:
                    proc.terminate()
                except Exception:
                    pass
            except Exception:
                continue

    def stop(self) -> None:
        try:
            if self._proc is not None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except Exception:
                    self._proc.kill()
        except Exception:
            pass
        finally:
            self._proc = None
            if self._prev_display:
                os.environ["DISPLAY"] = self._prev_display
            else:
                os.environ.pop("DISPLAY", None)
