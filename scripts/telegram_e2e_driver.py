#!/usr/bin/env python3
"""Telegram E2E driver for VITO.

Runs scripted Telegram dialogues against the running bot, validates expected
reply patterns, and writes a timestamped JSON report to reports/.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


@dataclass
class Step:
    id: str
    text: str
    expect_any: list[str]
    reject_any: list[str]
    timeout_sec: int = 45


def _builtin_scenario(name: str) -> list[Step]:
    n = name.strip().lower()
    if n == "smoke":
        return [
            Step("S01_start", "/start", ["vito", "готов"], ["traceback", "exception"], 35),
            Step("S02_help", "/help", ["справка", "help", "команд"], ["traceback", "exception"], 35),
            Step("S03_status", "статус", ["статус", "vito", "агент"], ["traceback", "exception"], 45),
            Step("S04_tasks", "задачи", ["задач", "очеред"], ["traceback", "exception"], 45),
        ]
    if n == "kdp_login_init":
        return [
            Step(
                "KDP01_login_start",
                "зайди на амазон",
                [
                    "6-знач",
                    "код из amazon",
                    "вход уже подтвержд",
                    "повторный логин не требуется",
                ],
                ["traceback", "exception"],
                90,
            ),
        ]
    raise ValueError(f"Unknown scenario: {name}")


def _load_scenario(path: str) -> list[Step]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    steps = []
    for i, item in enumerate(raw.get("steps", []), start=1):
        steps.append(
            Step(
                id=str(item.get("id") or f"STEP{i:02d}"),
                text=str(item.get("text") or "").strip(),
                expect_any=[str(x).lower() for x in (item.get("expect_any") or [])],
                reject_any=[str(x).lower() for x in (item.get("reject_any") or [])],
                timeout_sec=int(item.get("timeout_sec") or 45),
            )
        )
    if not steps:
        raise ValueError("Scenario has no steps")
    return steps


class TelegramE2E:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = int(str(chat_id).strip())
        self.base = _api_url(token, "")
        self.offset = 0

    def get_updates(self, timeout_sec: int = 2) -> list[dict[str, Any]]:
        url = _api_url(self.token, "getUpdates")
        q = parse.urlencode(
            {
                "offset": self.offset,
                "timeout": max(0, int(timeout_sec)),
                "allowed_updates": json.dumps(["message", "edited_message"]),
            }
        )
        try:
            data = _get_json(f"{url}?{q}", timeout=timeout_sec + 5)
        except HTTPError as e:
            if int(getattr(e, "code", 0) or 0) == 409:
                raise RuntimeError("telegram_getupdates_conflict_409") from e
            raise
        if not data.get("ok"):
            return []
        rows = data.get("result") or []
        if rows:
            self.offset = int(rows[-1].get("update_id", 0)) + 1
        return rows

    def flush(self) -> None:
        # Consume backlog so we only inspect fresh replies.
        for _ in range(3):
            self.get_updates(timeout_sec=1)

    def send_message(self, text: str) -> dict[str, Any]:
        url = _api_url(self.token, "sendMessage")
        payload = {"chat_id": self.chat_id, "text": text}
        return _post_json(url, payload, timeout=20)

    def wait_bot_reply(self, after_ts: int, timeout_sec: int) -> dict[str, Any] | None:
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            updates = self.get_updates(timeout_sec=2)
            for u in updates:
                msg = u.get("message") or u.get("edited_message") or {}
                chat = msg.get("chat") or {}
                if int(chat.get("id", 0)) != self.chat_id:
                    continue
                dt = int(msg.get("date", 0))
                sender = msg.get("from") or {}
                if dt < after_ts:
                    continue
                if not bool(sender.get("is_bot")):
                    continue
                return msg
            time.sleep(0.3)
        return None


class TelegramTraceReader:
    def __init__(self, trace_file: Path):
        self.trace_file = trace_file

    @staticmethod
    def _parse_ts(s: str) -> float:
        try:
            return datetime.fromisoformat(s).timestamp()
        except Exception:
            return 0.0

    def wait_reply(
        self,
        sent_text: str,
        after_ts: float,
        timeout_sec: int,
        from_pos: int = 0,
    ) -> tuple[str, int]:
        deadline = time.time() + max(1, int(timeout_sec))
        owner_in_seen_at = 0.0
        pos = int(max(0, from_pos))
        while time.time() < deadline:
            if not self.trace_file.exists():
                time.sleep(0.4)
                continue
            with self.trace_file.open("r", encoding="utf-8", errors="ignore") as fh:
                try:
                    fh.seek(pos)
                except Exception:
                    pos = 0
                    fh.seek(0)
                chunk = fh.read()
                pos = fh.tell()
            if not chunk:
                time.sleep(0.4)
                continue
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = self._parse_ts(str(row.get("ts") or ""))
                if ts < float(after_ts):
                    continue
                direction = str(row.get("direction") or "").strip().lower()
                txt = str(row.get("text") or "")
                if direction == "in" and txt.strip().lower() == sent_text.strip().lower():
                    owner_in_seen_at = ts
                    continue
                if direction == "out":
                    if owner_in_seen_at and ts >= owner_in_seen_at:
                        return txt, pos
                    if not owner_in_seen_at and ts >= float(after_ts):
                        return txt, pos
        return "", pos


def _check_reply(text: str, expect_any: list[str], reject_any: list[str]) -> tuple[bool, list[str]]:
    low = text.lower()
    reasons: list[str] = []
    if expect_any and not any(s in low for s in expect_any):
        reasons.append(f"missing expected markers: {expect_any}")
    bad = [s for s in reject_any if s in low]
    if bad:
        reasons.append(f"contains rejected markers: {bad}")
    return len(reasons) == 0, reasons


def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="smoke", help="Built-in scenario name: smoke | kdp_login_init")
    ap.add_argument("--scenario-file", default="", help="JSON file with steps[]")
    ap.add_argument("--mode", default="auto", choices=["auto", "updates", "trace"], help="Reply read mode")
    ap.add_argument("--trace-file", default="runtime/telegram_trace.jsonl", help="Trace file for mode=trace/auto fallback")
    ap.add_argument("--out", default="", help="Optional report path")
    args = ap.parse_args()

    token = str(getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = str(getattr(settings, "TELEGRAM_OWNER_CHAT_ID", "") or "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_CHAT_ID not configured")

    if args.scenario_file:
        steps = _load_scenario(args.scenario_file)
        scenario_name = Path(args.scenario_file).stem
    else:
        steps = _builtin_scenario(args.scenario)
        scenario_name = args.scenario.strip().lower()

    tg = TelegramE2E(token, chat_id)
    trace_reader = TelegramTraceReader(ROOT / args.trace_file)
    trace_pos = 0
    read_mode = str(args.mode or "auto").strip().lower()
    if read_mode in ("auto", "updates"):
        tg.flush()

    report: dict[str, Any] = {
        "timestamp": _utc_now(),
        "scenario": scenario_name,
        "mode": read_mode,
        "steps": [],
        "summary": {"passed": 0, "failed": 0, "total": len(steps)},
    }

    for st in steps:
        sent = tg.send_message(st.text)
        send_ok = bool(sent.get("ok"))
        start_ts = int(time.time()) - 1
        reply_text = ""
        mode_used = read_mode
        msg = None
        if send_ok:
            if read_mode == "trace":
                reply_text, trace_pos = trace_reader.wait_reply(
                    sent_text=st.text,
                    after_ts=float(start_ts),
                    timeout_sec=st.timeout_sec,
                    from_pos=trace_pos,
                )
            else:
                try:
                    msg = tg.wait_bot_reply(after_ts=start_ts, timeout_sec=st.timeout_sec)
                    reply_text = str((msg or {}).get("text") or "")
                except RuntimeError as e:
                    if "conflict_409" not in str(e) or read_mode == "updates":
                        raise
                    mode_used = "trace"
                    report["mode"] = "trace"
                    reply_text, trace_pos = trace_reader.wait_reply(
                        sent_text=st.text,
                        after_ts=float(start_ts),
                        timeout_sec=st.timeout_sec,
                        from_pos=trace_pos,
                    )
        ok, reasons = _check_reply(reply_text, st.expect_any, st.reject_any)
        step_row = {
            "id": st.id,
            "input": st.text,
            "send_ok": send_ok,
            "reply_text": reply_text,
            "mode_used": mode_used,
            "pass": bool(send_ok and reply_text and ok),
            "reasons": reasons if not (send_ok and reply_text and ok) else [],
            "at": _utc_now(),
        }
        if not reply_text:
            step_row["pass"] = False
            step_row["reasons"] = ["no bot reply within timeout"]
        report["steps"].append(step_row)
        if step_row["pass"]:
            report["summary"]["passed"] += 1
        else:
            report["summary"]["failed"] += 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    out_path = Path(args.out) if args.out else (ROOT / "reports" / f"VITO_TELEGRAM_E2E_{scenario_name}_{ts}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
