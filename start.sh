#!/usr/bin/env bash
# start.sh — the front door.
#
# One command: bring the demo up and put it on screen. Everything it needs it
# builds itself (its own Postgres in Docker, its own venv, 10,470 invented rows).
#
#   ./start.sh          bring it up and open the screen
#   ./start.sh stop     tear it down (container and volume removed)
#   ./start.sh status   is it running?
#
# This is a thin, friendly wrapper over ./run-demo, which does the real work and
# stays the thing tests and CI call. If something goes wrong, run `./run-demo up`
# directly -- it prints everything.
#
# It never touches anything but its own container. In particular it never goes
# near port 55433, which is a live database.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

APP_PORT=8787
DB_PORT=55440
DB_CONTAINER="autosql-demo-db"
APP_PIDFILE="demo/.venv/autosql-app.pid"
LAUNCHER="demo/launcher.html"

# ── colours, only when a human is looking ─────────────────────────────────
if [ -t 1 ]; then
  DIM=$'\033[2m'; B=$'\033[1m'; AQUA=$'\033[38;5;80m'; WARN=$'\033[38;5;215m'
  RED=$'\033[38;5;210m'; OFF=$'\033[0m'
else
  DIM=""; B=""; AQUA=""; WARN=""; RED=""; OFF=""
fi
say()  { printf '%s\n' "$*"; }
step() { printf '%s→%s %s\n' "$AQUA" "$OFF" "$*"; }
warn() { printf '%s!%s %s\n' "$WARN" "$OFF" "$*"; }
die()  { printf '%s✗%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

#: The page it opens: the dashboard (T-71). The engineer's two-pane screen
#: is still at / and is linked from the dashboard's Admin view.
PAGE="http://127.0.0.1:${APP_PORT}/dashboard"

is_up() { curl -fsS -m "${1:-3}" -o /dev/null "http://127.0.0.1:${APP_PORT}/api/operations" 2>/dev/null; }

# Before anything is cleared, the app is given more than one chance and more
# than three seconds: an app that is up but slow is running, not left behind.
is_up_patiently() { is_up 10 || { sleep 2; is_up 10; }; }

open_page() {
  # Prefer the live screen; fall back to the offline launcher, which is a real
  # page in its own right and says what to do next.
  #
  # The opener is backgrounded so an opener that blocks until the browser exits
  # cannot hang this script -- but we then wait briefly and check whether it
  # FAILED, because "an opener exists" and "a page opened" are different claims.
  # They come apart in practice: xdg-open is installed but the browser will not
  # start (no browser running and a stale profile lock is the common one). This
  # used to return 0 unconditionally, so that case printed nothing at all and
  # looked, from the terminal, exactly like success.
  local target="$1" opener pid i
  for opener in xdg-open open; do
    command -v "$opener" >/dev/null 2>&1 || continue
    "$opener" "$target" >/dev/null 2>&1 &
    pid=$!
    for i in $(seq 1 10); do                 # up to ~2s for a fast failure
      if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" && return 0              # exited cleanly: the page opened
        return 1                             # exited non-zero: it did not
      fi
      sleep 0.2
    done
    return 0                                 # still running: it did not fail fast
  done
  return 1                                   # no opener on this machine at all
}

# ── subcommands ───────────────────────────────────────────────────────────
case "${1:-up}" in
  stop|down)
    step "Stopping the demo…"
    ./run-demo down 2>&1 | tail -3
    say "${DIM}Its container and volume are removed. Nothing of it is left running.${OFF}"
    exit 0
    ;;
  status)
    if is_up; then
      say "${B}running${OFF} — ${PAGE}"
    else
      say "${B}not running${OFF} — start it with ./start.sh"
    fi
    exit 0
    ;;
  up|"") : ;;
  *)
    die "unknown command '${1}'. Use: ./start.sh [up|stop|status]"
    ;;
esac

# ── preflight, with remedies rather than stack traces ─────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not installed, and the demo brings up its own Postgres.
    Install Docker, then run this again."

docker info >/dev/null 2>&1 || die "Docker is installed but not running.
    Start Docker Desktop (or 'sudo systemctl start docker'), then run this again."

command -v python3 >/dev/null 2>&1 || die "python3 is not on PATH. The demo needs it for its own virtualenv."

