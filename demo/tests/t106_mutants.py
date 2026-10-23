"""demo/tests/t106_mutants.py — T-106's mutants: the collation dropped from one place at a time.

Each one gives text back to the database's collation in ONE place the statement (or the second engine) orders it;
parity/tests/test_t106_text_order.py, run on a locale-collated database, must catch each on its own assertion.
Run on ``t78_mutants.py``'s runner (bytecode off, files restored, the digest checked). RUN ON A SCRATCH COPY.
Needs AUTOSQL_LOCALE_DSN (postgres:16, --locale=en_US.utf8); AUTOSQL_PARITY_DSN (alpine) optional.

    AUTOSQL_LOCALE_DSN="host=… …" demo/.venv/bin/python demo/tests/t106_mutants.py [--dry-run] [--only X1]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "../parity/tests/test_t106_text_order.py::"
_B = "../picks/builder.py"
_LOC = "[en_US]"

T106_MUTANTS = [
    dict(id="X1", defect="a sorted jsonb value's strings back in the collation (the shared helper)",
         edits=[(_B, "THEN {value} #>> '{{}}' END) COLLATE \\\"C\\\" {direction} NULLS LAST\")",
                 "THEN {value} #>> '{{}}' END) {direction} NULLS LAST\")")],
         selector=_T + "test_rows_sorted_by_text_are_in_code_points" + _LOC, expect="assert"),
    dict(id="X2", defect="the key order with no sort back in the collation",
         edits=[(_B, "            return f' ORDER BY {q}key COLLATE \"C\", {q}key ASC'",
                 "            return f' ORDER BY {q}key ASC'")],
         selector=_T + "test_rows_with_no_sort_are_in_key_code_points" + _LOC, expect="assert"),
    dict(id="X3", defect="the sort's key tie-break back in the collation",
         edits=[(_B, "        lead = f'{code_point_order(value, direction)}, {q}key COLLATE \"C\"'",
                 "        lead = f'{code_point_order(value, direction)}'")],
         selector=_T + "test_rows_sorted_by_text_are_in_code_points" + _LOC, expect="assert"),
    dict(id="X4", defect="the rolling window's key order back in the collation",
         edits=[(_B, "f\"               ORDER BY     (r.data ->> '{series['time']}') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\"\\n\"",
                 "f\"               ORDER BY     (r.data ->> '{series['time']}') COLLATE \\\"C\\\", r.key\\n\"")],
         selector=_T + "test_the_series_window_orders_ties_by_key_code_points" + _LOC, expect="assert"),
    dict(id="X5", defect="the demo series' named window (ts / sender_id) back in the collation",
         edits=[(_B, "    \"               ORDER BY     (r.data ->> 'ts') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\")\"",
                 "    \"               ORDER BY     (r.data ->> 'ts') COLLATE \\\"C\\\", r.key)\"")],
         selector=_T + "test_the_changed_flag_reads_ties_in_key_code_points[en_US-sender_id]", expect="assert"),
    dict(id="X6", defect="the general series' named window back in the collation",
         edits=[(_B, "f\"               ORDER BY     (r.data ->> '{time}') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\")\"),",
                 "f\"               ORDER BY     (r.data ->> '{time}') COLLATE \\\"C\\\", r.key)\"),")],
         selector=_T + "test_the_changed_flag_reads_ties_in_key_code_points[en_US-who]", expect="assert"),
    # a-chk's C1/C3/C5: the TIME text's collation in each window (X4-X6 drop the key's)
    dict(id="X13", defect="the rolling window's time order back in the collation",
         edits=[(_B, "f\"               ORDER BY     (r.data ->> '{series['time']}') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\"\\n\"",
                 "f\"               ORDER BY     (r.data ->> '{series['time']}'), r.key COLLATE \\\"C\\\"\\n\"")],
         selector=_T + "test_the_series_window_orders_ties_by_key_code_points" + _LOC, expect="assert"),
    dict(id="X14", defect="the demo series' named window: its time order back in the collation",
         edits=[(_B, "    \"               ORDER BY     (r.data ->> 'ts') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\")\"",
                 "    \"               ORDER BY     (r.data ->> 'ts'), r.key COLLATE \\\"C\\\")\"")],
         selector=_T + "test_the_changed_flag_reads_ties_in_key_code_points[en_US-sender_id]", expect="assert"),
    dict(id="X15", defect="the general series' named window: its time order back in the collation",
         edits=[(_B, "f\"               ORDER BY     (r.data ->> '{time}') COLLATE \\\"C\\\", r.key COLLATE \\\"C\\\")\"),",
                 "f\"               ORDER BY     (r.data ->> '{time}'), r.key COLLATE \\\"C\\\")\"),")],
         selector=_T + "test_the_changed_flag_reads_ties_in_key_code_points[en_US-who]", expect="assert"),
    dict(id="X7", defect="a lookup's match order back in the collation",
         edits=[("../picks/lookup.py", "', m.key COLLATE \"C\", m.key ASC'", "', m.key ASC'")],
         selector=_T + "test_a_lookups_matches_are_in_key_code_points" + _LOC, expect="assert"),
    dict(id="X8", defect="a board's group order back in jsonb's (collated) order",
         edits=[("../picks/group.py", "        order = builder.code_point_order('\"grp\"', SORT_DIRS[s[\"dir\"]])",
                 "        order = f'\"grp\" {SORT_DIRS[s[\"dir\"]]} NULLS LAST'")],
         selector=_T + "test_a_board_by_group_is_in_code_points" + _LOC, expect="assert"),
    dict(id="X9", defect="the second engine's board tie-break back to Python's > (a number beside a string crashes)",
         edits=[("../picks/pyrunner/group.py", "        return compare_values(x[\"grp\"], y[\"grp\"], descending=False, group=True)",
                 "        return compare_values(x[\"grp\"], y[\"grp\"], descending=False)")],
         selector=_T + "test_a_board_by_count_breaks_ties_by_group_code_points" + _LOC, expect="TypeError"),
    dict(id="X10", defect="the probe's first offending row back in the collation",
         edits=[("../picks/probes.py", "        ' ORDER BY r.key COLLATE \"C\"\\n'", "        ' ORDER BY r.key\\n'")],
         selector=_T + "test_the_probes_first_offending_row_is_by_key_code_points" + _LOC, expect="assert"),
    dict(id="X11", defect="the setup's value list back in the collation",
         edits=[("../picks/view.py", "array_agg(s.t ORDER BY s.t COLLATE \"C\") AS strings",
                 "array_agg(s.t ORDER BY s.t) AS strings")],          # T-126: the facts statement's value list
         selector=_T + "test_the_setup_lists_values_and_keys_in_code_points" + _LOC, expect="assert"),
    dict(id="X12", defect="the setup's key list back in the collation",
         edits=[("../picks/view.py", "SELECT DISTINCT k COLLATE \"C\" AS k FROM {table} r",
                 "SELECT DISTINCT k AS k FROM {table} r")],
         selector=_T + "test_the_setup_lists_values_and_keys_in_code_points" + _LOC, expect="assert"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_LOCALE_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t106 mutants: refusing to run — set AUTOSQL_LOCALE_DSN to a locale-collated throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T106_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
