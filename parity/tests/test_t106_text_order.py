"""T-106: text in code-point order wherever the generated SQL orders it, on ANY collation (GA-74).

Found by asql-b-check: on a glibc/ICU `en_US` Postgres the statement ordered text by the database's collation
(`a, b, B`) while the second engine orders code points (`B, a, b`). Every check here before ran on postgres:16-alpine,
whose musl collates by code point, so nothing could see it. This file runs the class on BOTH a locale-collated
database (AUTOSQL_LOCALE_DSN: postgres:16, `--locale=en_US.utf8`) and the alpine one (AUTOSQL_PARITY_DSN), with rows
built so the two orders differ (`a`/`B`/`b`, `_x`/`X`, `emile`/`Émile`, keys `k-a`/`K-b`, `big1`/`Big2`):
the sort (asc, desc, with a cap, by a computed column), the key order, the series window, a lookup's matches, a
board by group and by count, the probe's first offending row, and the setup's value list and keys. Each answer is
the second engine's, and the main ones are also the order written out here by hand. SKIPS a database without a DSN.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DSNS = [pytest.param(os.environ.get("AUTOSQL_LOCALE_DSN"), id="en_US"),
        pytest.param(os.environ.get("AUTOSQL_PARITY_DSN"), id="alpine-C")]
TABLE = "t106"
T, P = "noun:Thing", "noun:Peer"
_TS = "2026-01-01T00:00:00Z"

THINGS = {
    # key: data -- the keys and the names differ between code-point order and en_US's
    "k-a": {"name": "a", "who": "s1", "ts": _TS, "n": 1, "peer": "p", "tag2": "b"},
    "K-b": {"name": "B", "who": "s1", "ts": _TS, "n": 10, "peer": "p", "tag2": "B"},
    "k-c": {"name": "b", "who": "s1", "ts": _TS, "n": 100, "tag2": "a"},
    "_k": {"name": "_x", "who": "s1", "ts": "2026-01-02T00:00:00Z", "n": 1000},
    "Z1": {"name": "X", "who": "s2", "ts": _TS, "n": 2},
    "e1": {"name": "emile", "who": "s2", "ts": "2026-01-02T00:00:00Z", "n": 3},
    "e2": {"name": "Émile", "who": "s2", "ts": "2026-01-03T00:00:00Z", "n": 4},
    "a2": {"name": "a", "who": "s2", "ts": "2026-01-04T00:00:00Z", "n": 5},
    "num": {"name": 5, "who": "s3", "ts": _TS, "n": 6},
    "nul": {"name": None, "who": "s3", "ts": "2026-01-02T00:00:00Z", "n": 7},
    "abs": {"who": "s3", "ts": "2026-01-03T00:00:00Z", "n": 8},
    "big1": {"who": "s4", "ts": _TS, "n": 9, "big": 1e300},
    "Big2": {"who": "s4", "ts": "2026-01-02T00:00:00Z", "n": 11, "big": 1e300},
    "t-a": {"name": "tie", "who": "s5", "ts": _TS, "n": 12, "arr": ["b"]},       # a tie whose keys order apart
    "T-b": {"name": "tie", "who": "s5", "ts": _TS, "n": 13, "arr": ["B"]},
    "u-a": {"who": "s6", "ts": _TS, "n": 14},     # two identical records at one time: "changed" keeps the first
    "U-b": {"who": "s6", "ts": _TS, "n": 14},
}
for _d in THINGS.values():                       # the series' member under both spellings the builder knows
    _d["sender_id"] = _d["who"]
PEERS = {"m-a": {"peer": "p", "tag": "A"}, "M-b": {"peer": "p", "tag": "B"}}

#: By hand: jsonb's type order (Null < String < Number), strings in code points (B < X < _ < a < b < e < É),
#: ties by key in code points (a2 < k-a, T-b < t-a), absent values last (keys in code points: Big2 < U-b < abs < ...).
NAME_ASC = ["nul", "K-b", "Z1", "_k", "a2", "k-a", "k-c", "e1", "T-b", "t-a", "e2", "num",
            "Big2", "U-b", "abs", "big1", "u-a"]


def _cp(xs):
    return sorted(xs, key=lambda s: s.encode("utf-8"))


@pytest.fixture(scope="module", params=DSNS)
def world(request):
    dsn = request.param
    if not dsn:
        pytest.skip("set AUTOSQL_LOCALE_DSN / AUTOSQL_PARITY_DSN to throwaway Postgres databases")
    import psycopg

    import demo.picks_host  # noqa: F401
    import this_runtime
    from picks.records import Records

    with psycopg.connect(dsn, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
        this_runtime.install(cx)
    conn = psycopg.connect(dsn)
    collate = conn.execute("SELECT datcollate FROM pg_database WHERE datname = current_database()").fetchone()[0]
    conn.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    with conn.cursor() as cur:
        for coll, rows in ((T, THINGS), (P, PEERS)):
            cur.executemany(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)",
                            [(coll, k, json.dumps(d)) for k, d in rows.items()])
    keys = sorted({k for d in THINGS.values() for k in d})
    yield conn, _records("who"), keys, collate
    conn.rollback()
    conn.close()


def _records(member):
    from picks.records import Records
    keys = sorted({k for d in THINGS.values() for k in d})
    return Records(table=TABLE, sources={T: ", ".join(keys), P: "peer, tag"},
                   series={"source": T, "time": "ts", "member": member})


def _pick(**kw):
    p = {"source": T, "computed": [], "filter": None, "sort": None, "cap": None, "window": None,
         "changed": False, "bucket": "off"}
    p.update(kw)
    return p


def _both(world, pick):
    from picks import builder
    from picks.pyrunner import shape as pyshape
    from picks.pyrunner.rows import read_rows
    conn, records, keys, _c = world
    built = builder.build(pick, keys, records=records)
    cur = conn.execute(built.sql, built.params)
    names = [d.name for d in cur.description]
    sql = [dict(zip(names, r)) for r in cur.fetchall()]
    py = pyshape.answer(read_rows(conn, T, records), pick, records)["rows"]
    return sql, py


def _keys(rows):
    return [r["key"] for r in rows]


def test_the_database_collates_as_named(world):
    conn, _r, _k, collate = world
    order = conn.execute("SELECT array_agg(x ORDER BY x) FROM unnest(ARRAY['a', 'b', 'B']) x").fetchone()[0]
    assert order == (["B", "a", "b"] if collate in ("C", "POSIX") else ["a", "b", "B"]), (collate, order)


def test_rows_sorted_by_text_are_in_code_points(world):
    sql, py = _both(world, _pick(sort={"field": "$.name", "dir": "asc"}))
    assert _keys(sql) == _keys(py) == NAME_ASC
    sql, py = _both(world, _pick(sort={"field": "$.name", "dir": "desc"}, cap=6))
    want = ["num", "e2", "T-b", "t-a", "e1", "k-c"]     # present values inverted, ties still by key ascending
    assert _keys(sql) == _keys(py) == want


def test_rows_with_no_sort_are_in_key_code_points(world):
    sql, py = _both(world, _pick())
    assert _keys(sql) == _keys(py) == _cp(THINGS)


def test_a_computed_column_sort_is_in_code_points(world):
    sql, py = _both(world, _pick(computed=[{"name": "nm", "expr": "$.name"}], sort={"field": "nm", "dir": "asc"}))
    assert _keys(sql) == _keys(py)
    assert [k for k in _keys(sql) if THINGS[k].get("name") is not None and not isinstance(THINGS[k]["name"], int)] == \
        ["K-b", "Z1", "_k", "a2", "k-a", "k-c", "e1", "T-b", "t-a", "e2"]


def test_the_series_window_orders_ties_by_key_code_points(world):
    """Three rows of one sender at the same time: the rolling average's frame follows the key order."""
    from decimal import Decimal
    sql, py = _both(world, _pick(window={"field": "$.n"}))
    got = {r["key"]: Decimal(str(r["rolling_avg"])) for r in sql}
    assert got == {r["key"]: Decimal(str(r["rolling_avg"])) for r in py}
    assert got["K-b"] == Decimal(10) and got["k-a"] == Decimal("5.5")   # K-b first, then k-a (code points)


