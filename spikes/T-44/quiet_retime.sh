#!/usr/bin/env bash
# T-44: the OPPORTUNISTIC QUIET RE-TIME, under the foreman's rules of 2026-10-01 (~01:25 MDT).
#
#   * Starts ONLY after the 1-minute load average has stayed below 2.0 for 5 straight minutes:
#     10 consecutive samples, 30 s apart, every one logged.
#   * Never starts after the deadline (04:40 MDT = 10:40Z). After that it is a morning item.
#   * Stops nothing. The negative control runs first, then the SAME harness, the SAME bar
#     read literally, and the pre-registered n = 25.
#   * Run it in a background shell (nohup), so a usage cap on the driving session cannot
#     kill it.
#   * While it runs, the marker out/QUIET_RETIME_RUNNING exists. Any seat must check it
#     before loading the host.
#
# The DSN is built from the container's own environment and never printed.
set -uo pipefail
ROOT="/home/corgea/Desktop/Coding Projects/autoSQL"
OUT="$ROOT/spikes/T-44/out"
LOG="$OUT/quiet-watch.log"
MARK="$OUT/QUIET_RETIME_RUNNING"
PY="${PY:?PY must name the scratch venv python}"
DEADLINE=$(date -u -d '2026-10-01T10:40:00Z' +%s)
NEED=10
streak=0
log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

log "watcher started: need $NEED consecutive 1-min loads < 2.0, 30 s apart; deadline 10:40Z"
while :; do
  if [ "$(date -u +%s)" -ge "$DEADLINE" ]; then
    log "DEADLINE reached without $NEED quiet samples in a row: re-time NOT run (a morning item)"
    exit 0
  fi
  l1=$(cut -d' ' -f1 /proc/loadavg)
  if awk -v x="$l1" 'BEGIN { exit !(x < 2.0) }'; then streak=$((streak + 1)); else streak=0; fi
  log "load1=$l1 streak=$streak/$NEED"
  [ "$streak" -ge "$NEED" ] && break
  sleep 30
done

PW=$(docker inspect autosql-corpus --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^POSTGRES_PASSWORD=//p')
export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=$PW dbname=autosql_spike"
export PYTHONDONTWRITEBYTECODE=1
touch "$MARK"
log "QUIET for 5 straight minutes: negative control first"
if ! "$PY" "$ROOT/spikes/T-44/control_t44.py" "$OUT/negative-control-quiet.json" >> "$LOG" 2>&1; then
  log "NEGATIVE CONTROL FAILED: no millisecond is taken"
  rm -f "$MARK"
  exit 1
fi
log "control passed: timing 20000,100000 x num,text, n=25"
"$PY" "$ROOT/spikes/T-44/bench_t44.py" 20000,100000 num,text "$OUT/timing-quiet.json" 25 >> "$LOG" 2>&1
log "re-time finished (exit $?)"
rm -f "$MARK"
