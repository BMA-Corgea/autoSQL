"""demo/tests/t109_mutants.py — T-109's mutants: the series time's guard removed, with no zone and on a clock.

Each brings back the HTTP 500 every summary of a data set gave on ONE stored time Postgres can't read; the parity
test (a scratch database of the throwaway) must catch each. Run on ``t78_mutants.py``'s runner. RUN ON A SCRATCH COPY.

    AUTOSQL_PARITY_DSN="host=… …" demo/.venv/bin/python demo/tests/t109_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "../parity/tests/test_t109_series_guard.py::test_a_summary_over_a_series_holding_an_unreadable_time_refuses_in_words"
_B = "../picks/builder.py"

T109_MUTANTS = [
    dict(id="G1", defect="no zone: the series time cast with no guard again",
         edits=[(_B, '        guard = f"\\n   AND {_series_readable(p, time)}"', '        guard = ""')],
         selector=_T + "[day-None]", expect="Internal Server Error"),
    dict(id="G2", defect="on a clock: the clock read before the time is known to be readable",
         edits=[(_B, "AND CASE WHEN {_series_readable(p, time)} THEN {_in_years(local, value)} ELSE false END",
                 "AND CASE WHEN true THEN {_in_years(local, value)} ELSE false END")],
         selector=_T + "[day-America/Denver]", expect="Internal Server Error"),
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