def test_a_lookups_matches_are_in_key_code_points(world):
    from picks import lookup
    from picks.pyrunner import lookup as pylookup
    from picks.pyrunner.rows import read_rows
    conn, records, keys, _c = world
    lk = {"source": P, "key": "peer", "parent_key": "peer", "match": "string", "columns": [{"name": "Mt", "path": "tag"}]}
    p = _pick(filter='$.peer == "p"')
    built = lookup.build(p, keys, lk, records)
    cur = conn.execute(built.sql, built.params)
    names = [d.name for d in cur.description]
    sql = [dict(zip(names, r)) for r in cur.fetchall()]
    py = pylookup.answer(read_rows(conn, T, records), p, read_rows(conn, P, records), lk, records)["rows"]
    assert [(r["key"], r["Mt"]) for r in sql] == [(r["key"], r["Mt"]) for r in py] == [
        ("K-b", "B"), ("K-b", "A"), ("k-a", "B"), ("k-a", "A")]


def _board(world, sort=None):
    from picks import group
    from picks.pyrunner import group as pygroup
    from picks.pyrunner.rows import read_rows
    conn, records, _k, _c = world
    spec = {"source": T, "group": "name", "filter": None, "counts": [], "time": None, "measure": None,
            "sort": sort, "cap": None}
    built = group.build(spec, records)
    cur = conn.execute(built.sql, built.params)
    names = [d.name for d in cur.description]
    sql = [dict(zip(names, r)) for r in cur.fetchall()]
    py = pygroup.answer(read_rows(conn, T, records), spec)["rows"]
    return [(r["grp"], int(r["rows"])) for r in sql], [(r["grp"], int(r["rows"])) for r in py]


