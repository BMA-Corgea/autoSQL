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
OWN_KEY = _M + "test_every_offered_name_reads_its_own_key_in_both_engines"

_SQL_WEEK = "date_trunc({_GRANULARITY_SQL[pick['bucket']]}, {value}::timestamp)"
_PY_WEEK = "        trunc = day - timedelta(days=day.weekday())          # Monday is 0"
_SQL_RE = 'TIME_VALUE_RE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z)?$"'
_PY_RE = r'_TIME_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ)?\Z", re.ASCII)'

T88_MUTANTS = [
    dict(id="V1", defect="BOTH engines start a week on Sunday (they agree)",
         edits=[("../picks/builder.py", _SQL_WEEK,
                 "(CASE WHEN {_GRANULARITY_SQL[pick['bucket']]} = 'week' THEN date_trunc('week', {value}::timestamp "
                 "+ interval '1 day') - interval '1 day' ELSE date_trunc({_GRANULARITY_SQL[pick['bucket']]}, "
                 "{value}::timestamp) END)"),
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
         edits=[("../picks/builder.py", '                 f"\\n   AND pg_input_is_valid({value}, \'timestamp\')")',
                 '                 "")')],
         selector=VECTORS, expect="DatetimeFieldOverflow"),
    dict(id="V6", defect="the second engine takes 24:00:00 as a time",
         edits=[("../picks/pyrunner/evaluate.py", _PY_RE,
                 r'_TIME_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-4]):[0-5]\d:[0-5]\dZ)?\Z", re.ASCII)'),
                ("../picks/pyrunner/evaluate.py", '        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)',
                 '        return (datetime.strptime(value.replace("T24:", "T00:"), "%Y-%m-%dT%H:%M:%SZ") + timedelta(days=value.count("T24:"))).replace(tzinfo=timezone.utc)')],
         selector=VECTORS, expect="the second engine:"),
    dict(id="V7", defect="the field reads skip a key that is not an identifier (as before T-88)",
         edits=[("../picks/view.py", "            name = paths.name([key])\n            if name is not None:\n",
                 "            name = paths.name([key])\n            if name is not None and key.isidentifier():\n")],
         selector=_M + "test_a_field_named_with_spaces_and_brackets_is_offered_and_read",
         expect="assert set() == {"),
    # ── the T-88 check's fix round ──────────────────────────────────────
    dict(id="K1", defect="a name is spelled the JSON way (\\b, \\u0008): such keys go unoffered",
         edits=[("../picks/paths.py", '            out += "[" + _quote(k) + "]"',
                 '            out += "[" + __import__("json").dumps(k, ensure_ascii=False) + "]"'),
                ("../picks/paths.py", "            key = _unquote(m.group(1))", "            key = __import__('json').loads(m.group(1))")],
         selector=OWN_KEY, expect="keys never offered: [100"),
    dict(id="K2", defect="the check's HIGH itself: JSON spelling, and no parser asked whether it reads the key back",
         edits=[("../picks/paths.py", '            out += "[" + _quote(k) + "]"',
                 '            out += "[" + __import__("json").dumps(k, ensure_ascii=False) + "]"'),
                ("../picks/paths.py", "            key = _unquote(m.group(1))", "            key = __import__('json').loads(m.group(1))"),
                ("../picks/paths.py", '        for role in ("parser", "evaluator"):', '        for role in ():')],
         selector=OWN_KEY, expect="the engines differ"),
    dict(id="K3", defect="any spelling that decodes is taken as a name (a hand-sent \\b reads abc)",
         edits=[("../picks/paths.py", "    if of(out) != text:", "    if False:")],
         selector=_M + "test_a_name_spelled_any_other_way_is_refused", expect="DID NOT RAISE"),
    dict(id="K4", defect="the field reads name every key (an empty key breaks its data set)",
         edits=[("../picks/view.py", "            name = paths.name([key])\n            if name is not None:\n",
                 "            name = paths.of([key])\n            if name is not None:\n")],
         selector=_M + "test_a_record_with_an_empty_key_does_not_break_its_data_sets_fields",
         expect="a key is non-empty text, not ''"),
    dict(id="Z1", defect="a named time field is cut in the session's time zone",
         edits=[("../picks/builder.py", "{value}::timestamp),\\n", "{value}::timestamptz) AT TIME ZONE 'UTC',\\n"),
                ("../picks/builder.py", "pg_input_is_valid({value}, 'timestamp')", "pg_input_is_valid({value}, 'timestamptz')")],
         selector=_M + "test_the_pick_vectors_hold_whatever_the_sessions_time_zone",
         expect="AssertionError: [('count per week"),
    dict(id="Z2", defect="another host's series is cut in the session's time zone",
         edits=[("../picks/builder.py", "(data ->> 'ts')::timestamptz, 'UTC') AT TIME ZONE 'UTC'",
                 "(data ->> 'ts')::timestamptz) AT TIME ZONE 'UTC'")],
         selector=_M + "test_a_series_buckets_in_utc_whatever_the_sessions_time_zone",
         expect="('day', [['2026-01-04"),
    dict(id="S1", defect="the demo's board reads its measure as \"$.\" + name",
         edits=[("server/scoreboard.py", 'server_app.expr.parse(paths.dollar(spec["measure"]["field"]))',
                 'server_app.expr.parse("$." + spec["measure"]["field"])')],
         selector=_M + "test_a_board_measures_a_field_named_in_brackets", expect="Expected a field name after '.'"),
    # ── the four both-engine survivors the check found (asql-a-chk's edits, verbatim) ──
    dict(id="W3", defect="BOTH engines read a bracketed key with a dot (x[\"y.z\"]) as a dotted path (x.y.z)",
         edits=[("../picks/paths.py",
                 '                raise ValueError(f"{path!r} names an empty key")\n            out.append(key)',
                 '                raise ValueError(f"{path!r} names an empty key")\n            out.extend(key.split("."))')],
         selector=OWN_KEY, expect="names that read another key or nothing"),
    dict(id="VW1", defect="BOTH engines: one number per value ignores the page's conditions",
         edits=[("../picks/view.py",
                 '        "group": summary["by"],\n        "filter": filter_expression(view, fields),',
                 '        "group": summary["by"],\n        "filter": None,')],
         selector=_M + "test_one_number_per_value_keeps_the_pages_conditions", expect="assert [("),
    dict(id="VW2", defect="BOTH engines: a total per value is answered as an average",
         edits=[("../picks/view.py",
                 '        "measure": None if summary["fn"] == "count" else {"fn": summary["fn"], "field": summary["field"]},',
                 '        "measure": None if summary["fn"] == "count" else {"fn": "avg" if summary["fn"] == "sum" else summary["fn"], "field": summary["field"]},')],
         selector=_M + "test_a_total_per_value_is_a_total", expect="assert [("),
    dict(id="O1", defect="a summary over a named time field drops the owner",
         edits=[("../picks/builder.py", "    where = p.where_clause() + guard",
                 "    where = (p.where_clause() if not field else \" WHERE collection = %(collection)s\") + guard")],
         selector=_M + "test_a_summary_over_a_named_time_field_reads_one_owner",
         expect="another owner's record was counted"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T88_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
