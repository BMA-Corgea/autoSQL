"""demo/tests/t133_mutants.py — T-133's mutants: the clock list gives no line for a difference only before 1970.

Each breaks one thing T-133's tests hold: the quiet list (in the engine, the server's list and parity's list), the
line kept for a difference that reaches 1970, the line passed on to the page, and the refusal at use (a question that
reads Amsterdam's 1916 row still refused in the same words). Each must die on its own assertion. Run on
``t78_mutants.py``'s runner, from a scratch copy, with AUTOSQL_PARITY_DSN set to a throwaway Postgres.

    AUTOSQL_PARITY_DSN=… demo/.venv/bin/python demo/tests/t133_mutants.py [--dry-run] [--only Q1,Q2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t98.py::"
_P = "../parity/tests/test_t101.py::"
_Z = "../picks/zones.py"
_QUIET = _T + "test_a_zone_the_clocks_disagree_on_only_before_1970_gets_no_line"
_HISTORY = "    if last.year < 1970:\n        return None\n"
_OLD_LINE = "    if last.year < 1970:\n        return \"Times before 1970 can't be read on this clock.\"\n"

T133_MUTANTS = [
    dict(id="Q1", defect="the line about times before 1970 back in the engine",
         edits=[(_Z, _HISTORY, _OLD_LINE)], selector=_QUIET, expect="Times before 1970 can"),
    dict(id="Q2", defect="a difference that reaches January 1970 taken as history: its line lost",
         edits=[(_Z, _HISTORY, _HISTORY.replace("< 1970", "<= 1970"))], selector=_QUIET, expect="assert None =="),
    dict(id="Q3", defect="the quiet list made only where a difference starts before 1970: one that runs on loses its line",
         edits=[(_Z, _HISTORY, _HISTORY.replace("last.year", "first.year"))], selector=_QUIET, expect="assert None =="),
    dict(id="Q4", defect="the old line left in the engine (hidden on the page alone): the server's list still carries it",
         edits=[(_Z, _HISTORY, _OLD_LINE)],
         selector=_T + "test_the_list_from_this_database_gives_no_clock_a_line_about_history",
         expect="Times before 1970 can"),
    dict(id="Q5", defect="the old line back, seen by every zone of this database's list",
         edits=[(_Z, _HISTORY, _OLD_LINE)],
         selector=_P + "test_every_zone_this_machine_greyed_before_is_selectable_now", expect="Times before 1970 can"),
    dict(id="Q6", defect="the list quieted by dropping history from the question's check: a 1916 row on Amsterdam's clock "
                         "is read, not refused",
         edits=[(_Z, "            memo[zone] = disagreements(conn, zone, transitions)\n",
                 "            memo[zone] = tuple(g for g in disagreements(conn, zone, transitions) if g[1] > 0)\n")],
         selector=_P + "test_a_clock_the_list_keeps_quiet_still_refuses_a_row_from_then_in_the_same_words",
         expect="AssertionError: ('rows',)"),
    dict(id="Q7", defect="the server drops every line: a difference this fall shows no line either",
         edits=[("server/dashboard.py", '"note": mark[e["zone"]][1]} for e in shown]', '"note": None} for e in shown]')],
         selector=_T + "test_the_page_gets_the_list_with_each_zones_mark",
         expect="Times from November 2026"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t133 mutants: refusing to run — set AUTOSQL_PARITY_DSN to a throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T133_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
