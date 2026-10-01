#!/usr/bin/env bash
# T-44: one compiler x one database x the three subset batteries, both comparison rules, efd 1.
# Usage: run_batteries.sh <compiler> <database> <tag-prefix> [off|on]
# AUTOSQL_SPIKE_DSN is built per database by the caller's dsn() helper (the password is
# never written into this repo).  Never 55433: battery.py refuses it.
set -uo pipefail
comp="$1"; db="$2"; prefix="$3"; par="${4:-off}"
ROOT="/home/corgea/Desktop/Coding Projects/autoSQL"
: "${PY:?PY must name the scratch venv python}"
: "${DSN_FOR:?DSN_FOR must be a command that prints a DSN for a database name}"
dsn="$($DSN_FOR "$db")"
pids=()
for prof in sub_ordinary sub_unicode sub_extreme; do
  for mode in recursive strict; do
    AUTOSQL_SPIKE_DSN="$dsn" AUTOSQL_EFD=1 AUTOSQL_MATCH_MODE=$mode \
      timeout 900 "$PY" "$ROOT/spikes/T-44/battery.py" --compiler "$comp" --profile "$prof" \
      --parallel "$par" --tag "${prefix}_${prof}_efd1_${mode}" &
    pids+=($!)
  done
done
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
exit $rc
