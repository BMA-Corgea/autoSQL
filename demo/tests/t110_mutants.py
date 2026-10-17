"""demo/tests/t110_mutants.py — T-110's mutants: a sort over text nested in jsonb is refused on a locale database.

The check skipped, the probe off by one, the refusal swallowed, its words lost, the check asked every time. The
parity tests run on a Debian en_US throwaway (AUTOSQL_LOCALE_DSN) and an alpine one (AUTOSQL_PARITY_DSN). Run on
``t78_mutants.py``'s runner. RUN ON A SCRATCH COPY.

    AUTOSQL_LOCALE_DSN=… AUTOSQL_PARITY_DSN=… demo/.venv/bin/python demo/tests/t110_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_N = "../parity/tests/test_t106_text_order.py::"
_P = "../parity/tests/test_t110_nested_order.py::"
_PR = "../picks/probes.py"
_B = "../picks/builder.py"

T110_MUTANTS = [
    dict(id="N1", defect="the order check skipped: every database treated as code points",
         edits=[(_PR, "    if nested_text_in_code_points(conn):\n        return None\n",
                 "    if True:\n        return None\n")],
         selector=_N + "test_text_nested_in_a_sorted_value_is_refused_on_a_locale_database[en_US-$.obj]",
         expect="DID NOT RAISE"),
    dict(id="N2", defect="the probe off by one: three rows needed where two can be ordered two ways",
         edits=[(_B, '\'SELECT count(*) >= 2 AS "fired"', '\'SELECT count(*) >= 3 AS "fired"')],
         selector=_N + "test_text_nested_in_a_sorted_value_is_refused_on_a_locale_database[en_US-$.arr]",
         expect="DID NOT RAISE"),
    dict(id="N3", defect="the refusal swallowed: the two-pane screen never asks, and answers in two orders",
         edits=[("server/app.py", "        sort_outcome = probes.check_sort(conn, pick, keys)\n",
                 "        sort_outcome = None\n")],
         selector=_P + "test_a_sort_by_the_payload_is_refused_in_words_on_a_locale_database[en_US]",
         expect="(200,"),
    dict(id="N4", defect="the sort refusal loses its own words on the two-pane screen",
         edits=[("server/errors.py", '"body": sort_order_words(exc.field) if exc.member == "c" else _LAYER_2_BODY,',
                 '"body": _LAYER_2_BODY,')],
         selector=_P + "test_a_sort_by_the_payload_is_refused_in_words_on_a_locale_database[en_US]",
         expect="The expression was inside the subset"),
    dict(id="N5", defect="the order check asked again on every question, never read from its cache",
         edits=[(_PR, "            if key[3] == started:\n                return hit\n",
                 "            if False:\n                return hit\n")],
         selector=_N + "test_the_order_check_runs_once_per_database[alpine-C]",
         expect="the second ask reads the cache"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_LOCALE_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t110 mutants: refusing to run — set AUTOSQL_LOCALE_DSN (and AUTOSQL_PARITY_DSN) to throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T110_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
