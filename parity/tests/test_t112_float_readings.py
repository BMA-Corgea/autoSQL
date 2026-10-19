"""T-112: a stored number a double can't hold is shown exactly or refused in words, by both engines alike.

GIMS's language computes and compares in doubles on both engines. A stored number no double holds
(``picks/doubles.py``: the double nearest to it, written as Postgres writes a double, isn't the same number) had no
honest reading: the statement refused some (XPR01, 22003) and rounded the rest, the second engine read them all
silently -- ``1e-400`` as ``0.0`` (b-check, T-93 step 0), ``12345678901234567890.123456789`` as
``1.2345678901234567e+19`` (the ticket), and a computed double in Python's digits where Postgres writes others
(``1e22 * 10``). Now, on both engines and in GIMS's one-engine shape (the second engine alone):

* a stored value only SHOWN is shown exactly (-0 as 0), and a computed double in Postgres's digits;
* a stored value READ AS A DOUBLE (compared, computed with, taken as true) that a double would misread -- held only
  as 0 (small), or with more digits than a double holds (digits) -- refuses the pick in words naming its kind and
  its first row: the statement's probe member d, the second engine's own check;
* a number written in the expression that no double holds is refused before any SQL exists;
* a number at or past the largest double is left as it was beside the statement (member a or XPR01 refuses it, the
  language declines it in arithmetic: walkthrough step 13), and refused by the second engine too when the host says
  it answers alone (``Records.alone``, GIMS's SQLite mode), where two such numbers would compare as one infinity.

The tests without a database run the second engine alone on GIMS's text (its SQLite mode); the rest need a throwaway
Postgres (AUTOSQL_PARITY_DSN) and SKIP without one. The printer differential reads 200,000 random doubles and the
edge families (about 8 s).
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401  (the engine, registered)
from picks import builder, gate, probes, view  # noqa: E402
from picks.pyrunner import rows as pyrows, shape as pyshape  # noqa: E402
from picks.records import Records  # noqa: E402

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres")
T, TABLE = "noun:T", "t112v"
KEYS = ["l", "n", "o", "s", "x", "y"]

HELD = ["9007199254740991", "9007199254740992", "1e308", "5e-324", "0.30000000000000004", "44319635693286576",
        "9.999999999999999e22", "0.1", "12.5", "-0", "-0.0"]
NOT_HELD = {
    "9007199254740993": "digits", "1e-400": "small",
    "2.4703282292062328e-324": "digits", "0.12345678901234567": "digits", "0.123456789012345678": "digits",
    "12345678901234567890.123456789": "digits", "1.7976931348623156e+308": "digits", "1e23": "digits",
    "44319635693286580": "digits",
}
#: at or past the largest double ("large"): the statement's member a / XPR01 beside it; refused alone
PAST = ["1e309", "1.7976931348623157e308"]


def _records():
    return Records(table=TABLE, sources={T: ", ".join(KEYS)})


def _alone():
    """GIMS's SQLite mode: the second engine answers by itself (``Records.alone``). 6dd0eb8 had no such option: its
    engine always answered as if beside a statement, so there the plain description stands in."""
    try:
        return Records(table=TABLE, sources={T: ", ".join(KEYS)}, alone=True)
    except TypeError:
        return _records()


def _gims_text(stored: str) -> str:
    """GIMS's served text for one stored record (api/dashboard/picks_source.py, _python_rows + _dumps)."""
    def enc(v):
        if isinstance(v, dict):
            return "{" + ",".join(json.dumps(str(k)) + ":" + enc(x) for k, x in v.items()) + "}"
        if isinstance(v, list):
            return "[" + ",".join(enc(x) for x in v) + "]"
        if isinstance(v, Decimal):
            return str(v) if v.is_finite() else json.dumps(float(v))
        return json.dumps(v)
    return enc(json.loads(stored, parse_float=Decimal))


def _pick(**kw):
    p = {"source": T, "computed": [], "filter": None, "sort": None, "cap": None, "window": None,
         "changed": False, "bucket": "off", "aggregate": None}
    p.update(kw)
    return p


def _py(stored: dict, pick: dict, text=_gims_text, records=None):
    """The second engine by itself over GIMS's text (its SQLite shape): its rows, or the refusal it raised."""
    rows = [pyrows.source_row(T, k, text(s)) for k, s in sorted(stored.items())]
    try:
        return pyshape.answer(rows, pick, records or _records())["rows"]
    except ValueError as e:
        return e


def _kind(e):
    return getattr(e, "kind", None)


