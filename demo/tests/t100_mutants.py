"""demo/tests/t100_mutants.py — T-100's mutants: summaries cut on the question's clock.

Most break BOTH engines the same way (the statement the builder writes AND the second engine's
bucketing), so the two still agree and only answers worked out by hand can catch them
(``parity/pick-vectors-in-zone.json`` and the demo numbers in ``test_t100.py``).  Run on
``t78_mutants.py``'s runner (each kill on the test's own assertion, bytecode off, files restored,
the digest checked).  RUN ON A SCRATCH COPY OF THE TREE, never in a worktree anyone reads.

The SQL half needs a THROWAWAY Postgres: set AUTOSQL_T98_DSN (or AUTOSQL_PARITY_DSN).

    AUTOSQL_T98_DSN="host=… …" demo/.venv/bin/python demo/tests/t100_mutants.py [--dry-run] [--only Z1,Z2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t100.py::"
VECTORS = "../parity/tests/test_t100_vectors.py::test_every_bucket_case_equals_its_hand_answer_in_both_engines"
GUARD = "../parity/tests/test_t100_vectors.py::test_a_summary_on_a_zone_the_clocks_disagree_on_is_refused_by_name"
_B = "../picks/builder.py"
_E = "../picks/pyrunner/evaluate.py"
_D = "server/dashboard.py"

_SQL_ON_CLOCK = '        return lambda t: f"({t} AT TIME ZONE %(bkt_zone)s::text)"'   # the plain reading (D empty)
_PY_ON_CLOCK = "    return at.astimezone(ZoneInfo(zone)).replace(tzinfo=None)"
_PY_DATE = "    if len(value) == 10:\n        return at.replace(tzinfo=None)\n"
_PY_WALL = "    return truncate_label(at.replace(tzinfo=timezone.utc), granularity)[:-1]"
_SQL_LABEL = ('_ZONED_LABEL = ("to_char( date_trunc({g}, {local}),\\n"\n'
              '                "                \'YYYY-MM-DD\\"T\\"HH24:MI:SS\' )")')

T100_MUTANTS = [
    dict(id="Z1", defect="BOTH engines cut the buckets in UTC whatever the zone (they agree)",
         edits=[(_B, _SQL_ON_CLOCK, _SQL_ON_CLOCK.replace("AT TIME ZONE %(bkt_zone)s::text)", "AT TIME ZONE 'UTC')")),
                (_E, _PY_ON_CLOCK, _PY_ON_CLOCK.replace("ZoneInfo(zone)", 'ZoneInfo("UTC")'))],
         selector=VECTORS, expect="Denver, Mar 8: a 23-hour day"),
    dict(id="Z2", defect="BOTH engines start the week on Sunday",
         edits=[(_B, _SQL_LABEL,
                 '_ZONED_LABEL = ("to_char( CASE WHEN {g} = \'week\' THEN date_trunc({g}, {local} + interval \'1 day\') '
                 '- interval \'1 day\' ELSE date_trunc({g}, {local}) END,\\n"\n'
                 '                "                \'YYYY-MM-DD\\"T\\"HH24:MI:SS\' )")'),
                (_E, _PY_WALL,
                 "    if granularity == \"week\":\n"
                 "        m = truncate_label((at + timedelta(days=1)).replace(tzinfo=timezone.utc), granularity)[:-1]\n"
                 "        return (datetime.strptime(m, \"%Y-%m-%dT%H:%M:%S\") - timedelta(days=1)).strftime(\"%Y-%m-%dT%H:%M:%S\")\n"
                 + _PY_WALL)],
         selector=VECTORS, expect="Denver weeks start on Monday"),
    dict(id="Z3", defect="BOTH engines shift a calendar date by the zone's offset",
         edits=[(_B, "    if not dates:\n        return on_clock\n", "    if True:\n        return on_clock\n"),
                (_E, _PY_DATE, "")],
         selector=VECTORS, expect="a date is its own day west of UTC too"),
    dict(id="Z4", defect="the hour axis keeps an hour the clock skips (an empty 2:00 AM bar on Mar 8)",
         edits=[(_D, "        if zone is None or unit != \"hour\" or _clock_shows(t, zone):",
                 "        if zone is None or unit != \"hour\" or True:")],
         selector=_T + "test_the_axis_has_no_slot_for_an_hour_the_clock_skips", expect="2026-03-08T02:00:00"),
    dict(id="Z5", defect="the zoned bucket reads the clock without its check (T-101: D ignored)",
         edits=[(_B, "    gaps = tuple(resolver(zone))\n    p.params[\"bkt_zone\"] = zone\n    if not gaps:",
                 "    gaps = tuple(resolver(zone))\n    p.params[\"bkt_zone\"] = zone\n    if True:")],
         selector=GUARD, expect="DID NOT RAISE"),
    dict(id="Z6", defect="BOTH engines keep the Z on a zoned label",
         edits=[(_B, _SQL_LABEL, _SQL_LABEL.replace("HH24:MI:SS' )", "HH24:MI:SS\\\"Z\\\"' )")),
                (_E, _PY_WALL, _PY_WALL.replace("[:-1]", ""))],
         selector=VECTORS, expect="Denver, Mar 8: a 23-hour day"),
    # a-chk's two MEDIUMs on T-100 (both HTTP 500s), each held by its own test
    dict(id="Z7", defect="the hour axis tests only an hour's first second (Lord Howe's 2:30-2:59 lose their slot)",
         edits=[(_D, "    for m, s in ((t.minute, t.second), (59, 59)):", "    for m, s in ((t.minute, t.second),):")],
         selector=_T + "test_an_hour_whose_first_minutes_the_clock_skips_keeps_its_slot", expect="2026-10-04T02:00:00"),
    dict(id="Z8", defect="the statement buckets a clock reading outside years 1..9999 (the zero date west of UTC)",
         edits=[(_B, "            f\" OR ({local} >= '0001-01-01 00:00:00'::timestamp AND {local} < '10000-01-01 00:00:00'::timestamp))\")",
                 "            f\" OR true)\")")],
         selector=VECTORS, expect="Denver: the zero date"),
    dict(id="Z9", defect="the axis writes year 1 as \"1\" (strftime's way), so its slots never meet the engines' buckets",
         edits=[(_D, "    return (f\"{t.year:04d}-", "    return (f\"{t.year}-")],
         selector=_T + "test_the_axis_writes_years_with_four_digits", expect="1-01-01"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    dsn = os.environ.get("AUTOSQL_T98_DSN")
    if dsn and not os.environ.get("AUTOSQL_PARITY_DSN"):
        os.environ["AUTOSQL_PARITY_DSN"] = dsn
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t100 mutants: refusing to run — set AUTOSQL_T98_DSN (or AUTOSQL_PARITY_DSN) to a throwaway Postgres;"
              " without it the SQL half would skip and every SQL mutant would 'survive' for nothing")
        return 2
    runner.T78_MUTANTS[:] = T100_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
