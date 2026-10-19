"""demo/tests/t98_mutants.py — T-98's mutants: time of day on a named clock, and its zone guard.

Most break BOTH engines the same way — the vendored evaluator AND the runtime — so the two still
agree and only answers worked out by hand can catch them (``parity/time-of-day-vectors.json``, the
clock facts in ``test_t98.py`` and ``compiler/tests/test_compile_time_of_day.py``).  Run on
``t78_mutants.py``'s runner (each kill on the test's own assertion, bytecode off, files restored,
the digest checked).  RUN ON A SCRATCH COPY OF THE TREE, never in a worktree anyone reads.

The SQL half needs a THROWAWAY Postgres: set AUTOSQL_T98_DSN (or the three AUTOSQL_RUNTIME_DSN /
AUTOSQL_COMPILER_DSN / AUTOSQL_PARITY_DSN).  Each test installs the scratch tree's own
runtime/runtime.sql there first, so a mutant of the runtime is what the SQL engine runs.

    AUTOSQL_T98_DSN="host=127.0.0.1 port=… …" demo/.venv/bin/python demo/tests/t98_mutants.py [--dry-run] [--only B1,B2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t98.py::"
_C = "../compiler/tests/test_compile_time_of_day.py::"
VECTORS = "../parity/tests/test_time_of_day_vectors.py::test_every_case_equals_its_hand_answer_in_both_engines"
BATTERY = "../runtime/tests/test_runtime_time_of_day.py::test_every_form_in_every_kind_of_zone"

_PY_CLOCK = "        clock = datetime.fromtimestamp(math.floor(parsed[0] / 1000.0), ZoneInfo(zone))"
_PY_RETURN = "    return float(clock.hour * 3600 + clock.minute * 60 + clock.second)"
_SQL_CLOCK = "  clock := to_timestamp(sec) AT TIME ZONE zone;"
_SQL_BARE = ")) <= 10 THEN RETURN NULL; END IF;"   # T-103: time_of_day's bare-date rule, read without a second parse
_SQL_SEC = "  sec := floor(ms / 1000.0::float8);"
_RT = "../runtime/runtime.sql"
_LOUD = ("    reporter.write_sep(\"=\", \"RUNTIME CHECK: THE DATABASE IS NOT RUNNING THIS TREE'S RUNTIME\", "
         "yellow=True, bold=True)\n")
_EV = "vendor/expr.py"

OUTCOME = "../parity/tests/test_t98_outcome.py::test_the_page_keeps_what_hand_written_sql_keeps_in_both_engines"
_V = "../picks/view.py"
_D = "server/dashboard.py"

T98_MUTANTS = [
    dict(id="B1", defect="BOTH engines read every zone's clock as UTC (they agree)",
         edits=[(_EV, _PY_CLOCK, _PY_CLOCK.replace("ZoneInfo(zone)", 'ZoneInfo("UTC")')),
                (_RT, _SQL_CLOCK, "  clock := to_timestamp(sec) AT TIME ZONE 'UTC';")],
         selector=VECTORS, expect="Denver, from 5:00 PM"),
    dict(id="B2", defect="BOTH engines turn the offset the wrong way (UTC-6 read as UTC+6)",
         edits=[(_EV, _PY_RETURN,
                 "    _u = datetime.fromtimestamp(math.floor(parsed[0] / 1000.0), timezone.utc).replace(tzinfo=None)\n"
                 "    clock = _u - (clock.replace(tzinfo=None) - _u)\n" + _PY_RETURN),
                (_RT, _SQL_CLOCK,
                 "  clock := (to_timestamp(sec) AT TIME ZONE 'UTC') - ((to_timestamp(sec) AT TIME ZONE zone) "
                 "- (to_timestamp(sec) AT TIME ZONE 'UTC'));")],
         selector=VECTORS, expect="Denver, from 5:00 PM"),
    dict(id="B3", defect="BOTH engines give a bare date the time of day of its midnight",
         edits=[(_EV, "    if parsed is None or parsed[1]:\n        return None\n    try:\n        clock",
                 "    if parsed is None:\n        return None\n    try:\n        clock"),
                (_RT, _SQL_BARE, ")) < 0 THEN RETURN NULL; END IF;")],
         selector=VECTORS, expect="a bare date, text that is no time"),
    dict(id="B4", defect="BOTH engines round a fraction of a second instead of dropping it",
         edits=[(_EV, _PY_CLOCK, _PY_CLOCK.replace("math.floor(parsed[0] / 1000.0)", "round(parsed[0] / 1000.0)")),
                (_RT, _SQL_SEC, "  sec := round(ms / 1000.0::float8);")],
         selector=VECTORS, expect="Denver, until 5:00 PM"),
    # B5, B6, B7 (the per-statement guard's emission and samples) and C8 (the up-front refusal) went
    # with what they broke: T-101 replaced both with each row's check against D. Its mutants
    # (t101_mutants.py) break the check, D's arithmetic and the per-question re-check.
    dict(id="B8", defect="Python's clock table puts each change a second early",
         edits=[("../compiler/compile.py", "            starts.append(hi)\n", "            starts.append(lo)\n")],
         selector=_C + "test_denvers_clock_in_2026", expect="KeyError: 1772960400"),
    dict(id="B9", defect="the gate admits a computed zone",
         edits=[("../picks/gate.py",
                 "    if not (isinstance(zone, tuple) and len(zone) == 2 and zone[0] == \"str\"\n"
                 "            and isinstance(zone[1], str)):",
                 "    if not isinstance(zone, tuple):"),
                ("../picks/gate.py", "    if zone[1] not in zones:", "    if zone[0] == \"str\" and zone[1] not in zones:")],
         selector=_T + "test_anything_else_is_refused_by_name", expect="DID NOT RAISE"),
    dict(id="B10", defect="the gate admits a zone the evaluator does not list",
         edits=[("../picks/gate.py", "    if zone[1] not in zones:", "    if False:")],
         selector=_T + "test_anything_else_is_refused_by_name", expect="DID NOT RAISE"),
    dict(id="B11", defect="the probes compile a time_of_day operand (without the zone list)",
         edits=[("../picks/probes.py",
                 '    return isinstance(node, tuple) and len(node) == 3 and node[0] == "call" and node[1] == "time_of_day"',
                 "    return False")],
         selector=_T + "test_no_probe_compiles_a_time_of_day_operand", expect="AssertionError: ('call', 'time_of_day'"),
    dict(id="B12", defect="a day's ends are computed in UTC, whatever the zone",
         edits=[("../picks/zones.py", "        return _dt.datetime(d.year, d.month, d.day, tzinfo=z)",
                 "        return _dt.datetime(d.year, d.month, d.day, tzinfo=_UTC)")],
         selector=_T + "test_a_day_is_its_first_instant_to_the_next_days",
         expect="At index 0 diff: '2026-08-20T00:00:00Z' != '2026-08-20T06:00:00Z'"),
    dict(id="B13", defect="on a day the clocks go back, a picked 1:30 AM is the SECOND one",
         edits=[("../picks/zones.py", "    first = wall.replace(tzinfo=z, fold=0)", "    first = wall.replace(tzinfo=z, fold=1)")],
         selector=_T + "test_a_picked_wall_time_is_one_instant", expect="'2026-11-01T08:30:00Z' == '2026-11-01T07:30:00Z'"),
    dict(id="B14", defect="a wall time the clocks skip is taken",
         edits=[("../picks/zones.py", "    if back != wall:", "    if False:")],
         selector=_T + "test_a_wall_time_the_clocks_skip_is_refused_in_words", expect="DID NOT RAISE"),
    dict(id="B15", defect="a field's kind is decided from its first 2,001 values again",
         # T-114: the counts are the rule's (picks.times.kind_counts); the mutant counts the first 2,001 only
         edits=[("../picks/view.py", "        kind = _kind(scalar_types, forms)",
                 "        kind = _kind(scalar_types, times.kind_counts(strings))")],
         selector=_T + "test_a_wide_time_field_whose_odd_values_sort_late_is_decided_over_every_value",
         expect="AssertionError: time"),
    dict(id="B16", defect="the statement alone answers for an instant before year 1",
         edits=[(_RT, "  IF sec < -62135596800::float8 OR sec > 253402300799::float8 THEN RETURN NULL; END IF;\n", "")],
         selector=BATTERY, expect="GIMS None, SQL"),
    dict(id="B17", defect="the second engine alone reads every zone as UTC",
         edits=[(_EV, _PY_CLOCK, _PY_CLOCK.replace("ZoneInfo(zone)", 'ZoneInfo("UTC")'))],
         selector=BATTERY, expect="disagreements"),
    dict(id="B18", defect="BOTH engines cut a fraction toward zero (a-chk's MT1): before 1970 that rounds UP",
         edits=[(_EV, _PY_CLOCK, _PY_CLOCK.replace("math.floor(parsed[0] / 1000.0)", "int(parsed[0] / 1000.0)")),
                (_RT, _SQL_SEC, "  sec := trunc(ms / 1000.0::float8);")],
         selector=VECTORS, expect="UTC, exactly 11:59:59 PM"),
    dict(id="B19", defect="BOTH engines drop the seconds (a-chk's MT2)",
         edits=[(_EV, _PY_RETURN, "    return float(clock.hour * 3600 + clock.minute * 60)"),
                (_RT, "          + floor(extract(second from clock)))::float8;", ")::float8;")],
         selector=VECTORS, expect="Denver, exactly 5:00:45 PM"),
    dict(id="D1", defect="the probes compile without the zone list (a-chk's MEDIUM on b1: a 500)",
         edits=[("../picks/probes.py", "    compile_kw = dict(compile_kw, time_zones=env.time_zones(), zone_gaps=env.zone_gaps())\n", "")],
         selector=_T + "test_a_probe_reads_the_clock_checked_as_the_statement_does", expect="Uncompilable"),
    dict(id="D2", defect="the suite's runtime check says nothing when the runtimes differ",
         edits=[("tests/conftest.py", _LOUD, "")],
         selector=_T + "test_a_seat_whose_runtime_differs_is_told_loudly_which_and_how_to_fix_it",
         expect="RUNTIME CHECK: THE DATABASE IS NOT RUNNING"),
    dict(id="A1", defect="a browser that names its zone the old way (Asia/Calcutta) is not aliased to its place",
         edits=[(_D, "        if z not in listed and z not in aliases and target in listed:\n            aliases[z] = target\n",
                 "        pass\n")],
         selector=_T + "test_a_browser_that_names_its_zone_the_old_way_reaches_its_place", expect="('Asia/Calcutta', None)"),
    # ── b2: the question's clock, in the view both engines share ─────────
    dict(id="C1", defect="BOTH engines: 'is on' takes the UTC day whatever the question's clock",
         edits=[(_V, "            first, nxt = zones.day_span(d, zone)", '            first, nxt = zones.day_span(d, "UTC")')],
         selector=_T + "test_aug_20_in_denver_is_denvers_day_and_the_rows_read_on_its_clock", expect="1200 == 900"),
    dict(id="C2", defect="BOTH engines: 'between' never wraps midnight",
         edits=[(_V, '    joined = "and" if a < b else "or"', '    joined = "and"')],
         selector=OUTCOME, expect="statement 0, second engine 0"),
    dict(id="C3", defect="BOTH engines: 'until' takes the time itself",
         edits=[(_V, '        return f"{t} < {a}", f"{label} until {zones.clock_words(a)}"',
                 '        return f"{t} <= {a}", f"{label} until {zones.clock_words(a)}"')],
         selector=OUTCOME, expect="hand-written SQL 5950"),
    dict(id="C4", defect="BOTH engines: 'from' leaves the time itself out",
         edits=[(_V, '        return f"{t} >= {a}", f"{label} from {zones.clock_words(a)}"',
                 '        return f"{t} > {a}", f"{label} from {zones.clock_words(a)}"')],
         selector=OUTCOME, expect="hand-written SQL 50"),
    dict(id="C5", defect="BOTH engines: a picked time is read as UTC, whatever the question's clock",
         edits=[(_V, '    if zone is not None and not value.endswith("Z"):', "    if False:")],
         selector=_T + "test_a_card_means_this_on_the_questions_clock", expect="2026-08-20T17:00:00.000000Z"),
    dict(id="C6", defect="the sentence doesn't say which clock its times are on",
         edits=[(_D, '        said += f" ({_zones.label(zone)})"', '        said += ""')],
         selector=_T + "test_aug_20_in_denver_is_denvers_day_and_the_rows_read_on_its_clock",
         expect="where Time is on Aug 20 (Denver time)"),
    dict(id="C7", defect="any text is taken as a question's zone",
         edits=[(_V, "    if not isinstance(zone, str) or zone not in known:", "    if not isinstance(zone, str):")],
         selector=_T + "test_any_other_zone_is_refused_in_words", expect="DID NOT RAISE"),
    dict(id="C9", defect="BOTH engines: a count column reads UTC, not its question's clock",
         edits=[(_V, '        expr, said = _count_conditions(c, counted_fields, f"“{label}”", view_zone(view))',
                 '        expr, said = _count_conditions(c, counted_fields, f"“{label}”")')],
         selector=_T + "test_a_count_column_reads_its_questions_clock", expect="24"),
    dict(id="C10", defect="a per-day summary doesn't name the clock its days are on (T-100)",
         edits=[(_D, '            head += f" ({_zones.label(zone)})"   # T-100', '            head += ""   # T-100')],
         selector=_T + "test_a_summary_per_day_names_the_clock_its_days_are_on", expect="per day (Denver time)"),
    dict(id="C11", defect="a table's times read in UTC on Denver's clock",
         edits=[(_V, "            return fmt_time(text, zone)\n", "            return fmt_time(text)\n")],
         selector=_T + "test_aug_20_in_denver_is_denvers_day_and_the_rows_read_on_its_clock", expect="Aug 20, 5:00 PM"),
    dict(id="C12", defect="a date field takes a time of day",
         edits=[(_V, '    if field["kind"] != "time":\n        raise ViewError(f"{field[\'label\']} has no time of day.")',
                 '    if False:\n        raise ViewError(f"{field[\'label\']} has no time of day.")')],
         selector=_T + "test_a_card_its_clock_cant_read_is_refused_in_words", expect="DID NOT RAISE"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    dsn = os.environ.get("AUTOSQL_T98_DSN")
    for var in ("AUTOSQL_RUNTIME_DSN", "AUTOSQL_COMPILER_DSN", "AUTOSQL_PARITY_DSN"):
        if dsn and not os.environ.get(var):
            os.environ[var] = dsn
        if not os.environ.get(var) and "--dry-run" not in (argv or sys.argv[1:]):
            print(f"t98 mutants: refusing to run — set AUTOSQL_T98_DSN (or {var}) to a throwaway Postgres;"
                  " without it the SQL half would skip and every SQL mutant would 'survive' for nothing")
            return 2
    runner.T78_MUTANTS[:] = T98_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