def test_a_board_by_group_is_in_code_points(world):
    sql, py = _board(world)
    assert sql == py
    assert [g for g, _n in sql if isinstance(g, str)] == ["B", "X", "_x", "a", "b", "emile", "tie", "Émile"]


def test_a_board_by_count_breaks_ties_by_group_code_points(world):
    sql, py = _board(world, {"column": "rows", "dir": "desc"})
    assert sql == py
    # the blank group (JSON null and absent: 4 rows) leads, then "a" (2); the ones break ties in §7.4's order
    assert sql[:3] == [(None, 6), ("a", 2), ("tie", 2)] and [g for g, n in sql if n == 1 and isinstance(g, str)][:3] == ["B", "X", "_x"]
    assert sql[-1] == (5, 1)                    # a number after every string (the tie-break that crashed Python)


def test_the_probes_first_offending_row_is_by_key_code_points(world):
    from picks import env, probes
    conn, records, _k, _c = world
    conn.execute(f"UPDATE {TABLE} SET data = jsonb_set(data, '{{big}}', '1e400'::jsonb) WHERE key IN ('big1', 'Big2')")
    try:
        ast = env.get("parser").parse("$.big > 1")
        outcomes = probes.run_probes(conn, T, probes.build_probes([ast], records=records))
        fired = [o for o in outcomes if o.fired]
        assert fired and fired[0].row_key == "Big2"
    finally:
        conn.execute(f"UPDATE {TABLE} SET data = jsonb_set(data, '{{big}}', '1e300'::jsonb) WHERE key IN ('big1', 'Big2')")


def test_the_setup_lists_values_and_keys_in_code_points(world):
    from picks import view
    conn, records, _k, _c = world
    fields = {f["path"]: f for f in view._read_fields(conn, T, records=records)}
    assert fields["tag2"]["values"] == ["B", "a", "b"]
    assert view.collection_keys(conn, T, records) == _cp({k for d in THINGS.values() for k in d})


@pytest.mark.parametrize("member", ["sender_id", "who"])
def test_the_changed_flag_reads_ties_in_key_code_points(world, member):
    """"changed" keeps a record that differs from the one before it in its member's order (time, then key): two
    identical records of s6 at one time, U-b first in code points, so U-b is kept and u-a is not. Both series spellings (the demo's ts/sender_id text, and the
    general one)."""
    from picks import builder
    from picks.pyrunner import shape as pyshape
    from picks.pyrunner.rows import read_rows
    conn, _r, keys, _c = world
    records = _records(member)
    pick = _pick(changed=True)
    built = builder.build(pick, keys, records=records)
    cur = conn.execute(built.sql, built.params)
    names = [d.name for d in cur.description]
    sql = [r[names.index("key")] for r in cur.fetchall()]
    py = [r["key"] for r in pyshape.answer(read_rows(conn, T, records), pick, records)["rows"]]
    assert sql == py
    assert "U-b" in sql and "u-a" not in sql      # U-b comes first in code points, so it is the one kept


def test_a_string_nested_in_an_array_is_the_recorded_limit(world):
    """The one place left in the collation's hands (spec): a sort value that is an array holding strings. No COLLATE
    reaches inside a jsonb comparison, so on en_US the statement orders ["b"] before ["B"] while the second engine
    orders code points. Pinned, so a fix (or a change in Postgres) shows here."""
    conn, _r, _k, collate = world
    pick = _pick(filter='$.name == "tie"', sort={"field": "$.arr", "dir": "asc"})
    sql, py = _both(world, pick)
    assert _keys(py) == ["T-b", "t-a"]                    # ["B"] < ["b"] in code points
    assert _keys(sql) == (["T-b", "t-a"] if collate in ("C", "POSIX") else ["t-a", "T-b"])
