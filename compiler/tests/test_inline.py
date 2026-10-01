"""T-52: the number checks written inline (T-44's C_both), held to the frozen compiler.

The full proof is spikes/T-44 (11,367 battery expressions with zero wrong numbers,
each case identical to the compiler before T-52, plus a direct differential of the
inline coercion against xpr.num on 3,216 targeted inputs). These tests are the standing
guard that keeps that true after the spike is history:

  * the boundary literal is THE SAME as the runtime's refusal boundary;
  * the rewritten families compute the same VALUE as the frozen compiler, row by row,
    over values chosen to reach every branch of the inline coercion (needs a database);
  * compile_predicate() is exactly the truthiness of compile_ast(), row by row;
  * the shapes that make it fast are present, so a later edit cannot quietly put the
    per-row function calls back.

Database tests: AUTOSQL_COMPILER_DSN, as in test_compiler.py.  They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_COMPILER_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is a live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_COMPILER_DSN to a Postgres with the runtime")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t52_expr", "demo/vendor/expr.py")
SHIPPING = _load("t52_shipping", "compiler/compile.py")
FROZEN = _load("t52_frozen", "spikes/T-1/proto/compile.py")

#: Every numeric family, plus the shapes the invented T-44 widget uses.
EXPRESSIONS = [
    "1 / 3", "1787169706037 * 1", "$.a + 1", "$.a - $.b", "- $.a", "$.a * 2", "$.a / $.b",
    "$.a % 3", "abs($.a)", "floor($.a)", "ceil($.a)", "round($.a, 1)", "number($.s)",
    "number($.a) + number($.b)", "coalesce($.a, 0) * 25", "coalesce($.a, 0) + coalesce($.b, 0) * 25",
    "if($.flag, $.a, 2) + 1", "length($.s) + 1", "count($.l) * 2", "sum($.l)", "min($.l) + 1",
    "$.a > 2", "$.a + 1 > $.b", "coalesce($.a, 0) + coalesce($.b, 0) * 25 > 195",
    "$.a < $.b", "$.s >= 1", "($.a + 1) == 6", "days_between($.d, $.e) + 0",
]

#: Values chosen to reach every branch of the inline coercion: JSON numbers in and beyond
#: range, -0, booleans, plain decimal strings, and every string that must fall through to
#: xpr.num (whitespace, exponent, full-width digits, junk), plus null and absent keys.
RECORDS = [
    {}, {"a": 5, "b": 2}, {"a": "7", "b": " 2 "}, {"a": "1e3", "b": "１２"}, {"a": True, "b": False},
    {"a": None, "b": 1}, {"a": "abc", "b": "-.5"}, {"a": 1.7976931348623157e308, "b": 2},
    {"a": -0.0, "b": 0}, {"a": "12.5", "b": "+3.", "l": [1, "2", " 3 ", None, "x"]},
    {"s": "12", "d": "2024-01-01", "e": "2024-03-01", "flag": True, "a": 1, "b": 3, "l": [1, 2]},
    {"a": "0.000000001", "b": "000123", "s": " 4 ", "flag": False},
]


def test_the_boundary_literal_is_the_runtimes():
    """xpr.f8 refuses above THIS literal; the inline check must switch at the same place,
    or the two would disagree about where the named refusal XPR01 starts."""
    src = (ROOT / "runtime" / "runtime.sql.in").read_text(encoding="utf-8")
    lits = set(re.findall(r"abs\(n\) > (\d+)::numeric", src))
    assert lits == {SHIPPING.DBL_MAX_LITERAL}


def test_compile_predicate_takes_compile_asts_arguments():
    assert (inspect.signature(SHIPPING.compile_predicate).parameters.keys()
            == inspect.signature(SHIPPING.compile_ast).parameters.keys())
    ast = EXPR.parse("$.a > 1")
    with pytest.raises(ValueError):
        SHIPPING.compile_predicate(ast, fold="nope")
    with pytest.raises(ValueError):
        SHIPPING.compile_predicate(ast, fold="gims")            # noun is required with it


@pytest.mark.parametrize("src", ["$.a + 1", "coalesce($.a, 0) + coalesce($.b, 0) * 25", "- $.a"])
def test_arithmetic_stays_float8_and_meets_jsonb_once(src):
    """The float8 channel: one xpr.j at the boundary, no jsonb round trip inside."""
    sql = SHIPPING.compile_ast(EXPR.parse(src)).sql
    assert sql.startswith("xpr.j(") and sql.count("xpr.j(") == 1 + sql.count("xpr.j((%(")
    assert "CASE jsonb_typeof(" in sql, "a field read should be coerced inline"


def test_an_ordering_between_numbers_is_native_and_the_rest_keep_xpr_ord():
    num = SHIPPING.compile_predicate(EXPR.parse("$.a + 1 > 195")).sql
    assert num.startswith("COALESCE((") and "xpr.ord(" not in num and "xpr.truthy(" not in num
    for src in ["$.a > $.b", '$.s > "x"', "$.a > 1"]:         # a bare field is not a number
        assert "xpr.ord(" in SHIPPING.compile_ast(EXPR.parse(src)).sql, src


def _value(cx, mod, src, rec):
    import psycopg
    c = mod.compile_ast(EXPR.parse(src))
    params = dict(c.params, ctx="{}", rec=json.dumps(rec))
    try:
        row = cx.execute("SELECT (" + c.sql + ")::text FROM (SELECT (%(rec)s)::jsonb AS data) t",
                         params).fetchone()
        return ("value", row[0])
    except psycopg.Error as exc:
        return ("raised", exc.sqlstate)


@needs_db
@pytest.mark.parametrize("src", EXPRESSIONS)
def test_the_rewritten_families_compute_what_the_frozen_compiler_computes(src):
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute("SET extra_float_digits = 1")
        for rec in RECORDS:
            assert _value(cx, SHIPPING, src, rec) == _value(cx, FROZEN, src, rec), (src, rec)


@needs_db
@pytest.mark.parametrize("src", EXPRESSIONS)
def test_compile_predicate_is_the_truthiness_of_compile_ast(src):
    import psycopg
    ast = EXPR.parse(src)
    pred = SHIPPING.compile_predicate(ast)
    val = SHIPPING.compile_ast(ast)
    with psycopg.connect(DSN, autocommit=True) as cx:
        for rec in RECORDS:
            got = []
            for sql, params in ((pred.sql, pred.params), ("xpr.truthy(" + val.sql + ")", val.params)):
                p = dict(params, ctx="{}", rec=json.dumps(rec))
                try:
                    got.append(cx.execute("SELECT " + sql + " FROM (SELECT (%(rec)s)::jsonb AS data) t",
                                          p).fetchone()[0])
                except psycopg.Error as exc:
                    got.append(exc.sqlstate)
            assert got[0] == got[1], (src, rec, got)
