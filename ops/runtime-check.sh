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
#   runtime/runtime.sql into it, runs the whole runtime suite with the DSN set, and
#   destroys the database afterwards.
#
#   It NEVER touches port 55433 — that is the owner's live glp-strong-db, and the role
#   that owns the scratch database owns the real one too.
#
# USAGE
#   ops/runtime-check.sh            # bring up, install, run, clean up
#   ops/runtime-check.sh --keep     # leave the scratch database for inspection
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

started_here=0
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker start "$CONTAINER" >/dev/null
  else
    echo "runtime-check: starting throwaway Postgres on 127.0.0.1:$PORT"
    docker run -d --name "$CONTAINER" \
      -e POSTGRES_USER="$USER" -e POSTGRES_PASSWORD="$PASS" -e POSTGRES_DB="$DB" \
      -e POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8" \
      -p "127.0.0.1:$PORT:5432" postgres:16-alpine >/dev/null
  fi
  started_here=1
fi

echo -n "runtime-check: waiting for the database"
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" >/dev/null 2>&1; then break; fi
  echo -n "."; sleep 1
done
echo
if ! docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" >/dev/null 2>&1; then
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
status=$?

if [ "$KEEP" = "0" ] && [ "$started_here" = "1" ]; then
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  echo "runtime-check: throwaway container removed"
else
  echo "runtime-check: --keep — $CONTAINER left on 127.0.0.1:$PORT"
fi
exit $status
