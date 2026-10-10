"""demo/tests/test_picks_records.py — T-86: the pick engine over records that are not the demo's.

``picks/`` was moved out of the demo and made to read any table of JSON
records described to it (``picks/records.py``).  The demo's own suite proves
the move changed nothing for the demo; this file proves the description is
real: a different table, an OWNER partition (two owners' records in one
table), and a time series with other field names.  Every answer is held to
hand-written SQL over the same rows, and to the second engine.

The table is TEMPORARY, made inside a transaction that is always rolled back,
on the demo's writable connection: nothing outlives a test.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401  (the demo registers the engine's modules)
from demo.server import app as server_app  # noqa: E402
from demo.server import db  # noqa: E402
from picks import builder, env, group, legality, lookup, probes  # noqa: E402
from picks.pyrunner import group as pygroup  # noqa: E402
from picks.pyrunner import lookup as pylookup  # noqa: E402
from picks.pyrunner import shape as pyshape  # noqa: E402
from picks.pyrunner.rows import read_rows  # noqa: E402
from picks.records import Records  # noqa: E402

TABLE = "t86_records"
SOURCES = {"noun:Reading": "who, at, v, kind", "noun:Meter": "id, room"}

#: Two owners, "acme" and "other", in one table.  Readings are a time series:
#: ``at`` per ``who`` (not the demo's ``ts`` per ``sender_id``).
_ROWS = [
    # owner, collection, key, data
    ("acme", "noun:Reading", "r1", {"who": "m1", "at": "2026-01-05T00:30:00Z", "v": 2, "kind": "a"}),
    ("acme", "noun:Reading", "r2", {"who": "m1", "at": "2026-01-05T01:30:00Z", "v": 4, "kind": "a"}),
    ("acme", "noun:Reading", "r3", {"who": "m1", "at": "2026-01-06T00:00:00Z", "v": 4, "kind": "b"}),
    ("acme", "noun:Reading", "r4", {"who": "m2", "at": "2026-01-05T00:00:00Z", "v": 10, "kind": "b"}),
    # the same as r4 but for its time: "keep only changed" drops it (the record minus `at`)
    ("acme", "noun:Reading", "r5", {"who": "m2", "at": "2026-01-06T01:00:00Z", "v": 10, "kind": "b"}),
    ("acme", "noun:Meter", "k1", {"id": "m1", "room": "North"}),
    ("acme", "noun:Meter", "k2", {"id": "m2", "room": "South"}),
    # the other owner's rows, in the same table and collections — never read for acme
    ("other", "noun:Reading", "r1", {"who": "m1", "at": "2026-01-05T00:30:00Z", "v": 1000, "kind": "a"}),
    ("other", "noun:Reading", "r9", {"who": "m1", "at": "2026-01-07T00:00:00Z", "v": 7000, "kind": "a"}),
    ("other", "noun:Meter", "k1", {"id": "m1", "room": "Elsewhere"}),
]


def acme(**kw) -> Records:
    base = dict(table=TABLE, sources=SOURCES, partition=("owner", "acme"),
                series={"source": "noun:Reading", "time": "at", "member": "who"})
    base.update(kw)
    return Records(**base)


@pytest.fixture
def wconn():
    """The demo's connection, with a TEMPORARY table of two owners' records,
    always rolled back."""
    c = db.connect(application_name="autosql-demo-t86-records")
    try:
        c.execute(f"CREATE TEMPORARY TABLE {TABLE} (owner text, collection text, key text, data jsonb, "
                  "PRIMARY KEY (owner, collection, key))")
        for owner, coll, key, data in _ROWS:
            c.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s, %s::jsonb)", (owner, coll, key, json.dumps(data)))
        yield c
    finally:
        c.rollback()
        c.close()


def pick(**kw) -> dict:
    p = dict(legality.default_pick(acme()), computed=[], filter=None)
    p.update(kw)
    return p


def both(conn, p, records):
    """(the statement's rows, the second engine's rows) for one pick — given
    both in one spelling of its field slots, as the demo's run_pick gives them."""
    p = server_app.normalised_pick(p)
    built = builder.build(p, list(SOURCES[p["source"]].replace(" ", "").split(",")), records=records)
    sql = server_app.sql_pane(conn, built)
    py = pyshape.answer(read_rows(conn, p["source"], records), p, records)
    return built, sql, py


def hand(conn, sql, params=None):
    return conn.execute(sql, params or {}).fetchall()


