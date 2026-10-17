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
         edits=[(_E, "if len(ts_text) != _TS_WIDTH or not _SERIES_TIME.fullmatch(ts_text):",
                 "if len(ts_text) != _TS_WIDTH:")],
         # the zoned path is HIGH 2's: the row passed the check, then local_time's None dropped it (the page's capped
         # Denver hour now refuses through the statement's own XPR06, whatever the second engine does)
         selector=_R + "test_the_second_engine_refuses_the_same_row_by_name[lowercase-America/Denver]",
         expect="DID NOT RAISE"),
    dict(id="G6", defect="the second engine refuses without naming the row",
         edits=[(_S, "raise ValueError(f\"row {r.key!r} has a time this can't read: {ts!r}\") from None", "raise")],
         selector=_R + "test_the_second_engine_refuses_the_same_row_by_name[fraction-None]",
         expect="not fixed-width UTC ISO-8601"),
    dict(id="G7", defect="the page doesn't catch XPR06: the summary answers 500",
         edits=[(_D, "if getattr(exc, \"sqlstate\", None) == SERIES_TIME_SQLSTATE:",
                 "if getattr(exc, \"sqlstate\", None) == \"no such state\":")],
         selector=_R + "test_the_page_says_which_heartbeat_and_why[em-spaces-None]",
         expect="assert 500 == 200"),
    dict(id="G8", defect="_span reads a field with no range (a-chk's MEDIUM: the 500 moved, not closed)",
         edits=[(_D, "    if not r:\n        return None, None\n    if zone is None:", "    if zone is None:")],
         selector=_R + "test_a_field_with_no_range_is_no_edge[None]",
         expect="TypeError"),
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
