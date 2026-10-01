"""T-67: contains() compares the way GIMS's _eq does: numbers as doubles, at every depth.

GIMS's _fn_contains (expr.py:488-499) is any(_eq(needle, x) for x in hay), and _eq
(expr.py:363-378) compares numbers as doubles. xpr.contains compared list elements with jsonb
equality, which is exact numeric, so contains([12345678901234568], 12345678901234567) was false
where GIMS says True (the T-60/61/63 refute-review, F61-1). T-61 fixed == and != with
xpr.eq_deep, which IS _eq; contains now uses it too, so beyond DBL_MAX it refuses (XPR01)
where Python raises OverflowError.

Every case is held to GIMS's own _fn_contains (demo/vendor/expr.py). Values come from a ROW
SOURCE, and Python's None is SQL NULL (never jsonb 'null'), as the compiler delivers it.

Database tests: AUTOSQL_RUNTIME_DSN, as in test_runtime.py.  They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is the live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")

_spec = importlib.util.spec_from_file_location("t67_gims_expr", ROOT / "demo" / "vendor" / "expr.py")
GIMS = importlib.util.module_from_spec(_spec)
sys.modules["t67_gims_expr"] = GIMS
_spec.loader.exec_module(GIMS)

#: (haystack, needle). The first group is where exact and double equality part ways.
CASES = [
    ([12345678901234568], 12345678901234567), ([12345678901234567], 12345678901234568),
    ([9007199254740993], 9007199254740992), ([0.1], 0.1000000000000000055511151231257827),
    ([[12345678901234568]], [12345678901234567]), ([{"k": 12345678901234567}], {"k": 12345678901234568}),
    ([1, [2, [3, 12345678901234567]]], [2, [3, 12345678901234568]]),
    # controls: equal or unequal either way
    ([1], 1.0), ([1.0], 1), ([[1, 2]], [1, 2.0]), ([1, 2], 3), ([12345678901234567], 12345678901234570),
    ([None, 1], None), ([1], None), ([None], 1), ([], 1),
    ([True], 1), ([1], True), ([True], True), ([False], 0),
    (["2"], 2), (["a", "b"], "b"), ([{"a": 1}], {"a": 1, "b": 2}),
    ("abc", "b"), ("abc", "z"), (None, 1),
]


def _sql(conn, pairs):
    q = ("SELECT xpr.contains(nullif(x -> 0, 'null'::jsonb), nullif(x -> 1, 'null'::jsonb)) "
         "FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS t(x, n) ORDER BY n")
    return [r[0] for r in conn.execute(q, (json.dumps(pairs),)).fetchall()]


@pytest.fixture(scope="module")
def conn():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as cx:
        yield cx


def test_the_long_integer_cases_really_part_exact_from_double_equality():
    assert 12345678901234567 != 12345678901234568
    assert float(12345678901234567) == float(12345678901234568)


@needs_db
def test_contains_is_gims_contains(conn):
    got = _sql(conn, [list(c) for c in CASES])
    want = [GIMS._fn_contains(list(c), {}) for c in CASES]
    assert got == want, [(c, g, w) for c, g, w in zip(CASES, got, want) if g != w]


@needs_db
def test_beyond_dbl_max_it_refuses_where_python_raises(conn):
    import psycopg
    huge = 10 ** 400
    with pytest.raises(OverflowError):
        GIMS._fn_contains([[huge], 1], {})
    with pytest.raises(psycopg.Error) as exc:
        _sql(conn, [[[huge], 1]])
    assert exc.value.sqlstate == "XPR01"
