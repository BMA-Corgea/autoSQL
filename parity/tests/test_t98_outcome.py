"""T-98's outcome, the way the owner will check it: the page's own filters with a time of day, on
the demo's own Heartbeats, through BOTH engines, each equal to hand-written SQL.

The Heartbeats are copied, read-only, from the shared demo database into a TEMPORARY table on a
throwaway Postgres carrying THIS tree's runtime (AUTOSQL_PARITY_DSN): the shared database holds the
runtime its last `./run-demo up` installed. The hand-written SQL reads the UTC text by hour, worked
out from the rule (Denver is UTC-6 all of August), never from either engine. SKIPS without a DSN.
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

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres with this tree's runtime")
DEN = "America/Denver"
TABLE = "t98_heartbeats"


def card(field, op, value="", value2="", **kw):
    return {"field": field, "op": op, "value": value, "value2": value2, "values": [], **kw}


def tod(op, value="", value2=""):
    return card("ts", op, value, value2, part="time_of_day")


def tree(*items):
    return {"version": 1, "join": "all", "items": list(items)}


def _hours(*hh):
    return "substr(data->>'ts', 12, 2) IN (" + ", ".join(f"'{h:02d}'" for h in hh) + ")"


#: name → (zone, filter tree, hand-written WHERE, the sentence's filter words)
CASES = {
    "the owner's question: Aug 20 from 5:00 PM, Denver (one hour: the data ends at 5 PM there)": (
        DEN, tree(card("ts", "on", "2026-08-20"), tod("from", "17:00")),
        "data->>'ts' >= '2026-08-20T23:00:00Z' AND data->>'ts' < '2026-08-21T06:00:00Z'",
        "Time is on Aug 20 and Time (time of day) from 5:00 PM"),
    "the same in UTC (seven hours)": (
        "UTC", tree(card("ts", "on", "2026-08-20"), tod("from", "17:00")),
        "data->>'ts' >= '2026-08-20T17:00:00Z' AND data->>'ts' < '2026-08-21T00:00:00Z'",
        "Time is on Aug 20 and Time (time of day) from 5:00 PM"),
    "Aug 19 from 5:00 PM, Denver (seven hours)": (
        DEN, tree(card("ts", "on", "2026-08-19"), tod("from", "17:00")),
        "data->>'ts' >= '2026-08-19T23:00:00Z' AND data->>'ts' < '2026-08-20T06:00:00Z'",
        "Time is on Aug 19 and Time (time of day) from 5:00 PM"),
    "every day from 5:00 PM, Denver (23:00Z to 05:59Z)": (
        DEN, tree(tod("from", "17:00")), _hours(23, 0, 1, 2, 3, 4, 5),
        "Time (time of day) from 5:00 PM"),
    "every day until 5:00 PM, Denver": (
        DEN, tree(tod("until", "17:00")), "NOT " + _hours(23, 0, 1, 2, 3, 4, 5),
        "Time (time of day) until 5:00 PM"),
    "between 10:00 PM and 2:00 AM, across midnight, Denver (04:00Z to 07:59Z)": (
        DEN, tree(tod("between", "22:00", "02:00")), _hours(4, 5, 6, 7),
        "Time (time of day) between 10:00 PM and 2:00 AM"),
    "between 9:00 AM and 5:00 PM, Denver (15:00Z to 22:59Z)": (
        DEN, tree(tod("between", "09:00", "17:00")), _hours(15, 16, 17, 18, 19, 20, 21, 22),
        "Time (time of day) between 9:00 AM and 5:00 PM"),
    "from 5:00 PM in Kathmandu (UTC+5:45: 11:15Z to 18:14Z, so the hours 12:00Z to 18:00Z, 11:45 PM there)": (
        "Asia/Kathmandu", tree(tod("from", "17:00")), _hours(*range(12, 19)),
        "Time (time of day) from 5:00 PM"),
}


@pytest.fixture(scope="module")
def world():
    import psycopg

    import demo.picks_host  # noqa: F401  (registers the host's modules)
    import this_runtime
    from demo.server import db
    from picks import view
    from picks.records import Records

    src = db.connect(application_name="autosql-t98-outcome-copy")
    try:
        rows = src.execute("SELECT key, data::text FROM demo.records WHERE collection = 'noun:Heartbeat'").fetchall()
    finally:
        src.rollback()
        src.close()
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)       # the runtime under test, never what a database happens to hold
    conn = psycopg.connect(DSN)
    conn.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO {TABLE} VALUES ('noun:Heartbeat', %s, %s::jsonb)", rows)
    keys = sorted({k for _, d in rows for k in json.loads(d)})
    records = Records(table=TABLE, sources={"noun:Heartbeat": ", ".join(keys)})
    fields = {f["path"]: f for f in view._read_fields(conn, "noun:Heartbeat", records=records)}
    assert fields["ts"]["kind"] == "time" and len(rows) == 8400
    fields["ts"]["label"] = "Time"                   # as the demo's setup names it
    yield conn, records, fields, keys
    conn.rollback()
    conn.close()


@needs_db
@pytest.mark.parametrize("name", list(CASES))
def test_the_page_keeps_what_hand_written_sql_keeps_in_both_engines(world, name):
    from picks import builder, view
    from picks.pyrunner import shape as pyshape
    from picks.pyrunner.rows import read_rows

    conn, records, fields, keys = world
    zone, flt, where, words = CASES[name]
    v = {"zone": zone, "filter": flt}
    expr = view.filter_expression(v, fields)
    assert view.filter_words(v, fields) == words
    pick = {"source": "noun:Heartbeat", "computed": [], "filter": expr, "sort": None, "cap": None,
            "window": None, "changed": False, "bucket": "off"}
    built = builder.build(pick, keys, records=records)
    sql = sorted(r[1] for r in conn.execute(built.sql, built.params).fetchall())
    py = sorted(r["key"] for r in pyshape.answer(read_rows(conn, "noun:Heartbeat", records), pick, records)["rows"])
    hand = sorted(r[0] for r in conn.execute(
        f"SELECT key FROM {TABLE} WHERE collection = 'noun:Heartbeat' AND ({where})").fetchall())
    assert 0 < len(hand) < 8400, "this case tells no rows apart"
    assert (len(sql), len(py)) == (len(hand), len(hand)) and sql == hand and py == hand, (
        f"{name}: statement {len(sql)}, second engine {len(py)}, hand-written SQL {len(hand)}")


@needs_db
def test_the_counts_the_owner_will_see(world):
    """The numbers his "try these" list gives: 50, 350, 350."""
    conn = world[0]
    n = lambda w: conn.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}").fetchone()[0]  # noqa: E731
    assert [n(CASES[k][2]) for k in list(CASES)[:3]] == [50, 350, 350]


@needs_db
def test_a_probe_over_a_time_of_day_runs_and_never_fires(world):
    """a-chk's MEDIUM on b1: time_of_day inside a probed operand. The probes compile it behind the
    zone guard, run it on the real Heartbeats, and find nothing out of range (0..86399 never is)."""

    from picks import env, probes

    conn, records, _f, _k = world
    srcs = ['time_of_day($.ts, "UTC") * 2 > 100', 'coalesce(time_of_day($.ts, "UTC"), 0) > 5',
            'abs(time_of_day($.ts, "America/Denver") - 43200) < 3600',
            'time_of_day($.ts, "UTC") + $.payload.load > 61200',
            'if(time_of_day($.ts, "UTC") > 0, time_of_day($.ts, "UTC"), 1) / 60 > 1']
    parse = env.get("parser").parse
    outcomes = probes.check(conn, "noun:Heartbeat", [parse(s) for s in srcs], records=records)
    assert outcomes and not any(o.fired for o in outcomes)
    assert any("xpr.zone_checked(" in o.probe.sql for o in outcomes)
