"""demo/tests/t109_mutants.py — T-109's mutants (its round, a-chk's two HIGHs and MEDIUM): a series time either
engine can't read is refused by name, by each engine on its own, and never reaches the span.

Each brings back a silent wrong number or a 500; the parity tests (a scratch database of the throwaway) must
catch each. Run on ``t78_mutants.py``'s runner. RUN ON A SCRATCH COPY.

    AUTOSQL_PARITY_DSN="host=… …" demo/.venv/bin/python demo/tests/t109_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "../parity/tests/test_t109_series_guard.py::test_a_summary_over_a_series_holding_an_unreadable_time_refuses_in_words"
_R = "../parity/tests/test_t109_refuses_by_name.py::"
_B = "../picks/builder.py"
_E = "../picks/pyrunner/evaluate.py"
_S = "../picks/pyrunner/shape.py"
_D = "../demo/server/dashboard.py"
_A = "../demo/server/app.py"
_RT = "../runtime/runtime.sql"
_F = "../runtime/tests/test_refusals_never_fold.py::test_a_constant_argument_case_never_raises_when_the_else_is_not_reached"

T109_MUTANTS = [
    dict(id="G3", defect="the label's refusal gone: an unreadable time is a NULL bucket again (8,401, nothing said)",
         edits=[(_B, "ELSE xpr.series_time_refused(key, (data ->> '{time}')) END\")", "ELSE NULL END\")")],
         selector=_R + "test_the_statement_alone_refuses_the_row_by_name[lowercase-None]",
         expect="the statement alone answered 8,401, the row left out"),
    dict(id="G4", defect="on a clock: the unreadable row dropped in the WHERE again (8,400, nothing said)",
         edits=[(_B, "THEN {_in_years(local, value)} ELSE true END", "THEN {_in_years(local, value)} ELSE false END")],
         selector=_R + "test_the_statement_alone_refuses_the_row_by_name[lowercase-America/Denver]",
         expect="the statement alone answered 8,400, the row left out"),
    dict(id="G5", defect="the second engine's check is strptime's again, ignoring letter case (a-chk's HIGH 2)",
         # T-114: the check is the rule's (picks/times.py), case-sensitive like the statement's
         edits=[("../picks/times.py", "_READABLE = re.compile(READABLE)", "_READABLE = re.compile(READABLE, re.IGNORECASE)"),
                ("../picks/times.py", '    if rest == "Z":', '    if rest in ("Z", "z"):')],
         # the zoned path is HIGH 2's: the row passed the check, then local_time's None dropped it (the page's capped
         # Denver hour now refuses through the statement's own XPR06, whatever the second engine does)
         selector=_R + "test_the_second_engine_refuses_the_same_row_by_name[lowercase-America/Denver]",
         expect="DID NOT RAISE"),
    dict(id="G6", defect="the second engine refuses without naming the row",
         edits=[(_S, "raise ValueError(f\"row {r.key!r} has a time this can't read: {ts!r}\") from None", "raise")],
         # T-114: a fraction reads now; lowercase is still no readable time (picks.times), its words the rule's
         selector=_R + "test_the_second_engine_refuses_the_same_row_by_name[lowercase-None]",
         expect="not a readable time"),
    dict(id="G7", defect="the page doesn't catch XPR06: the summary answers 500",
         edits=[(_D, "if getattr(exc, \"sqlstate\", None) == SERIES_TIME_SQLSTATE:",
                 "if getattr(exc, \"sqlstate\", None) == \"no such state\":")],
         selector=_R + "test_the_page_says_which_heartbeat_and_why[em-spaces-None]",
         expect="assert 500 == 200"),
    dict(id="G8", defect="_span reads a field with no range (a-chk's MEDIUM: the 500 moved, not closed)",
         edits=[(_D, "    if not r:\n        return None, None\n", "")],
         selector=_R + "test_a_field_with_no_range_is_no_edge[None]",
         expect="TypeError"),
    dict(id="G9", defect="the two-pane screen doesn't word XPR06 from the statement: /api/pick answers 500 again",
         edits=[(_A, "        if refusals_in_words and state == _SERIES_TIME_SQLSTATE:\n"
                     "            # T-109's round: the statement met a series time it can't read, and refused it by name\n"
                     "            return _series_time_refusal(conn, pick, exc, **refused)\n", "")],
         selector=_R + "test_the_two_pane_screen_says_which_heartbeat_and_why[lowercase-None]",
         expect="(500, 'Internal Server Error')"),
    dict(id="G10", defect="xpr.series_time_refused IMMUTABLE again: a constant-argument CASE raises at plan time",
         edits=[(_RT, "xpr.series_time_refused(key text, value text) RETURNS text\nLANGUAGE plpgsql VOLATILE",
                 "xpr.series_time_refused(key text, value text) RETURNS text\nLANGUAGE plpgsql IMMUTABLE")],
         selector=_F + "[series_time_refused]", expect="its series time is not one this reads"),
    dict(id="G11", defect="xpr.clock_refused IMMUTABLE again: a constant-argument CASE raises at plan time",
         edits=[(_RT, "xpr.clock_refused(t timestamptz, zone text) RETURNS timestamp\nLANGUAGE plpgsql VOLATILE",
                 "xpr.clock_refused(t timestamptz, zone text) RETURNS timestamp\nLANGUAGE plpgsql IMMUTABLE")],
         selector=_F + "[clock_refused]", expect="this database's clock differs from the evaluator's"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t109 mutants: refusing to run — set AUTOSQL_PARITY_DSN to a throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T109_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
