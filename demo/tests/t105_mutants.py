"""demo/tests/t105_mutants.py — T-105's mutants: the catches that tell each database refusal in its own words.

Run on ``t78_mutants.py``'s runner (the kill on the test's own assertion, bytecode off, files restored, the digest
checked). RUN ON A SCRATCH COPY OF THE TREE, never in a worktree anyone reads. Read-only on the demo database.

    demo/.venv/bin/python demo/tests/t105_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

T105_MUTANTS = [
    dict(id="P1", defect="the catch removed: XPR01 from the probes or the statement answers HTTP 500 again",
         edits=[("server/app.py", '_OUT_OF_RANGE_SQLSTATE = "XPR01"', '_OUT_OF_RANGE_SQLSTATE = "XPR01-not-caught"')],
         selector="tests/test_t105.py::test_an_out_of_range_number_inside_equality_is_refused_in_words",
         expect="500"),
    # the T-105 round (a-chk's check): each refusal in its own words
    dict(id="MQ1", defect="the statement's catch widened to every database refusal: all told as an out-of-range number (a-chk's MQ1)",
         edits=[("server/app.py",
                 "        if refusals_in_words and state == _OUT_OF_RANGE_SQLSTATE:\n            # T-105: the statement itself",
                 "        if refusals_in_words:\n            # T-105: the statement itself")],
         selector="tests/test_t105.py::test_each_refusal_the_statement_meets_is_told_in_its_own_words",
         expect="number out of range"),
    dict(id="MQ2", defect="the probes' catch widened the same way",
         edits=[("server/app.py",
                 "        if refusals_in_words and state == _OUT_OF_RANGE_SQLSTATE:      # abs($.huge) == 1",
                 "        if refusals_in_words:      # abs($.huge) == 1")],
         selector="tests/test_t105.py::test_a_float8_overflow_met_by_a_probe_is_refused_in_its_own_words",
         expect="number out of range"),
    dict(id="MZ", defect="the zone refusal not caught: T-101's XPR05 answers 500 on the two-pane screen again",
         edits=[("server/app.py", '_ZONE_SQLSTATE = "XPR05"', '_ZONE_SQLSTATE = "XPR05-not-caught"')],
         selector="tests/test_t105.py::test_each_refusal_the_statement_meets_is_told_in_its_own_words",
         expect="500"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T105_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
