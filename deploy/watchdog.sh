#!/bin/bash
# VITO RAM Watchdog
# Проверяет каждые 60 секунд. Если available RAM < 1GB — убивает опасные процессы.
# Логирует всё в journald через logger.

THRESHOLD_KB=1048576  # 1 GB in KB
CHECK_INTERVAL=60

log() {
    logger -t vito-watchdog "$1"
}

kill_dangerous_processes() {
    local killed=0

    # Kill headless_shell / chromium headless
    for pid in $(pgrep -f 'headless_shell|chromium.*--headless' 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null && {
            log "KILLED headless_shell pid=$pid"
            killed=$((killed + 1))
        }
    done

    # Kill pytest workers (but not the main pytest)
    for pid in $(pgrep -f 'pytest.*-n|pytest-worker' 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null && {
            log "KILLED pytest pid=$pid"
            killed=$((killed + 1))
        }
    done

    # Kill zombie processes owned by vito
    for pid in $(ps -u vito -o pid,stat | awk '$2 ~ /Z/ {print $1}'); do
        kill -9 "$pid" 2>/dev/null && {
            log "KILLED zombie pid=$pid"
            killed=$((killed + 1))
        }
    done

    echo "$killed"
}

log "Watchdog started. Threshold: ${THRESHOLD_KB}KB, interval: ${CHECK_INTERVAL}s"

while true; do
    # Get available memory in KB
    available_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)

    if [ -z "$available_kb" ]; then
        log "ERROR: Cannot read /proc/meminfo"
        sleep "$CHECK_INTERVAL"
        continue
    fi

    available_mb=$((available_kb / 1024))

    if [ "$available_kb" -lt "$THRESHOLD_KB" ]; then
        log "WARNING: Low RAM! Available: ${available_mb}MB (threshold: $((THRESHOLD_KB / 1024))MB). Killing dangerous processes..."
        killed=$(kill_dangerous_processes)
        log "Killed $killed processes. Available after cleanup: $(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)MB"

        # Drop caches to free more memory
        sync
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
        log "Caches dropped. Available now: $(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)MB"
    fi

    sleep "$CHECK_INTERVAL"
done