def _exact(text: str) -> Decimal:
    d = Decimal(text)
    return d.copy_abs() if d.is_zero() else d


# ── the second engine alone (GIMS's SQLite mode), no database ───────────

@pytest.mark.parametrize("lit", HELD + list(NOT_HELD) + PAST)
def test_a_stored_number_only_shown_is_shown_exactly(lit):
    got = _py({"a": '{"n": ' + lit + '}'}, _pick(computed=[{"name": "v", "expr": "$.n"}]))
    assert not isinstance(got, Exception), got
    v = got[0]["v"]
    assert v == _exact(lit) and not str(v).startswith("-0"), (lit, v)


@pytest.mark.parametrize("lit", list(NOT_HELD))
@pytest.mark.parametrize("expr_kind", ["filter > 0", "filter == 1", "filter truthy", "computed * 1"])
def test_a_stored_number_no_double_holds_read_as_a_double_is_refused_by_name(lit, expr_kind):
    stored = {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'}
    pick = {"filter > 0": _pick(filter="$.n > 0"), "filter == 1": _pick(filter="$.n == 1"),
            "filter truthy": _pick(filter="$.n"),
            "computed * 1": _pick(computed=[{"name": "w", "expr": "$.n * 1"}])}[expr_kind]
    got = _py(stored, pick)
    assert isinstance(got, ValueError) and _kind(got) == NOT_HELD[lit], (lit, expr_kind, got)
    assert got.row_key == "a" and '"a"' in str(got)


@pytest.mark.parametrize("lit", HELD)
def test_a_held_number_read_as_a_double_answers_as_its_exact_value_says(lit):
    stored = {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'}
    kept = [r["key"] for r in _py(stored, _pick(filter="$.n > 0"))]
    assert kept == sorted(k for k, s in stored.items() if Decimal(json.loads(s, parse_float=Decimal)["n"]) > 0)


def test_the_refusal_reads_every_row_not_only_the_filters():
    # the probe's scope: a row the filter leaves out still holds the number the filter reads
    got = _py({"a": '{"n": 1e-400}', "b": '{"n": 5}'}, _pick(filter="$.n > 1"))
    assert _kind(got) == "small" and got.row_key == "a"


def test_one_row_with_two_kinds_names_the_larger_first():
    # the probe's words take the same precedence: small, then digits (alone: large first)
    got = _py({"a": '{"n": 1e-400, "s": "9007199254740993"}'},
              _pick(filter="$.n > 0", computed=[{"name": "w", "expr": "$.s * 2"}]))
    assert _kind(got) == "small"
    pick = _pick(filter="$.n > 0", computed=[{"name": "w", "expr": "$.s * 2"}])
    assert _kind(_py({"a": '{"n": 1e-400, "s": "1e309"}'}, pick)) == "small"
    assert _kind(_py({"a": '{"n": 1e-400, "s": "1e309"}'}, pick, records=_alone())) == "large"


def test_a_computed_double_is_written_as_postgres_writes_it():
    got = _py({"a": '{"n": 1e22}'}, _pick(computed=[{"name": "w", "expr": "$.n * 10"}]))
    assert got[0]["w"] == Decimal("99999999999999990000000")          # Python's repr: 1e+23
    got = _py({"a": '{"n": 44319635693286576}'}, _pick(computed=[{"name": "w", "expr": "$.n * 1"}]))
    assert got[0]["w"] == Decimal("44319635693286576")                # repr: 4.431963569328658e+16


def test_numbers_stored_as_text():
    assert _kind(_py({"a": '{"s": "9007199254740993"}'}, _pick(computed=[{"name": "w", "expr": "$.s * 1"}]))) == "digits"
    assert _kind(_py({"a": '{"s": " 1e-400 "}'}, _pick(computed=[{"name": "w", "expr": "$.s * 1"}]))) == "small"
    assert _py({"a": '{"s": "12.5"}'}, _pick(computed=[{"name": "w", "expr": "$.s * 1"}]))[0]["w"] == Decimal("12.5")
    # an ID stored as text, compared as text, is never read as a number
    got = _py({"a": '{"s": "9007199254740993"}', "b": '{"s": "9007199254740992"}'},
              _pick(filter='$.s == "9007199254740993"'))
    assert not isinstance(got, Exception) and [r["key"] for r in got] == ["a"], got


def test_numbers_nested_in_lists_and_objects():
    stored = {"a": '{"l": [0.12345678901234567, 1], "o": {"x": 1e-400}}'}
    got = _py(stored, _pick(computed=[{"name": "v", "expr": "$.l"}, {"name": "u", "expr": "$.o"}]))
    assert got[0]["v"] == [Decimal("0.12345678901234567"), 1] and got[0]["u"] == {"x": Decimal("1E-400")}
    assert _kind(_py(stored, _pick(filter="$.l[0] > 0"))) == "digits"
    assert _kind(_py(stored, _pick(computed=[{"name": "w", "expr": "max($.l)"}]))) == "digits"
    assert _kind(_py(stored, _pick(filter="$.o.x > 0"))) == "small"
    # passed through coalesce / if: shown, not read
    got = _py(stored, _pick(computed=[{"name": "v", "expr": "coalesce($.l[0], 0)"}]))
    assert got[0]["v"] == Decimal("0.12345678901234567")


def test_a_sort_and_a_summary_by_the_column_read_the_exact_value():
    stored = {"a": '{"n": 0.12345678901234566}', "b": '{"n": 0.12345678901234567}', "c": '{"n": 1}'}
    got = _py(stored, _pick(computed=[{"name": "v", "expr": "$.n"}], sort={"field": "v", "dir": "desc"}))
    assert [r["key"] for r in got] == ["c", "b", "a"]             # the double ties a and b (and the key puts a first)
    got = _py({"a": '{"n": 12345678901234567890.123456789}', "b": '{"n": 1}'},
              _pick(computed=[{"name": "v", "expr": "$.n"}], aggregate={"fn": "sum", "field": "v"}))
    assert got[0]["agg"] == Decimal("12345678901234567891.123457")


def test_the_demos_text_reads_the_same_as_gims():
    # jsonb writes every digit: the demo hands 1e309 as a 310-digit integer, 1e-400 as a 401-digit fraction
    for lit, k, rec in (("1e309", "large", _alone()), ("1e-400", "small", None),
                        ("12345678901234567890.123456789", "digits", None)):
        positional = {"a": '{"n": ' + format(Decimal(lit), "f") + '}'}
        assert _kind(_py(positional, _pick(filter="$.n > 0"), text=lambda s: s, records=rec)) == k
        assert _py(positional, _pick(computed=[{"name": "v", "expr": "$.n"}]), text=lambda s: s)[0]["v"] == Decimal(lit)


# ── at or past the largest double ───────────────────────────────────────

@pytest.mark.parametrize("lit", PAST)
def test_beside_the_statement_a_number_past_the_largest_double_is_left_to_the_language(lit):
    # the demo's two-pane pane (no option): as before T-112 -- the statement refuses first (member a, XPR01) and the
    # language declines the number in arithmetic (walkthrough step 13: no value), so this engine answers
    stored = {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'}
    for pick in (_pick(filter="$.n > 0"), _pick(filter="$.n == 1"), _pick(filter="$.n"),
                 _pick(computed=[{"name": "w", "expr": "$.n * 1"}])):
        got = _py(stored, pick)
        assert not isinstance(got, Exception), (lit, pick, got)
    if lit == "1e309":
        assert _py(stored, _pick(computed=[{"name": "w", "expr": "$.n * 1"}]))[0]["w"] is None


#: the foreman's vectors (GIMS's SQLite mode, the engine by itself): stored rows, the pick, the exact answer's keys
ALONE = {
    "1e309 == 1e310": ({"a": '{"x": 1e309, "y": 1e310}'}, _pick(filter="$.x == $.y"), []),
    "1e309 < 1e310": ({"a": '{"x": 1e309, "y": 1e310}'}, _pick(filter="$.x < $.y"), ["a"]),
    "sort by a column holding 1e309 and 1e310": (
        {"c": '{"n": 1e309}', "d": '{"n": 1e310}'},
        _pick(computed=[{"name": "v", "expr": "$.n"}], sort={"field": "v", "dir": "desc"}), ["d", "c"]),
    "-1e309 < 1e309 (the control)": ({"a": '{"x": -1e309, "y": 1e309}'}, _pick(filter="$.x < $.y"), ["a"]),
}


@pytest.mark.parametrize("vector", list(ALONE))
def test_alone_a_number_past_the_largest_double_is_never_a_wrong_answer(vector):
    # by itself, the engine reads exactly or refuses in words: the control's infinities happen to answer right
    stored, pick, truth = ALONE[vector]
    got = _py(stored, pick, records=_alone())
    if isinstance(got, Exception):
        assert _kind(got) == "large", (vector, got)
    else:
        assert [r["key"] for r in got] == truth, (vector, [r["key"] for r in got])


@pytest.mark.parametrize("vector", list(ALONE))
def test_alone_such_a_number_is_refused_by_the_rule_not_by_the_outcome(vector):
    stored, pick, _truth = ALONE[vector]
    got = _py(stored, pick, records=_alone())
    assert isinstance(got, ValueError) and _kind(got) == "large", (vector, got)
    assert got.row_key == sorted(stored)[0] and "out-of-range magnitude" in str(got)


@pytest.mark.parametrize("vector", list(ALONE))
def test_beside_the_statement_the_same_vectors_are_not_refused(vector):
    stored, pick, _truth = ALONE[vector]
    got = _py(stored, pick)
    assert not isinstance(got, Exception), (vector, got)


# ── a number written in the expression ──────────────────────────────────

@pytest.mark.parametrize("src", ["$.n == 9007199254740993", "$.n > 0.12345678901234567", "$.n > 1e-400",
                                 "$.n * 12345678901234567890.123456789"])
def test_a_number_written_in_the_expression_that_no_double_holds_is_refused_before_any_sql(src):
    with pytest.raises(gate.Refused):
        builder.build(_pick(filter=src), KEYS, records=_records())


def test_a_condition_value_no_double_holds_is_refused_in_words():
    with pytest.raises(view.ViewError) as e:
        view.number_literal(9007199254740993)
    assert str(e.value) == "That number has more digits than can be compared exactly."
    assert view.number_literal(9007199254740992) == "9007199254740992"
    assert view.number_literal(0.1) == "0.1"
    assert view.number_literal(1e23) == "9.999999999999999e+22"     # the double the request already holds


# ── the statement, and both engines, on the throwaway ───────────────────

@pytest.fixture(scope="module")
def conn():
    import psycopg

    import this_runtime
    with psycopg.connect(DSN, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
        this_runtime.install(cx)
    c = psycopg.connect(DSN)
    c.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    yield c
    c.rollback()
    c.close()


def _put(conn, stored: dict):
    conn.execute(f"DELETE FROM {TABLE}")
    for k, s in stored.items():
        conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, s))


def _sql(conn, pick: dict):
    """The statement alone, as GIMS's Postgres mode runs it: the probes (the filter a truth), then the statement."""
    from picks import env
    p = env.get("parser")
    exprs = [p.parse(c["expr"]) for c in pick.get("computed") or []]
    truths = [p.parse(pick["filter"])] if pick.get("filter") else []
    try:
        with conn.transaction():
            probes.check(conn, T, exprs, truth_roots=truths, records=_records())
    except probes.RuntimeRefusal as e:
        return e
    built = builder.build(pick, KEYS, records=_records())
    with conn.transaction():
        cur = conn.cursor()
        import psycopg.types.json
        psycopg.types.json.set_json_loads(lambda s: json.loads(s, parse_float=Decimal), context=cur)
        cur.execute(built.sql, built.params)
        names = [d.name for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def _member_kind(e):
    if isinstance(e, probes.NumberRefusal):
        return "d", e.kind
    if isinstance(e, probes.RuntimeRefusal):
        return e.member, "large"
    return None


@needs_db
@pytest.mark.parametrize("lit", list(NOT_HELD))
def test_the_statement_alone_refuses_what_the_second_engine_refuses(conn, lit):
    stored = {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'}
    _put(conn, stored)
    for pick in (_pick(filter="$.n > 0"), _pick(filter="$.n == 1"), _pick(filter="$.n"),
                 _pick(computed=[{"name": "w", "expr": "$.n * 1"}])):
        got = _sql(conn, pick)
        member, k = _member_kind(got) or (None, None)
        assert k == NOT_HELD[lit], (lit, pick, got)
        assert member == "d" or (member == "a" and k == "large"), (lit, member)
        assert got.row_key == "a"
        py = _py(stored, pick, text=lambda s: s)
        assert _kind(py) == k, (lit, pick, py)


@needs_db
@pytest.mark.parametrize("lit", HELD)
def test_held_numbers_answer_on_both_engines_alike(conn, lit):
    stored = {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'}
    _put(conn, stored)
    demo_rows = dict(conn.execute(f"SELECT key, data::text FROM {TABLE}").fetchall())
    for pick, col in ((_pick(filter="$.n > 0"), "key"), (_pick(computed=[{"name": "v", "expr": "$.n"}]), "v"),
                      (_pick(computed=[{"name": "w", "expr": "$.n * 1"}]), "w")):
        sql = _sql(conn, pick)
        py = _py(demo_rows, pick, text=lambda s: s)
        assert [r["key"] for r in sql] == [r["key"] for r in py], (lit, pick)
        if col != "key":
            assert [Decimal(r[col]) for r in sql] == [Decimal(r[col]) for r in py], (lit, pick, sql, py)


@needs_db
@pytest.mark.parametrize("lit", PAST)
def test_the_statement_leaves_a_number_past_the_largest_double_to_member_a(conn, lit):
    _put(conn, {"a": '{"n": ' + lit + '}', "b": '{"n": 2}'})
    from picks import env
    parse = env.get("parser").parse
    for exprs, truths in (([], [parse("$.n > 0")]), ([parse("$.n * 1")], []), ([], [parse("$.n == 1")])):
        with conn.transaction():
            out = probes.run_probes(conn, T, probes.build_probes(exprs, truth_roots=truths, records=_records()))
        fired = {o.probe.member: o.fired for o in out}
        assert fired.get("d") is False, (lit, fired)
        if "a" in fired:
            assert fired["a"] is True and [o.row_key for o in out if o.probe.member == "a"] == ["a"], (lit, fired)


@needs_db
def test_the_probes_held_test_and_the_second_engines_agree_on_every_value(conn):
    """One rule, two statements of it: the probe's own SQL predicate against pyrunner's check, value for value."""
    from picks.pyrunner import exact
    rnd = random.Random(112)
    corpus = list(HELD) + list(NOT_HELD)
    for _ in range(4000):
        f = struct.unpack("<d", struct.pack("<q", rnd.getrandbits(63)))[0]
        if math.isfinite(f):
            corpus.append(repr(f))
    corpus += [f"{rnd.randrange(10**15, 10**18)}e{rnd.randrange(-340, 300)}" for _ in range(800)]
    corpus += [str(rnd.randrange(2**53 - 50, 2**60)) for _ in range(200)]
    texts = [json.dumps(c) for c in corpus]
    fire = probes._d_forms("v.j", "coerced", probes._fires_sql)
    for form in ("number", "text"):
        vals = corpus if form == "number" else texts
        cur = conn.execute(f"SELECT {fire} FROM unnest(%s::jsonb[]) WITH ORDINALITY AS v(j, o) ORDER BY o", (vals,))
        sql_says = [r[0] for r in cur.fetchall()]
        for c, said in zip(corpus, sql_says):
            py_says = exact._value_kind(Decimal(c) if form == "number" else c, exact.COERCED) is not None
            assert said is py_says, (form, c, said, py_says)


@needs_db
def test_the_printer_emulation_is_postgres_own():
    """The live float8out against picks.doubles.pg_shortest, on 200,000 random doubles, every power of two and of
    ten, 20,000 integers in [2^53, 2^64), and the midpoint cases."""
    import psycopg
    from picks import doubles
    rnd = random.Random(1120)
    vals = []
    while len(vals) < 200_000:
        f = struct.unpack("<d", struct.pack("<q", rnd.getrandbits(63)))[0] * (1 if rnd.random() < .5 else -1)
        if math.isfinite(f):
            vals.append(f)
    vals += [2.0 ** e for e in range(-1074, 1024)] + [float(f"1e{e}") for e in range(-323, 309)]
    vals += [float(rnd.randrange(2**53, 2**64)) for _ in range(20_000)]
    vals += [1e23, 4.4319635693286576e16, 5e-324, 1.7976931348623157e308, -0.0]
    with psycopg.connect(DSN) as c:
        c.execute("SET extra_float_digits = 1")
        bad = []
        for i in range(0, len(vals), 50_000):
            chunk = vals[i:i + 50_000]
            pg = [r[0] for r in c.execute("SELECT x::text FROM unnest(%s::float8[]) WITH ORDINALITY AS t(x, o) "
                                          "ORDER BY o", (chunk,)).fetchall()]
            bad += [(v, doubles.pg_shortest(v), p) for v, p in zip(chunk, pg)
                    if Decimal(doubles.pg_shortest(v)) != Decimal(p) or (p.startswith("-") != doubles.pg_shortest(v).startswith("-"))]
    assert not bad, bad[:5]


# ── the demo: its two-pane screen and its dashboard, on a scratch copy of its rows ──
SCRATCH = "t112_demo_scratch"


@pytest.fixture(scope="module")
def demo():
    if not DSN:
        pytest.skip("set AUTOSQL_PARITY_DSN to a throwaway Postgres")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    from demo.server import app as server_app, dashboard, db, settings
    from fastapi.testclient import TestClient

    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
        cx.execute(f"CREATE DATABASE {SCRATCH}")
    dsn = make_conninfo(**{**conninfo_to_dict(DSN), "dbname": SCRATCH})
    with psycopg.connect(dsn, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(dsn) as cx:
        load.install_schema(cx)
        load.copy_rows(cx)
        cx.commit()
    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    real = db.connect
    db.connect = lambda *, application_name=None, autocommit=False: psycopg.connect(dsn, autocommit=autocommit,
                                                                                    options=opts)
    dashboard._CACHE.clear()
    try:
        yield {"client": TestClient(server_app.app, raise_server_exceptions=False), "dsn": dsn}
    finally:
        db.connect = real
        dashboard._CACHE.clear()
        with psycopg.connect(DSN, autocommit=True) as cx:
            cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def _beat(demo, load_lit):
    """One extra Heartbeat whose payload's load is stored exactly as written (or none)."""
    import psycopg
    from demo.server import dashboard
    with psycopg.connect(demo["dsn"], autocommit=True) as cx:
        cx.execute("DELETE FROM demo.records WHERE key = 'hb-zz-t112'")
        if load_lit is not None:
            cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', 'hb-zz-t112', "
                       "('{\"ts\": \"2026-08-14T00:00:00Z\", \"status\": \"ok\", \"sender_id\": \"hb-01\", "
                       "\"payload\": {\"load\": ' || %s || ', \"note\": \"t112\"}}')::jsonb)", (load_lit,))
    dashboard._CACHE.clear()


@pytest.fixture()
def beat(demo):
    yield lambda lit: _beat(demo, lit)
    _beat(demo, None)


def _two_pane(demo, pick):
    from picks import legality
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat"})
    p.update(pick)
    return demo["client"].post("/api/pick", json={"pick": p})


@needs_db
@pytest.mark.parametrize("lit, words", [
    ("1e-400", "One of these values is too small to compute with, so this can't be answered honestly."),
    ("12345678901234567890.123456789", "One of these values has more digits than can be compared exactly, so this "
                                       "can't be answered honestly. Store long numbers such as IDs as text."),
])
def test_the_two_pane_screen_refuses_on_both_panes_in_its_own_words(demo, beat, lit, words):
    beat(lit)
    r = _two_pane(demo, {"filter": "$.payload.load > 0", "cap": 5})
    assert r.status_code == 422, (r.status_code, r.text[:200])
    body = r.json()
    rf = body["refusal"]
    assert (rf["layer"], rf["member"], rf["row_key"]) == (2, "d", "hb-zz-t112") and rf["body"] == words
    assert "could not read the value either" in json.dumps(body["panes"]["python"])


@needs_db
@pytest.mark.parametrize("lit", ["12345678901234567890.123456789", "1e-400"])
def test_the_two_pane_screen_shows_a_stored_value_exactly_on_both_panes(demo, beat, lit):
    beat(lit)
    r = _two_pane(demo, {"computed": [{"name": "v", "expr": "$.payload.load"}], "filter": '$.payload.note == "t112"'})
    assert r.status_code == 200 and r.json()["verdict"] == "agree", r.text[:300]
    assert r.json()["page"]["total"] == 1


@needs_db
def test_the_two_pane_screen_agrees_on_a_computed_double_both_printers_wrote_apart(demo, beat):
    beat("1e22")
    r = _two_pane(demo, {"computed": [{"name": "w", "expr": "$.payload.load * 10"}], "filter": '$.payload.note == "t112"'})
    assert r.status_code == 200 and r.json()["verdict"] == "agree", r.text[:300]


@needs_db
def test_the_dashboard_says_it_plainly_and_admin_gets_the_hint(demo, beat):
    beat("12345678901234567890.123456789")
    v = {"dataset": "heartbeats", "columns": ["sender_id", "payload.load"], "sort": None, "show": None,
         "summary": None, "conditions": [{"field": "payload.load", "op": "gt", "value": 0}]}
    a = demo["client"].post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True}).json()
    assert a["kind"] == "refused", a
    assert a["message"] == "One of these values has more digits than can be compared exactly, so this can't be " \
                           "answered honestly."
    assert "Store long numbers such as IDs as text." in json.dumps(a.get("admin") or {})
    everyone = demo["client"].post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": False}).json()
    assert "Store long numbers" not in json.dumps(everyone)
