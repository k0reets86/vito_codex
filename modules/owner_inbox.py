"""Owner inbox/outbox for offline testing (file-based communication)."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone


INBOX_DIR = Path("/home/vito/vito-agent/input/owner_inbox")
PROCESSED_DIR = Path("/home/vito/vito-agent/input/owner_inbox_processed")
OUTBOX_DIR = Path("/home/vito/vito-agent/output/owner_outbox")


def ensure_dirs() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def read_pending_messages(limit: int = 20) -> list[tuple[Path, str]]:
    ensure_dirs()
    files = sorted(INBOX_DIR.glob("*.txt"))
    results: list[tuple[Path, str]] = []
    for fp in files[:limit]:
        try:
            text = fp.read_text(encoding="utf-8").strip()
        except Exception:
            text = ""
        results.append((fp, text))
    return results


def mark_processed(fp: Path) -> None:
    ensure_dirs()
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = PROCESSED_DIR / f"{fp.stem}_{ts}.txt"
        fp.rename(dest)
    except Exception:
        pass


def write_outbox(text: str) -> Path:
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = OUTBOX_DIR / f"response_{ts}.txt"
    out.write_text(text, encoding="utf-8")
    return out


def write_inbox(text: str, prefix: str = "message") -> Path:
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    msg = INBOX_DIR / f"{prefix}_{ts}.txt"
    msg.write_text(text, encoding="utf-8")
    return msg


def read_outbox(limit: int = 20) -> list[tuple[Path, str]]:
    ensure_dirs()
    files = sorted(OUTBOX_DIR.glob("*.txt"))
    result: list[tuple[Path, str]] = []
    for fp in files[-limit:]:
        try:
            text = fp.read_text(encoding="utf-8").strip()
        except Exception:
            text = ""
        result.append((fp, text))
    return result
