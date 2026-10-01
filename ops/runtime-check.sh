#!/usr/bin/env bash
# ops/runtime-check.sh — run the runtime suite's DATABASE half.
#
# WHY THIS EXISTS
#   runtime/runtime.sql's digit tables are DERIVED from the running interpreter's Unicode
#   data (runtime/generate.py's header says why: Python's float() accepts any Unicode
#   decimal digit by numeric value, so freezing the table splits the two engines silently
#   on a Python upgrade).
#
#   `test_the_generated_runtime_is_not_stale` DETECTS that drift and needs no database.
#   But the 39 cases that prove the regenerated mapping actually makes SQL agree with
#   Python — Arabic-Indic ١٢٣, Thai ๑๒๓, Devanagari १२३, fullwidth １２３, mathematical
#   𝟎𝟏 — sit behind @needs_db and SKIP unless AUTOSQL_RUNTIME_DSN is set. Nothing in this
#   repo set it. So `pytest runtime/tests/` printed "8 passed, 50 skipped" and read as
#   green, and a regeneration could be shipped without one Unicode digit ever being
#   compared between the two engines.
#
#   This is that DSN, and the throwaway Postgres behind it.
#
# WHAT IT DOES
#   Brings up a throwaway container, creates a scratch database, installs the CURRENT
#   runtime/runtime.sql into it, and runs the whole runtime suite with the DSN set.
#
#   Its teardown removes exactly what this run created, and nothing it did not (T-25):
#     - a container this run CREATED is removed WITH its volume (`docker rm -f -v`) on every
#       exit: after the suite, and on the early exits too (the database never became ready,
#       runtime.sql did not install). Without -v, every run left ~48 MB dangling.
#     - a container this run did not create is left as found: one already running is used
#       and left running; a stopped one is started, used, and stopped again.
#     - --keep leaves it up. Remove a kept container, and its volume, with
#           docker rm -f -v autosql-runtime-check
#       A plain `docker rm -f` leaves its data volume behind, dangling.
#
#   It NEVER touches port 55433 — that is the owner's live glp-strong-db, and the role
#   that owns the scratch database owns the real one too.
#
# USAGE
#   ops/runtime-check.sh            # bring up, install, run, clean up
#   ops/runtime-check.sh --keep     # leave the scratch database up for inspection, then later:
#   docker rm -f -v autosql-runtime-check
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

CONTAINER="autosql-runtime-check"
PORT=55435                       # NOT 55433 (live) and NOT 55434 (T-4's corpus)
DB="runtime_check"
USER="runtime_check"
PASS="runtime_check_throwaway"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

if [ "$PORT" = "55433" ]; then
  echo "runtime-check: 55433 is the owner's LIVE database. Refusing." >&2; exit 2
fi

# What this run did to the container decides what its teardown may do to it:
#   created   -> remove it and its volume      restarted -> stop it again      found -> leave it
mode=""
fail() { echo "runtime-check: FAILED: $*" >&2; [ "$rc" -eq 0 ] && rc=1; }
teardown() {
  rc=$?
  if [ "$KEEP" = "1" ]; then
    echo "runtime-check: --keep was passed: $CONTAINER left up on 127.0.0.1:$PORT"
    echo "runtime-check: remove it, and its volume, with: docker rm -f -v $CONTAINER"
  elif [ "$mode" = "created" ]; then
    # -v is not optional (T-25). postgres:16-alpine declares VOLUME /var/lib/postgresql/data and
    # nothing is mounted there, so this run got an ANONYMOUS volume. A plain `docker rm -f`
    # removes the container and leaves that volume dangling, about 48 MB a run. Measured: one run
    # took the machine's dangling count from 74 to 75 before this flag, and left it at 74 after.
    # The volume is named from the container first, so "removed" below is checked, not assumed.
    vol="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$CONTAINER" 2>/dev/null)"
    if ! docker rm -f -v "$CONTAINER" >/dev/null 2>&1; then
      fail "docker rm -f -v $CONTAINER did not succeed; the container and its volume may still be there"
    elif [ -z "$vol" ]; then
      echo "runtime-check: throwaway container removed (no data-dir volume was named on it to check)"
    elif docker volume inspect "$vol" >/dev/null 2>&1; then
      fail "$CONTAINER was removed, but its volume $vol is still there"
    else
      echo "runtime-check: throwaway container and its volume (${vol:0:12}) removed"
    fi
  elif [ "$mode" = "restarted" ]; then
    if docker stop "$CONTAINER" >/dev/null 2>&1; then
      echo "runtime-check: $CONTAINER was stopped when this run began and this run did not create it: stopped again, as found"
    else
      fail "could not stop $CONTAINER again; this run started it"
    fi
  else
    echo "runtime-check: $CONTAINER was already running, so this run did not start it and leaves it as found"
    echo "runtime-check: remove it, and its volume, with: docker rm -f -v $CONTAINER"
  fi
  exit "$rc"
}

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  mode="found"
elif docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker start "$CONTAINER" >/dev/null || { echo "runtime-check: could not start the stopped $CONTAINER" >&2; exit 1; }
  mode="restarted"
else
  echo "runtime-check: starting throwaway Postgres on 127.0.0.1:$PORT"
  # create, then start: if the start fails (the port is taken, say), the container and its volume
  # already exist, and the teardown must still remove them.
  docker create --name "$CONTAINER" \
    -e POSTGRES_USER="$USER" -e POSTGRES_PASSWORD="$PASS" -e POSTGRES_DB="$DB" \
    -e POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8" \
    -p "127.0.0.1:$PORT:5432" postgres:16-alpine >/dev/null \
    || { echo "runtime-check: could not create $CONTAINER; nothing was created" >&2; exit 1; }
  mode="created"
fi
# From here on EVERY exit goes through the teardown, the early ones below included.
trap teardown EXIT
if [ "$mode" = "created" ] && ! docker start "$CONTAINER" >/dev/null; then
  echo "runtime-check: $CONTAINER was created but would not start" >&2; exit 1
fi

# Ready means ready over TCP. On first start the image's entrypoint runs a TEMPORARY server that
# listens on the Unix socket only, then shuts it down and starts the real one. Observed
# 2026-10-01: a socket poll passed against the temporary server, the confirming check below
# landed in its shutdown, and the run exited "never became ready" before the suite ran. Only the
# real server listens on TCP.
echo -n "runtime-check: waiting for the database"
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U "$USER" -d "$DB" >/dev/null 2>&1; then break; fi
  echo -n "."; sleep 1
done
echo
if ! docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U "$USER" -d "$DB" >/dev/null 2>&1; then
  echo "runtime-check: the database never became ready" >&2; exit 1
fi

# A FRESH schema every run: an agreement test against a stale runtime is worse than no
# test, because it reports agreement with something that is no longer shipped.
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -q -c "DROP SCHEMA IF EXISTS xpr CASCADE" >/dev/null
docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" -q < runtime/runtime.sql >/dev/null || {
  echo "runtime-check: runtime/runtime.sql did not install" >&2; exit 1; }
echo "runtime-check: installed $(docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -tAc \
  "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='xpr'") xpr functions from runtime/runtime.sql"

PY="demo/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
AUTOSQL_RUNTIME_DSN="host=127.0.0.1 port=$PORT user=$USER password=$PASS dbname=$DB" \
  PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest runtime/tests/ "${@:2}" -q --no-header
exit $?   # the teardown (trap above) runs now, and keeps this status unless it fails itself
