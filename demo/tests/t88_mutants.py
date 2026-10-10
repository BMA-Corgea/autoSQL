"""demo/tests/t88_mutants.py — T-88's mutants: time over any date field, one number per value of a field.

Most break BOTH engines the same way — the two then agree, and only the answers worked out by hand
(``parity/pick-vectors.json``, the hand-written SQL in ``test_t88.py``) can catch them.  Run on
``t78_mutants.py``'s runner (each kill on the test's own assertion, bytecode off, files restored,
the digest checked).  RUN ON A SCRATCH COPY OF THE TREE, never in a worktree anyone reads (the
foreman's rule since T-86's check).

    demo/.venv/bin/python demo/tests/t88_mutants.py [--dry-run] [--only V1,V2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_M = "tests/test_t88.py::"
VECTORS = _M + "test_a_pick_vector_equals_its_hand_worked_answer_in_both_engines"
WEEK_SQL = _M + "test_samples_per_week_of_due_date_equals_hand_sql"
STATUS_SQL = _M + "test_samples_per_status_equals_hand_sql"

_SQL_WEEK = "date_trunc({_GRANULARITY_SQL[pick['bucket']]}, {value}::timestamptz)"
_PY_WEEK = "        trunc = day - timedelta(days=day.weekday())          # Monday is 0"
_SQL_RE = 'TIME_VALUE_RE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z)?$"'
_PY_RE = r'_TIME_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ)?\Z", re.ASCII)'

T88_MUTANTS = [
    dict(id="V1", defect="BOTH engines start a week on Sunday (they agree)",
         edits=[("../picks/builder.py", _SQL_WEEK,
                 "(CASE WHEN {_GRANULARITY_SQL[pick['bucket']]} = 'week' THEN date_trunc('week', {value}::timestamptz "
                 "+ interval '1 day') - interval '1 day' ELSE date_trunc({_GRANULARITY_SQL[pick['bucket']]}, "
                 "{value}::timestamptz) END)"),
                ("../picks/pyrunner/evaluate.py", _PY_WEEK,
                 "        trunc = day - timedelta(days=(day.weekday() + 1) % 7)")],
         selector=[VECTORS, WEEK_SQL], expect="!= [['2025-12-29T00:00:00Z', '2']"),
    dict(id="V2", defect="BOTH engines take a time without seconds (another form) as a time",
         edits=[("../picks/builder.py", _SQL_RE,
                 'TIME_VALUE_RE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?Z?)?$"'),
                ("../picks/pyrunner/evaluate.py", _PY_RE,
                 r'_TIME_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?Z?)?\Z", re.ASCII)'),
                ("../picks/pyrunner/evaluate.py", '        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)',
                 '        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)')],
         selector=VECTORS, expect="!= [['2025-12-29T00:00:00Z', '2'], ['2026-01-05T00:00:00Z', '3']]"),
    dict(id="V3", defect="BOTH engines read an empty text as blank in a group",
         edits=[("../picks/group.py", "    select = ['nullif( r.data #> %(grp_path)s, \\'null\\'::jsonb )  AS \"grp\"',",
                 "    select = ['nullif( nullif( r.data #> %(grp_path)s, \\'null\\'::jsonb ), \\'\"\"\\'::jsonb )  AS \"grp\"',"),
                ("../picks/pyrunner/group.py", '    if value is MISSING or value is None:\n        return ("blank",)',
                 '    if value is MISSING or value is None or value == "":\n        return ("blank",)'),
                ("../picks/pyrunner/group.py", '            "value": None if value is MISSING else value,',
                 '            "value": None if value is MISSING or value == "" else value,')],
         selector=VECTORS, expect="!= [['', '1']"),
    dict(id="V4", defect="the view (shared by both engines) asks for days when a week is picked",
         edits=[("../picks/view.py", '        pick["bucket"] = "off" if summary["per"] == "all" else summary["per"]',
                 '        pick["bucket"] = "off" if summary["per"] == "all" else ("day" if summary["per"] == "week" else summary["per"])')],
         selector=_M + "test_the_view_asks_for_exactly_the_unit_and_the_field_picked", expect="('day', 'due_date') == ('week', 'due_date')"),
    dict(id="V5", defect="the statement drops its check for a real day (2026-02-30 reaches the cast)",
         edits=[("../picks/builder.py", '                 f"\\n   AND pg_input_is_valid({value}, \'timestamptz\')")',
                 '                 "")')],
         selector=VECTORS, expect="DatetimeFieldOverflow"),
    dict(id="V6", defect="the second engine takes 24:00:00 as a time",
         edits=[("../picks/pyrunner/evaluate.py", _PY_RE,
                 r'_TIME_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-4]):[0-5]\d:[0-5]\dZ)?\Z", re.ASCII)'),
                ("../picks/pyrunner/evaluate.py", '        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)',
                 '        return (datetime.strptime(value.replace("T24:", "T00:"), "%Y-%m-%dT%H:%M:%SZ") + timedelta(days=value.count("T24:"))).replace(tzinfo=timezone.utc)')],
         selector=VECTORS, expect="the second engine:"),
    dict(id="V7", defect="the field reads skip a key that is not an identifier (as before T-88)",
         edits=[("../picks/view.py", "            found[paths.of([key])] = set(ts)",
                 "            if key.isidentifier():\n                found[paths.of([key])] = set(ts)")],
         selector=_M + "test_a_field_named_with_spaces_and_brackets_is_offered_and_read",
         expect="assert set() == {"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T88_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
