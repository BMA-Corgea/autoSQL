"""demo/tests/t87_mutants.py — T-87's mutants: owner isolation, the probe that meets an out-of-range
number, number conditions.  On ``t78_mutants.py``'s runner (each kill on the test's own assertion,
bytecode off, files restored, the digest checked).  RUN ON A SCRATCH COPY OF THE TREE, never in a
worktree anyone reads.

    demo/.venv/bin/python demo/tests/t87_mutants.py [--dry-run] [--only P5,P7]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_M = "tests/test_t87.py::"

T87_MUTANTS = [
    dict(id="P5", defect="the field reads (values, ranges, groups, keys) drop the owner (T-86 check's mutant)",
         edits=[("../picks/view.py",
                 '    sql = template.replace("{table}", records.table).replace("{scope}", records.scope("r", params))',
                 '    sql = template.replace("{table}", records.table).replace("{scope}", "r.collection = %(collection)s")')],
         selector=[_M + "test_the_field_reads_offer_one_owners_values_ranges_and_groups",
                   _M + "test_the_keys_a_pick_is_judged_against_are_one_owners"],
         expect="another owner's field names were offered"),
    dict(id="P7", defect="the row provider is handed no owner",
         edits=[("../picks/pyrunner/rows.py",
                 "        owner = records.partition[1] if records.partition is not None else None",
                 "        owner = None")],
         selector=_M + "test_the_row_provider_is_handed_the_owner", expect="('noun:Reading', None)"),
    dict(id="P8", defect="a process-wide default may carry an owner",
         edits=[("../picks/env.py", "    if records.partition is not None:\n        raise ValueError(",
                 "    if False:\n        raise ValueError(")],
         selector=_M + "test_a_default_with_an_owner_is_refused", expect="DID NOT RAISE"),
    dict(id="P9", defect="a probe that meets an out-of-range number raises instead of firing (the old 500)",
         edits=[("../picks/probes.py",
                 '            fired = bool(conn.execute(p.sql, params).fetchone()[0])\n'
                 '    except Exception as exc:  # noqa: BLE001 — two SQLSTATEs, re-raised otherwise\n'
                 '        if getattr(exc, "sqlstate", None) not in _OUT_OF_RANGE or p.member != "a":',
                 '            fired = bool(conn.execute(p.sql, params).fetchone()[0])\n'
                 '    except Exception as exc:  # noqa: BLE001 — two SQLSTATEs, re-raised otherwise\n'
                 '        if True:')],
         selector=_M + "test_a_probe_that_meets_an_out_of_range_number_refuses_by_name", expect="answered 500"),
    dict(id="C13", defect='"is more than" includes the value (the T-86 check\'s mutant)',
         edits=[("../picks/view.py", '    sym = {"eq": "==", "on": "==", "ne": "!=", "gt": ">",',
                 '    sym = {"eq": "==", "on": "==", "ne": "!=", "gt": ">=",')],
         selector=_M + "test_a_number_condition_counts_what_hand_sql_counts", expect="int(a[\"number\"][\"exact\"]) == want"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T87_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