already_running() {
  say ""
  say "${B}Already running.${OFF} ${PAGE}"
  open_page "${PAGE}" ||
    say "${DIM}(couldn't open a browser — open the URL above yourself, or ${LAUNCHER})${OFF}"
  exit 0
}

if is_up; then
  already_running
fi

# ── one look and one act, under the demo's host-wide lock ─────────────────
# The lock is run-demo's own (T-62): the same file and flock. Holding it, no
# other run-demo (a test run in another worktree, another ./start.sh) can be
# between its own look and its own act while this script reads what is there
# and then clears or starts it. The run-demo verbs called below are told so
# (RUN_DEMO_LOCK_HELD) and don't wait on their parent; the lock's fd is closed
# in them, so the app they start never holds it.
LOCKFILE="/tmp/run-demo.${DB_CONTAINER}.lock"
command -v flock >/dev/null 2>&1 || die "flock (util-linux) is not installed, and the demo needs it to keep two runs apart."
[ -e "$LOCKFILE" ] || ( umask 000; : >>"$LOCKFILE" ) 2>/dev/null || true
exec {LOCK_FD}<"$LOCKFILE" || die "Could not open the demo's lock file, $LOCKFILE."
if ! flock -n "$LOCK_FD"; then
  step "Another run is using the demo; waiting for it to finish (up to 30 minutes)…"
  flock -w 1800 "$LOCK_FD" ||
    die "Another run is still using the demo after 30 minutes. Nothing was changed; try again later."
fi
export RUN_DEMO_LOCK_HELD="$DB_CONTAINER"
unlock() { exec {LOCK_FD}<&-; }

# Looked at again now that nothing else can change it.
if is_up_patiently; then
  unlock
  already_running
fi

# What an earlier run left behind is this demo's own, not "something else":
# its database with no app answering in front of it (a start that failed
# partway; stopped, after a reboot), or this checkout's app pidfile. Refusing
# here used to leave the front door stuck until someone thought to run
# './start.sh stop'. It is cleared and started fresh: every row is invented
# and reseeded on the way up. A clear that fails stops here, in its own words.
if [ -n "$(docker ps -aq --filter "name=^/${DB_CONTAINER}$")" ] || [ -f "$APP_PIDFILE" ]; then
  step "Clearing what an earlier run left behind…"
  ./run-demo down {LOCK_FD}<&- 2>&1 | sed 's/^/    /'
  if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    die "What an earlier run left behind could not be cleared; the lines above say why. Nothing was started."
  fi
fi

for port in "$APP_PORT" "$DB_PORT"; do
  if (command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":${port} ") ||
     (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1); then
    die "Port ${port} is already taken by something else, and the demo refuses to share it.
    It is not this demo (anything of the demo's own was cleared above). Free it, then run this again."
  fi
done

# ── bring it up ───────────────────────────────────────────────────────────
say ""
say "  ${B}autoSQL${OFF} ${DIM}— the same question, answered two ways${OFF}"
say ""
step "Starting. First run pulls a Postgres image and builds a virtualenv, so give it a minute."
say ""

if ! ./run-demo up {LOCK_FD}<&- 2>&1 | sed 's/^/    /'; then
  say ""
  die "The demo did not come up. The output above is the whole story;
    './run-demo up' on its own prints it again with nothing trimmed."
fi

# ── confirm it actually answers, rather than trusting the exit code ───────
step "Waiting for it to answer…"
for _ in $(seq 1 30); do
  if is_up; then ok=1; break; fi
  sleep 1
done

unlock

if [ "${ok:-0}" != "1" ]; then
  warn "It started but is not answering on port ${APP_PORT} yet."
  say  "    Try ./start.sh status in a moment, or ./run-demo up to see why."
  exit 1
fi

say ""
say "  ${B}Ready.${OFF}  ${AQUA}${PAGE}${OFF}"
say ""
say "  ${DIM}Pick a data set, the columns and the rows you want; the answer follows."
say "  The engineer's two-pane screen is still at http://127.0.0.1:${APP_PORT}/${OFF}"
say ""
say "  ${DIM}Stop it with ./start.sh stop. Every row in it is invented.${OFF}"
say ""

open_page "${PAGE}" ||
  say "  ${DIM}(couldn't open a browser — open the URL above yourself, or ${LAUNCHER})${OFF}"
