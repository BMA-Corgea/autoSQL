#!/usr/bin/env bash
# T-6 sp-investigate orchestrator.
#
# Same instruments, same batteries, same seeds as T-3. Two things differ and both
# are declared: the runtime is spikes/T-6/runtime.sql (the named coercion refusal),
# and every battery runs TWICE -- once under the ORIGINAL strict comparison rule and
# once under FRAMING section 4's recursive one -- so both numbers are published side
# by side and nothing is claimed under the new rule alone.
#
# Throwaway container on 55434. Never 55433; differ.py fails closed on it anyway.
set -uo pipefail

ROOT="/home/corgea/Desktop/Coding Projects/autoSQL"
FUZZ="$ROOT/spikes/T-1/analysis/fuzz"
OUT="$ROOT/spikes/T-6/out"
PY="/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python"

export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=throwaway dbname=autosql_spike"
case "$AUTOSQL_SPIKE_DSN" in *port=55433*) echo "REFUSING: live database"; exit 2;; esac

mkdir -p "$OUT"
cd "$FUZZ" || exit 1

echo "=== T-6 matrix — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo

# ── controls first, per setting (FRAMING section 6: a battery whose controls did not run is void)
echo "--- positive control: did the float-digit setting actually change? ---"
for efd in 1 0 -3; do
  AUTOSQL_EFD=$efd "$PY" "$ROOT/spikes/T-3/efd_control.py" 2>&1 | tee -a "$OUT/efd_control.txt"
done
echo

# ── the three subset batteries, three settings, two comparison rules
for efd in 1 0 -3; do
  for prof in sub_ordinary sub_unicode sub_extreme; do
    for mode in strict recursive; do
      f="$OUT/H_${prof}_efd${efd}_${mode}.txt"
      AUTOSQL_EFD=$efd AUTOSQL_MATCH_MODE=$mode \
        timeout 900 "$PY" H_ast_fuzz.py "$prof" 4000 2026 > "$f" 2>&1
      printf '%-14s efd=%-3s %-9s  %s\n' "$prof" "$efd" "$mode" \
        "$(grep -E '^\s+(AGREE|DIVERGE|SQL_REFUSAL|SQL_RAISE|NULLNESS)\s' "$f" \
           | awk '{printf "%s=%s ", $1, $2}')"
    done
  done
done
echo

# ── the 130-case contract fixture, per setting (strict rule; it is GIMS's own suite)
echo "--- contract fixture (proto/conformance.py), per setting ---"
for efd in 1 0 -3; do
  AUTOSQL_EFD=$efd AUTOSQL_MATCH_MODE=strict \
    "$PY" "$ROOT/spikes/T-3/fixture_driver.py" t6 2>&1 | tee -a "$OUT/fixture_summary.txt" | head -2
done
echo

# ── the domain gate: did the batteries reach the places the failures live?
echo "--- domain gate ---"
AUTOSQL_EFD=1 AUTOSQL_MATCH_MODE=strict \
  "$PY" "$ROOT/spikes/T-3/t3_domain_gate.py" > "$OUT/domain_gate.txt" 2>&1
tail -4 "$OUT/domain_gate.txt"

echo
echo "=== done — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
