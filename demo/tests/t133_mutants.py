"""demo/tests/t133_mutants.py — T-133's mutants: the clock list gives no line for a difference only before 1970.

Each breaks one thing T-133's tests hold: the quiet list (in the engine, the server's list and parity's list), the
line kept for a difference that reaches 1970, the line passed on to the page, and the refusal at use (a question that
reads Amsterdam's 1916 row still refused by the statement, in one sentence on both screens, the two-pane screen's second
engine still answering beside it). Each must die on its own assertion. Run on
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
_BOTH = ("../parity/tests/test_t133_refusal_on_both_screens.py::"
         "test_the_1916_row_on_amsterdams_clock_is_refused_by_the_statement_in_one_sentence_on_both_screens")
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
    # bar 3, as reworded (a-chk's reading of 4600939): the refusal is the statement's, in one sentence on both screens
    dict(id="Q8", defect="the dashboard answers the statement's refusal in the database's words, not the sentence",
         edits=[("server/dashboard.py", '"message": _zones.refusal_words(str(exc))}, status_code=422)',
                 '"message": str(exc)}, status_code=422)')],
         selector=_BOTH, expect="time zone Europe/Amsterdam: this database"),
    dict(id="Q9", defect="the two-pane screen refuses in the database's words, not the dashboard's sentence",
         edits=[("server/app.py", '        "body": _zones.refusal_words(detail),\n', '        "body": detail,\n')],
         selector=_BOTH, expect="AssertionError: time zone Europe/Amsterdam"),
    dict(id="Q10", defect="the dashboard asks for the two-pane screen's refusal, so its second engine runs once the "
                          "statement refused",
         edits=[("server/app.py", "def run_pick(conn, pick: dict, *, whole: bool = False, refusals_in_words: bool = False)",
                 "def run_pick(conn, pick: dict, *, whole: bool = False, refusals_in_words: bool = True)")],
         selector=_BOTH, expect="the second engine ran on the dashboard"),
    dict(id="Q11", defect="the two-pane screen's second engine pane left empty beside the refusal",
         edits=[("server/app.py", '    py_pane, py_total = _fallback_python_pane(conn, pick)\n    body = _refused(\n'
                 '        payload, pick=pick,\n        panes={"sql": _empty_pane("raised" if sent else "abandoned", _EMPTY_PANE_ZONE),',
                 '    py_pane, py_total = _empty_pane("abandoned", _EMPTY_PANE_ZONE), 0\n    body = _refused(\n'
                 '        payload, pick=pick,\n        panes={"sql": _empty_pane("raised" if sent else "abandoned", _EMPTY_PANE_ZONE),')],
         selector=_BOTH, expect="the second engine's pane didn't answer on its own clock"),
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
