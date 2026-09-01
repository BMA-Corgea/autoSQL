#!/usr/bin/env bash
# start.sh — the front door.
#
# One command: bring the demo up and put it on screen. Everything it needs it
# builds itself (its own Postgres in Docker, its own venv, 10,410 invented rows).
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

is_up() { curl -fsS -m 3 -o /dev/null "http://127.0.0.1:${APP_PORT}/api/operations" 2>/dev/null; }

open_page() {
  # Prefer the live screen; fall back to the offline launcher, which is a real
  # page in its own right and says what to do next.
  local target="$1"
  for opener in xdg-open open; do
    if command -v "$opener" >/dev/null 2>&1; then
      "$opener" "$target" >/dev/null 2>&1 &
      return 0
    fi
  done
  return 1
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
      say "${B}running${OFF} — http://127.0.0.1:${APP_PORT}/"
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

if is_up; then
  say ""
  say "${B}Already running.${OFF} http://127.0.0.1:${APP_PORT}/"
  open_page "http://127.0.0.1:${APP_PORT}/" || say "${DIM}(open that URL yourself — no browser opener found)${OFF}"
  exit 0
fi

for port in "$APP_PORT" "$DB_PORT"; do
  if (command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":${port} ") ||
     (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1); then
    die "Port ${port} is already taken by something else, and the demo refuses to share it.
    Free it, or run './start.sh stop' if a previous run is still up."
  fi
done

# ── bring it up ───────────────────────────────────────────────────────────
say ""
say "  ${B}autoSQL${OFF} ${DIM}— the same question, answered two ways${OFF}"
say ""
step "Starting. First run pulls a Postgres image and builds a virtualenv, so give it a minute."
say ""

if ! ./run-demo up 2>&1 | sed 's/^/    /'; then
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

if [ "${ok:-0}" != "1" ]; then
  warn "It started but is not answering on port ${APP_PORT} yet."
  say  "    Try ./start.sh status in a moment, or ./run-demo up to see why."
  exit 1
fi

say ""
say "  ${B}Ready.${OFF}  ${AQUA}http://127.0.0.1:${APP_PORT}/${OFF}"
say ""
say "  ${DIM}Seven states across the top. Start at 'Reconciled' — it is the value"
say "  that used to come back wrong, now reading the same on both engines.${OFF}"
say ""
say "  ${DIM}Stop it with ./start.sh stop. Every row in it is invented.${OFF}"
say ""

open_page "http://127.0.0.1:${APP_PORT}/" ||
  say "  ${DIM}(no browser opener found — open the URL above, or ${LAUNCHER})${OFF}"
