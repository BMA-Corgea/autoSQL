"""demo/tests/t101_mutants.py — T-101's mutants: each row's clock reading checked against D(zone).

They break the per-row check (the runtime's xpr.clock, the compiler's choice of it), D's arithmetic,
its cache and the per-question re-check, and the list's greying. Run on ``t78_mutants.py``'s runner
(each kill on the test's own assertion, bytecode off, files restored, the digest checked).  RUN ON A
SCRATCH COPY OF THE TREE, never in a worktree anyone reads.

The SQL half needs a THROWAWAY Postgres: set AUTOSQL_T98_DSN (or AUTOSQL_COMPILER_DSN and
AUTOSQL_PARITY_DSN).  Each test installs the scratch tree's own runtime there first.

    AUTOSQL_T98_DSN="host=… …" demo/.venv/bin/python demo/tests/t101_mutants.py [--dry-run] [--only T1,T2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_P = "../parity/tests/test_t101.py::"
_C = "../compiler/tests/test_compile_time_of_day.py::"
_T = "tests/test_t98.py::"
_RT = "../runtime/runtime.sql"
_Z = "../picks/zones.py"
_RECHECK = _P + "test_a_server_whose_zone_data_changed_without_a_restart_is_seen_by_the_next_question"
_NOW = '    now = conn.execute(_off_sql(_RECHECK_SQL), {"ts": list(samples), "z": zone}).fetchone()[1]\n'
_HIT = ('        if hit and hit["started"] == started and hit["python"] == (starts, offsets) '
        'and hit["seen"] == tuple(now):')

T101_MUTANTS = [
    dict(id="T1", defect="D ignored: the runtime's check never refuses a row (xpr.clock reads every instant)",
         edits=[(_RT, "  IF bounds IS NOT NULL AND width_bucket(sec, bounds) % 2 = inside THEN", "  IF false THEN")],
         selector=_P + "test_a_row_where_the_clocks_disagree_is_refused_naming_its_date", expect="('rows'"),
    dict(id="T2", defect="D's intervals one second off at their start",
         edits=[(_Z, "            lo = NEG_INF if pt is None else float(pt + 1)", "            lo = NEG_INF if pt is None else float(pt)")],
         selector=_C + "test_a_row_at_the_first_differing_second_is_refused_and_the_second_before_is_not",
         expect="1793519999"),
    dict(id="T3", defect="the cache never invalidated (keyed without the server's start time)",
         edits=[(_Z, _HIT, _HIT.replace('hit["started"] == started and ', ""))],
         selector=_P + "test_a_restarted_server_works_D_out_again", expect="inf"),
    dict(id="T4", defect="a non-empty D compiled as empty (the plain reading)",
         edits=[("../compiler/compile.py",
                 "            if not gaps:                                      # the two clocks agree: the plain reading",
                 "            if True:                                          # the two clocks agree: the plain reading")],
         selector=_C + "test_an_empty_D_is_the_plain_reading_and_any_other_is_checked", expect="float8[]"),
    dict(id="T5", defect="the list greys a zone the clocks disagree on only in history",
         edits=[("server/dashboard.py", '"why": mark[e["zone"]][0], "note"', '"why": mark[e["zone"]][0] or mark[e["zone"]][1], "note"')],
         selector=_T + "test_the_page_gets_the_list_with_each_zones_mark", expect="Times from November 2026"),
    dict(id="T6", defect="the per-row call put back: the summary's check goes through a call of ours for every row",
         edits=[("../picks/builder.py",
                 "    return lambda v: (f\"(CASE WHEN mod(width_bucket(",
                 "    return lambda v: (f\"(CASE WHEN xpr.time_of_day(to_jsonb({v}), 'UTC') IS NOT NULL AND mod(width_bucket(")],
         selector=_P + "test_a_row_outside_D_costs_no_call_of_ours", expect="time_of_day"),
    dict(id="R1", defect="the per-question re-check skipped (the cached readings stand in for the server's)",
         edits=[(_Z, _NOW, '    now = (_GAP_CACHE.get((conn.info.host, conn.info.port, conn.info.dbname, zone)) or {}).get("seen") \\\n'
                           '        or conn.execute(_off_sql(_RECHECK_SQL), {"ts": list(samples), "z": zone}).fetchone()[1]\n')],
         selector=_RECHECK, expect="('rows'"),
    dict(id="R2", defect="the re-check reads only Python's change instants (no monthly noons)",
         edits=[(_Z, "    out.update(range(-5364619200, 0, 4 * 604800))\n    out.update(range(43200, 4133937600 + 1, 30 * 86400))\n", "")],
         selector=_RECHECK, expect="('rows'"),
    dict(id="R3", defect="a difference the re-check finds doesn't work D out again",
         edits=[(_Z, _HIT, _HIT.replace(' and hit["seen"] == tuple(now)', ""))],
         selector=_RECHECK, expect="('rows'"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    dsn = os.environ.get("AUTOSQL_T98_DSN")
    for var in ("AUTOSQL_COMPILER_DSN", "AUTOSQL_PARITY_DSN"):
        if dsn and not os.environ.get(var):
            os.environ[var] = dsn
        if not os.environ.get(var) and "--dry-run" not in (argv or sys.argv[1:]):
            print(f"t101 mutants: refusing to run — set AUTOSQL_T98_DSN (or {var}) to a throwaway Postgres;"
                  " without it the SQL half would skip and every SQL mutant would 'survive' for nothing")
            return 2
    runner.T78_MUTANTS[:] = T101_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
