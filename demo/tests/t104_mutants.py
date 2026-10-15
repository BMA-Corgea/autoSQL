"""demo/tests/t104_mutants.py — T-104's mutants: the summaries' time axis and its width limit.

One per part of the fix, each killed on its own test's assertion.  Run on ``t78_mutants.py``'s runner
(bytecode off, files restored, the digest checked).  RUN ON A SCRATCH COPY OF THE TREE, never in a worktree
anyone reads, and under a memory cap: with the limit taken out, a per-hour axis from 1900 lays 1.11 M slots.

    prlimit --as=4G timeout 1800 demo/.venv/bin/python demo/tests/t104_mutants.py [--dry-run] [--only A1,A2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_M = "tests/test_t104.py::"
D = "server/dashboard.py"

T104_MUTANTS = [
    dict(id="A1", defect="an edge the clock can't show becomes 0001-01-01 again (an axis from year 1)",
         edits=[(D, "            return None      # read on this clock it leaves years 1..9999: that time is in no bucket",
                 '            return "0001-01-01T00:00:00"')],
         selector=_M + "test_on_a_clock_that_cannot_show_the_zero_date_the_axis_is_the_data_s_own",
         expect="months, not the data's own"),
    dict(id="A2", defect="no width limit: the axis is laid however wide it is",
         edits=[(D, "        if _slot_count(unit, lo, hi, zone) > AXIS_SLOTS:\n            # Too wide",
                 "        if False:\n            # Too wide")],
         selector=_M + "test_a_reading_in_1900_per_hour_is_refused_in_words[UTC]",
         expect="instead of a refusal"),
    dict(id="A3", defect="past the limit the axis keeps the data set's span (no filter can make it answer)",
         edits=[(D, "                lo, hi = first, last\n        if _slot_count(unit, lo, hi, zone) > AXIS_SLOTS:",
                 "                pass\n        if _slot_count(unit, lo, hi, zone) > AXIS_SLOTS:")],
         selector=_M + "test_a_filter_to_a_short_time_answers_again",
         expect="refused with a filter to one day"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T104_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
