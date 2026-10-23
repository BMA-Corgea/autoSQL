"""demo/tests/t126_mutants.py — T-126's mutants: the setup reads a record type in two statements, its answer unchanged.

Each breaks one fact the two statements work out (or how many statements there are), and must die on its own
assertion: the old-against-new differential (T-114's tip's reader, frozen in the test), the Python reader against
Postgres, the statement count, or T-114's kind-count test. Run on ``t78_mutants.py``'s runner, from a scratch copy,
with AUTOSQL_PARITY_DSN set to a throwaway Postgres.

    AUTOSQL_PARITY_DSN=… demo/.venv/bin/python demo/tests/t126_mutants.py [--dry-run] [--only S1,S2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_P = "../parity/tests/test_t126_setup.py::"
_DIFF = _P + "test_every_collection_reads_as_t114s_tip_read_it"
_PY = _P + "test_the_python_reader_reads_every_added_type_as_postgres_does"
_COUNT = _P + "test_the_setup_sends_as_many_statements_for_200_fields_as_for_5"
_V = "../picks/view.py"

T126_MUTANTS = [
    dict(id="S1", defect="the distinct count by text, not jsonb equality: 1 and 1.0 are two values",
         edits=[(_V, "   GROUP BY 1, 2\n), s AS MATERIALIZED (", "   GROUP BY 1, 2, x.v::text\n), s AS MATERIALIZED (")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S2", defect="the blank group missed: a row that lacks the field is no group of its own",
         edits=[(_V, "distinct + (1 if present < total else 0)", "distinct")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S3", defect="the forms counted by distinct value, not by row (a value held ten times counts once)",
         edits=[(_V, "coalesce(sum(n) FILTER (WHERE filled AND looks), 0)::bigint AS looks_n",
                 "count(*) FILTER (WHERE filled AND looks) AS looks_n")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S4", defect="a blank text counted in the forms",
         edits=[(_V, "  SELECT i, n, looks, t <> '' AS filled,", "  SELECT i, n, looks, true AS filled,")],
         selector="../parity/tests/test_t114_times.py::test_the_setups_sql_counts_what_its_python_counts"
                  "[blank strings are not counted]",
         expect="AssertionError: ('blank strings are not counted'"),
    dict(id="S5", defect="the values read only below VALUE_LIMIT: a field of exactly VALUE_LIMIT values offers none",
         edits=[(_V, '        if kind == "text" and strings_n <= VALUE_LIMIT:',
                 '        if kind == "text" and strings_n < VALUE_LIMIT:')],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S6", defect="a key opened one level though it sometimes holds no object",
         edits=[(_V, '        if ts == {"object"}:\n            for k2, ts2 in inner.get(key, {}).items():',
                 '        if "object" in ts:\n            for k2, ts2 in inner.get(key, {}).items():')],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S7", defect="a key with no name both engines read back is kept (the empty key)",
         edits=[(_V, "            name = paths.name([key])\n            if name is not None:\n                found[name]",
                 "            name = paths.name([key]) or key\n            if name is not None:\n                found[name]")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S8", defect="a day the calendar lacks taken as an edge of a date field's span",
         edits=[(_V, "CASE WHEN looks AND len = 10 AND xpr.time_at(t) IS NOT NULL THEN t END AS day",
                 "CASE WHEN looks AND len = 10 THEN t END AS day")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S9", defect="the Python reader tells values apart by their repr: Decimal 1 and 1.0 are two",
         edits=[(_V, "len({_distinct_key(v) for v in held})", "len({repr(v) for v in held})")],
         selector=_PY, expect="AssertionError: [("),
    dict(id="S10", defect="the facts read one field a statement again: the count grows with the fields",
         edits=[(_V, '''    facts = _read(conn, records, _FACTS_SQL, {
        "collection": collection, "k1": [st[0] for st in steps], "k2": [st[1] if len(st) > 1 else "" for st in steps],
        "lvl": [len(st) - 1 for st in steps], "limit": VALUE_LIMIT}).fetchall()''',
                 '''    facts = [row for st in steps for row in _read(conn, records, _FACTS_SQL, {
        "collection": collection, "k1": [st[0]], "k2": [st[1] if len(st) > 1 else ""],
        "lvl": [len(st) - 1], "limit": VALUE_LIMIT}).fetchall()]''')],
         selector=_COUNT, expect="AssertionError: {'noun:Five'"),
    dict(id="S11", defect="the cheap test for LOOKS at the wrong place: no time looks like one",
         edits=[(_V, "substr(t, 5, 1) = '-' AND substr(t, 8, 1) = '-'", "substr(t, 6, 1) = '-' AND substr(t, 8, 1) = '-'")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S12", defect="the not-a-date shortcut turned round: a word is a date",
         edits=[(_V, "len <> 10 OR t !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AS not_date",
                 "len = 10 AND t !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AS not_date")],
         selector=_DIFF, expect="AssertionError: [("),
    dict(id="S13", defect="JSON null counted as a value: a field both null and absent in places has one group too many",
         edits=[(_V, "   WHERE {scope}\n     AND x.v <> 'null'::jsonb\n", "   WHERE {scope}\n")],
         selector=_DIFF, expect="AssertionError: [("),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t126 mutants: refusing to run — set AUTOSQL_PARITY_DSN to a throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T126_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