# ═════════════════════════════════════════════════════════════════════════
# 1 · The description itself
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kw", [
    {"table": "t86_records; DROP TABLE x"},
    {"table": "a.b.c"},
    {"partition": ("owner = owner OR true --", "acme")},
    {"series": {"source": "noun:Reading", "time": "at'); --", "member": "who"}},
    {"series": {"source": "noun:Nope", "time": "at", "member": "who"}},
    {"fold": "gims"},                                   # a fold needs noun_of
    {"fold": "other", "noun_of": str},
])
def test_a_records_description_refuses_what_could_reach_statement_text(kw):
    with pytest.raises(ValueError):
        acme(**kw)


def test_the_partition_is_a_bound_parameter_never_text():
    params = {}
    where = acme(partition=("owner", "x'; DROP TABLE t86_records; --")).scope("r", params)
    assert where == "r.collection = %(collection)s AND r.owner = %(partition)s"
    assert params == {"partition": "x'; DROP TABLE t86_records; --"}


def test_a_fold_reaches_the_compiler_with_the_noun():
    r = acme(fold="gims", noun_of=lambda c: c.split(":", 1)[1])
    assert r.compile_kwargs("noun:Reading") == {"fold": "gims", "noun": "Reading"}
    # a key with a separator is read the way the fold serves it (compiler/compile.py, T-48);
    # a plain key reads the same either way
    folded = builder.build(pick(filter="$.sample_weight > 1"), ["who", "at", "v", "kind"], records=r)
    plain = builder.build(pick(filter="$.sample_weight > 1"), ["who", "at", "v", "kind"], records=acme())
    assert folded.sql != plain.sql
    same = builder.build(pick(filter='$.kind == "a"'), ["who", "at", "v", "kind"], records=r)
    assert same.sql == builder.build(pick(filter='$.kind == "a"'), ["who", "at", "v", "kind"], records=acme()).sql


# ═════════════════════════════════════════════════════════════════════════
# 2 · Only the owner asked for, in every statement and in the second engine
# ═════════════════════════════════════════════════════════════════════════

def test_rows_of_one_owner_both_engines_and_hand_sql(wconn):
    p = pick(filter="$.v >= 2", sort={"field": "v", "dir": "desc"})
    built, sql, py = both(wconn, p, acme())
    assert "owner = %(partition)s" in built.sql and built.params["partition"] == "acme"
    want = [k for (k,) in hand(wconn, f"SELECT key FROM {TABLE} WHERE owner = 'acme' AND collection = 'noun:Reading' "
                                      "AND (data->>'v')::numeric >= 2 ORDER BY (data->'v') DESC, key")]
    assert [r["key"] for r in sql["rows"]] == [r["key"] for r in py["rows"]] == want == ["r4", "r5", "r2", "r3", "r1"]


def test_one_number_of_one_owner(wconn):
    p = pick(aggregate={"fn": "sum", "field": "v"})
    _, sql, py = both(wconn, p, acme())
    (want,) = hand(wconn, f"SELECT sum((data->>'v')::numeric) FROM {TABLE} "
                          "WHERE owner = 'acme' AND collection = 'noun:Reading'")[0:1]
    assert Decimal(str(sql["rows"][0]["agg"])) == py["agg"] == Decimal(want[0]) == Decimal(30)


def test_per_day_over_this_series_time_field(wconn):
    p = pick(aggregate={"fn": "count", "field": None}, bucket="day")
    _, sql, py = both(wconn, p, acme())
    want = hand(wconn, f"SELECT to_char(date_trunc('day', (data->>'at')::timestamptz) AT TIME ZONE 'UTC', "
                       "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') b, count(*) FROM " + TABLE +
                       " WHERE owner = 'acme' AND collection = 'noun:Reading' GROUP BY 1 ORDER BY 1")
    got_sql = [(r["bucket"], int(r["agg"])) for r in sql["rows"]]
    got_py = [(r["bucket"], int(r["agg"])) for r in py["rows"]]
    assert got_sql == got_py == [(b, int(n)) for b, n in want] == [("2026-01-05T00:00:00Z", 3), ("2026-01-06T00:00:00Z", 2)]


