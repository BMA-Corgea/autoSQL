#!/usr/bin/env bash
# T-1 spike, semantic-faithfulness seat -- re-run every reproduction.
#
# Each battery is self-contained and prints its own evidence; the .txt beside
# each .py is the output captured on 2026-08-19 against
#   PostgreSQL 16.14 (docker glp-strong-db), database autosql_spike, schema xpr
#   GIMS-Project@995cc59, gims-ledger@7b7a049
#   CPython 3.12.3 (GIMS-Project/.venv)
#
# Nothing here writes to either GIMS tree, to spikes/T-1/proto/, or to any
# database other than autosql_spike.  Batteries F3 and O create and DROP their
# own scratch tables (fuzz_guc, fuzz_rows).
set -u
PY="/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python"
cd "$(dirname "$0")" || exit 1

run() { echo; echo "##### $1 #####"; "$PY" "$1" ${2:-} ${3:-} ${4:-}; }

run A_f8_guard.py          # the 297-digit guard literal + its blast radius
run B_overflow.py          # float8 overflow AND underflow -> 22003, query aborted
run C_numgate.py           # xpr.num's ASCII gate vs Python's Unicode-aware _to_num
run D_rawjson.py           # jsonb `numeric` vs Python `float` on non-Python-written rows
run E_dates.py             # date parse/format, incl. expr's own OverflowError
run E2_dates_ws.py         # date trimming + Unicode digits, systematically
run F_ecma_num.py          # ecma_num random fuzz + the GUC table
run F1b_ecma_rate.py       # ecma_num mismatch RATE over 200k doubles
run F3_immutable_index.py  # IMMUTABLE + a GUC -> index/seq-scan split brain
run G_fmod_round.py        # fmod and round, 40k pairs each (both clean)
run G2b_round_raises.py    # round, per-item, so the raise rate is honest
run H_ast_fuzz.py ordinary 4000 2026
run H_ast_fuzz.py extreme  4000 99
run H_ast_fuzz.py unicode  4000 555
run I_case_collate.py      # exhaustive case-mapping sweep + collation check
run J_conventions.py       # 95 convention corners
run K_sum_neumaier.py      # builtin sum() is compensated; PG's sum() is not
run L_misc.py              # int4 indices, NUL bytes, SQL size, volatility table
run M_encoding_guc.py      # to_jsonb(float8) itself depends on the GUC
run N_shortcircuit.py      # evaluation order (no divergence found on PG 16.14)
run O_row_loss.py          # the same divergences as a WHERE predicate
