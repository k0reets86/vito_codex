#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/runtime/etsy_remote"
DISPLAY_NUM="${ETSY_REMOTE_DISPLAY:-:99}"
VNC_PORT="${ETSY_REMOTE_VNC_PORT:-5901}"
NOVNC_PORT="${ETSY_REMOTE_NOVNC_PORT:-6080}"
PASS_FILE="$RUNTIME_DIR/vnc.pass"
LOG_FILE="$RUNTIME_DIR/session.log"
PID_DIR="$RUNTIME_DIR/pids"

mkdir -p "$RUNTIME_DIR" "$PID_DIR"

_pid_alive() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local p
    p="$(cat "$f" 2>/dev/null || true)"
    [[ -n "${p}" ]] && kill -0 "$p" 2>/dev/null
  else
    return 1
  fi
}

_kill_pidfile() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local p
    p="$(cat "$f" 2>/dev/null || true)"
    if [[ -n "${p}" ]]; then
      kill "$p" 2>/dev/null || true
    fi
    rm -f "$f"
  fi
}

start() {
  if _pid_alive "$PID_DIR/websockify.pid"; then
    status
    return 0
  fi

  if [[ ! -f "$PASS_FILE" ]]; then
    python3 - <<'PY' >"$PASS_FILE"
import secrets, string
alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(12)))
PY
  fi
  chmod 600 "$PASS_FILE"
  x11vnc -storepasswd "$(cat "$PASS_FILE")" "$RUNTIME_DIR/.x11vnc.pass" >/dev/null 2>&1

  nohup Xvfb "$DISPLAY_NUM" -screen 0 1366x900x24 >"$RUNTIME_DIR/xvfb.log" 2>&1 &
  echo $! >"$PID_DIR/xvfb.pid"
  sleep 1

  DISPLAY="$DISPLAY_NUM" nohup openbox >"$RUNTIME_DIR/openbox.log" 2>&1 &
  echo $! >"$PID_DIR/openbox.pid"
  sleep 1

  DISPLAY="$DISPLAY_NUM" nohup x11vnc \
    -rfbport "$VNC_PORT" \
    -display "$DISPLAY_NUM" \
    -rfbauth "$RUNTIME_DIR/.x11vnc.pass" \
    -forever -shared -noxrecord -noxfixes -noxdamage \
    >"$RUNTIME_DIR/x11vnc.log" 2>&1 &
  echo $! >"$PID_DIR/x11vnc.pid"
  sleep 1

  nohup websockify --web /usr/share/novnc "$NOVNC_PORT" "127.0.0.1:$VNC_PORT" \
    >"$RUNTIME_DIR/websockify.log" 2>&1 &
  echo $! >"$PID_DIR/websockify.pid"
  sleep 1

  DISPLAY="$DISPLAY_NUM" nohup python3 "$ROOT_DIR/scripts/etsy_auth_helper.py" browser-capture \
    --timeout-sec 1200 \
    --storage-path "$ROOT_DIR/runtime/etsy_storage_state.json" \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_DIR/capture.pid"

  local host
  host="${ETSY_REMOTE_HOST:-$(hostname -I | awk '{print $1}')}"
  echo "REMOTE_URL=http://${host}:${NOVNC_PORT}/vnc.html?resize=remote&autoconnect=1&view_only=0"
  echo "VNC_PASSWORD=$(cat "$PASS_FILE")"
  echo "CAPTURE_LOG=$LOG_FILE"
}

stop() {
  _kill_pidfile "$PID_DIR/capture.pid"
  _kill_pidfile "$PID_DIR/websockify.pid"
  _kill_pidfile "$PID_DIR/x11vnc.pid"
  _kill_pidfile "$PID_DIR/openbox.pid"
  _kill_pidfile "$PID_DIR/xvfb.pid"
  echo "stopped"
}

status() {
  local host
  host="${ETSY_REMOTE_HOST:-$(hostname -I | awk '{print $1}')}"
  echo "remote_url=http://${host}:${NOVNC_PORT}/vnc.html?resize=remote&autoconnect=1&view_only=0"
  echo "password=$(cat "$PASS_FILE" 2>/dev/null || echo '<not-set>')"
  for name in xvfb openbox x11vnc websockify capture; do
    local f="$PID_DIR/$name.pid"
    if _pid_alive "$f"; then
      echo "$name=running($(cat "$f"))"
    else
      echo "$name=stopped"
    fi
  done
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *)
    echo "Usage: $0 {start|stop|status}" >&2
    exit 1
    ;;
esac