def test_the_rolling_window_and_keep_changed_read_this_series(wconn):
    """Per ``who``, in ``at`` order: m1 is r1 (2), r2 (4), r3 (4); m2 is r4 (10), r5 (10)."""
    p = pick(window={"field": "v"}, sort={"field": "at", "dir": "asc"})
    _, sql, py = both(wconn, p, acme())
    rolling = {r["key"]: Decimal(str(r["rolling_avg"])) for r in sql["rows"]}
    assert rolling == {r["key"]: r["rolling_avg"] for r in py["rows"]}
    assert rolling == {"r1": Decimal(2), "r2": Decimal(3), "r3": Decimal("3.333333"), "r4": Decimal(10),
                       "r5": Decimal(10)}
    # keep only changed: the record minus `at` — r3 differs from r2 by kind and stays; r5 is r4
    # but for its time, so it goes
    p = pick(changed=True, sort={"field": "at", "dir": "asc"})
    _, sql, py = both(wconn, p, acme())
    assert [r["key"] for r in sql["rows"]] == [r["key"] for r in py["rows"]] == ["r4", "r1", "r2", "r3"]


def test_a_board_and_a_match_read_one_owner(wconn):
    r = acme()
    spec = {"source": "noun:Meter", "group": "id", "filter": None, "counts": [], "time": None,
            "measure": {"fn": "sum", "field": "v"}, "sort": None, "cap": None,
            "related": {"source": "noun:Reading", "key": "who", "parent_key": "id", "match": "string"}}
    sql = server_app.sql_pane(wconn, group.build(spec, r))
    py = pygroup.answer(read_rows(wconn, "noun:Meter", r), spec, read_rows(wconn, "noun:Reading", r))
    got = {row["grp"]: (int(row["rows"]), Decimal(str(row["measure"]))) for row in sql["rows"]}
    assert got == {row["grp"]: (row["rows"], row["measure"]) for row in py["rows"]}
    assert got == {"m1": (3, Decimal(10)), "m2": (2, Decimal(20))}       # never the other owner's 8000
    prof = server_app.sql_pane(wconn, group.build_profile(spec, r))["rows"][0]
    assert dict(prof) == pygroup.profile(read_rows(wconn, "noun:Meter", r), spec, read_rows(wconn, "noun:Reading", r))
    lk = {"source": "noun:Meter", "key": "id", "parent_key": "who", "match": "string",
          "columns": [{"name": "Room", "path": "room"}]}
    p = pick(computed=[{"name": "K", "expr": "$.who"}])
    built = lookup.build(p, ["who", "at", "v", "kind"], lk, r)
    rows = server_app.sql_pane(wconn, built)["rows"]
    pyrows = pylookup.answer(read_rows(wconn, "noun:Reading", r), p, read_rows(wconn, "noun:Meter", r), lk, r)["rows"]
    assert [(x["key"], x["Room"]) for x in rows] == [(x["key"], x["Room"]) for x in pyrows] == [
        ("r1", "North"), ("r2", "North"), ("r3", "North"), ("r4", "South"), ("r5", "South")]


def test_probes_ask_one_owner(wconn):
    """The other owner holds a number past the largest double; acme does not."""
    wconn.execute(f"INSERT INTO {TABLE} VALUES ('other', 'noun:Reading', 'huge', '{{\"who\":\"m1\",\"v\":1e400}}'::jsonb)")
    from picks.pyrunner import evaluate  # noqa: F401  (the evaluator is registered)
    ast = env.get("parser").parse("$.v > 1")
    assert probes.check(wconn, "noun:Reading", [ast], records=acme()) is not None
    with pytest.raises(probes.RuntimeRefusal):
        probes.check(wconn, "noun:Reading", [ast], records=acme(partition=("owner", "other")))


# ═════════════════════════════════════════════════════════════════════════
# 3 · The host's row provider, and a host that set nothing
# ═════════════════════════════════════════════════════════════════════════

def test_the_second_engine_reads_through_the_hosts_row_provider():
    asked = []

    def rows(conn, collection, owner):            # handed the owner since T-87
        asked.append((collection, owner))
        return [(k, json.dumps(d)) for o, c, k, d in _ROWS if o == owner and c == collection]

    r = acme(rows=rows)
    out = pyshape.answer(read_rows(None, "noun:Reading", r), pick(aggregate={"fn": "count", "field": None}), r)
    assert asked == [("noun:Reading", "acme")] and out["agg"] == 5      # no database at all


def test_an_engine_with_no_host_says_so_by_name(tmp_path):
    """Imported by a program that never called picks.env.use(), the engine
    refuses by name rather than guessing a compiler or a table."""
    import subprocess
    code = ("import sys; sys.path.insert(0, %r)\n"
            "try:\n    import picks.builder\nexcept RuntimeError as e:\n    print('REFUSED', e)\n"
            "from picks import env\n"
            "try:\n    env.records()\nexcept RuntimeError as e:\n    print('REFUSED', e)\n") % str(_REPO_ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path).stdout
    assert out.count("REFUSED") == 2 and "picks.env.use" in out and "set_default_records" in out
