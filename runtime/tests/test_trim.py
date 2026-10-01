"""T-66: the runtime trims exactly what Python's str.strip() trims, and never the letter v.

PostgreSQL E-strings have no \\v escape ("any other character following a backslash is taken
literally"), so E'\\v' is the LETTER v. From T-1 to T-66 the runtime trimmed with
E' \\t\\n\\r\\f\\v', which stripped leading and trailing v's: xpr.num('"v2"') was 2 where GIMS's
number() gives None, and "v2024-02-29" was a date (the T-60/61/63 refute-review, F60-1).

Every case is held to GIMS's own Python: demo/vendor/expr.py, byte-identical to GIMS's
core/dashboard/expr.py. _to_num is the oracle for numbers and _parse_date_ms for dates. Values
come from a ROW SOURCE, so nothing is folded at plan time.

Database tests: AUTOSQL_RUNTIME_DSN, as in test_runtime.py.  They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is the live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")

_spec = importlib.util.spec_from_file_location("t66_gims_expr", ROOT / "demo" / "vendor" / "expr.py")
GIMS = importlib.util.module_from_spec(_spec)
sys.modules["t66_gims_expr"] = GIMS
_spec.loader.exec_module(GIMS)

#: Python's whitespace: every code point str.isspace() accepts.
PY_WS = [c for c in map(chr, range(0x110000)) if c.isspace()]

#: The letter v wherever the old trim stripped it, and its neighbours as controls.
V_NUMBERS = ["v2", "2v", "vv3.5v", "12v", "v12", "v", "vv", "v 2", "2 v", "\vv2\v", "V2", "x2", "2"]
V_DATES = ["v2024-02-29", "2024-02-29v", "v2024-02-29T10:00:00Z", "vv2024-02-29vv", "\vv2024-02-29",
           "2024-02-29"]


def _rows(conn, expr, values):
    q = f"SELECT {expr} FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS t(x, n) ORDER BY n"
    return [r[0] for r in conn.execute(q, (json.dumps(values),)).fetchall()]


@pytest.fixture(scope="module")
def conn():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as cx:
        yield cx


def test_python_strips_29_code_points_the_vertical_tab_among_them_and_no_letter():
    assert len(PY_WS) == 29 and "\x0b" in PY_WS and not any(c.isalpha() for c in PY_WS)


@needs_db
def test_no_letter_is_trimmed_from_a_number(conn):
    got = _rows(conn, "xpr.num(x)", V_NUMBERS)
    want = [GIMS._to_num(s) for s in V_NUMBERS]
    assert got == want, [c for c in zip(V_NUMBERS, got, want) if c[1] != c[2]]


@needs_db
def test_every_python_whitespace_character_is_trimmed_from_a_number(conn):
    values = [w + "2" + w for w in PY_WS] + [w + "2.5" for w in PY_WS] + ["7" + w for w in PY_WS]
    want = [GIMS._to_num(s) for s in values]
    assert None not in want
    assert _rows(conn, "xpr.num(x)", values) == want


@needs_db
def test_no_letter_is_trimmed_from_a_date(conn):
    want = [GIMS._parse_date_ms(s) for s in V_DATES]
    got_ms = _rows(conn, "xpr.pdate_ms(x)", V_DATES)
    got_only = _rows(conn, "xpr.pdate_only(x)", V_DATES)
    assert got_ms == [w and w[0] for w in want], [c for c in zip(V_DATES, got_ms, want) if c[1] != (c[2] and c[2][0])]
    assert got_only == [w and w[1] for w in want], list(zip(V_DATES, got_only))


@needs_db
def test_every_python_whitespace_character_is_trimmed_from_a_date(conn):
    values = [w + "2024-02-29" + w for w in PY_WS] + [w + "2024-02-29T10:00:00Z" for w in PY_WS]
    want = [GIMS._parse_date_ms(s) for s in values]
    assert None not in want
    assert _rows(conn, "xpr.pdate_ms(x)", values) == [w[0] for w in want]
    assert _rows(conn, "xpr.pdate_only(x)", values) == [w[1] for w in want]


def test_the_template_uses_no_escape_postgres_lacks():
    """Postgres E-strings know \\b \\f \\n \\r \\t, octal digits, \\x, \\u and \\U; any other
    backslash pair is the bare character, which is how \\v became the letter v. This guards
    every E-string in the template, not just the three T-66 fixed."""
    src = (ROOT / "runtime" / "runtime.sql.in").read_text(encoding="utf-8")
    bad = [(lit, m.group(0)) for lit in re.findall(r"E'((?:[^']|'')*)'", src)
           for m in re.finditer(r"\\(.)", lit) if m.group(1) not in "bfnrtxuU01234567\\'"]
    assert not bad, bad
