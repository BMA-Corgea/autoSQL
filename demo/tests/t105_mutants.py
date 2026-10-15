"""demo/tests/t105_mutants.py — T-105's mutant: the catch that turns XPR01 into words removed.

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
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T105_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
