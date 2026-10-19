"""T-109's round: a series time either engine can't read is refused by name, by each engine on its own (a-chk, NOT CLEAN).

- HIGH 1: T-109's guard dropped such a row in the statement's WHERE, so a host running the statement alone (GIMS's
  pushed-down path, no second engine) totalled 8,400 against 8,401, for every odd form, with no word said. Now the
  bucket label itself refuses the row: XPR06, naming its key and its value.
- HIGH 2: the second engine's loud check (``bucket_label``) used strptime, which ignores letter case, so a lowercase
  ``…t…z`` passed it, ``local_time`` then read None, and the zoned bucket dropped the row as if its clock reading
  left years 1..9999. With T-109's guard the engines agreed on the wrong number (a capped Denver hour: 50, by hand
  51). Now the check is the one exact form, and an unreadable time on a clock raises, naming the row.
- MEDIUM: ``dashboard._span`` answered 500 on a field with no range (any series time outside the one form).

Built on a scratch database of the throwaway (the demo's seed, this tree's runtime), one odd Heartbeat added per
test and removed after; dropped at the end. SKIPS without AUTOSQL_PARITY_DSN.
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
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres")
SCRATCH = "t109r_scratch"
KEY = "hb-zz-t109"
MISSING = object()

#: a-chk's table: each a series time on Aug 20 by any reading, none a readable time (the demo has 8,400). T-114 made
#: two of a-chk's forms readable -- a fraction, an offset -- so they moved to READ_NOW: both engines count them
ODD = {
    "em-spaces": " 2026-08-20 ",
    "bare-date": "2026-08-20",
    "ascii-spaces": " 2026-08-20 ",
    "lowercase": "2026-08-20t10:00:00z",
    "missing": MISSING,
}
ZONES = (None, "America/Denver")


@pytest.fixture(scope="module")
def scratch():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    from demo.server import app as server_app, dashboard, db, settings
    from fastapi.testclient import TestClient

    with psycopg.connect(DSN, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
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
    db.connect = lambda *, application_name=None, autocommit=False: psycopg.connect(dsn, autocommit=autocommit, options=opts)
    dashboard._CACHE.clear()
    try:
        yield {"dsn": dsn, "opts": opts, "client": TestClient(server_app.app, raise_server_exceptions=False)}
    finally:
        db.connect = real
        dashboard._CACHE.clear()
        with psycopg.connect(DSN, autocommit=True) as cx:
            cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def _put(scratch, ts):
    """One Heartbeat with this series time (or none), in place of any earlier one."""
    import psycopg
    from demo.server import dashboard
    with psycopg.connect(scratch["dsn"], autocommit=True) as cx:
        cx.execute("DELETE FROM demo.records WHERE key = %s", (KEY,))
        if ts is not None:
            d = {"status": "ok", "sender_id": "hb-01", "payload": {"load": 10, "note": "odd"}}
            if ts is not MISSING:
                d["ts"] = ts
            cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', %s, %s::jsonb)", (KEY, json.dumps(d)))
    dashboard._CACHE.clear()


@pytest.fixture()
def odd(scratch):
    yield lambda ts: _put(scratch, ts)
    _put(scratch, None)


def _pick(per, zone):
    from demo.server import app as server_app
    p = {"source": "noun:Heartbeat", "computed": [], "filter": None, "sort": None, "cap": None, "window": None,
         "changed": False, "bucket": per, "aggregate": {"fn": "count", "field": None}}
    if zone:
        p["bucket_zone"] = zone
    return server_app.normalised_pick(p)


def _statement_alone(scratch, per, zone):
    """What a host with no second engine runs: the built statement, executed. Its rows, or the error it raised."""
    import psycopg
    from demo.server import app as server_app
    from picks import builder, env, zones
    with psycopg.connect(scratch["dsn"], options=scratch["opts"], autocommit=True) as conn:
        with env.checking_zones(zones.clock_check(conn)):
            b = builder.build(_pick(per, zone), server_app.collection_keys(conn, "noun:Heartbeat"))
        try:
            return conn.execute(b.sql, b.params).fetchall()
        except psycopg.Error as e:
            return e


def _ask(scratch, per, zone=None, show=None):
    v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": show,
         "summary": {"fn": "count", "field": None, "per": per}}
    if zone:
        v["zone"] = zone
    return scratch["client"].post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})


@needs_db
@pytest.mark.parametrize("zone", ZONES)
def test_with_no_odd_row_the_statement_counts_every_heartbeat(scratch, odd, zone):
    got = _statement_alone(scratch, "day", zone)
    assert not isinstance(got, Exception), got
    assert sum(int(r[1]) for r in got) == 8400


#: T-114: a series time with a fraction or an offset is a readable time now -- in its bucket on both engines, by its
#: instant (10:00:00.5Z and 15:30+05:30 are both Aug 20, 10:00 UTC, which is Aug 20, 04:00 in Denver)
READ_NOW = {"fraction": "2026-08-20T10:00:00.5Z", "offset": "2026-08-20T15:30:00+05:30"}


@needs_db
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", list(READ_NOW))
def test_a_series_time_with_a_fraction_or_an_offset_is_counted_by_both_engines(scratch, odd, form, zone):
    import psycopg
    from demo.server.app import pyshape
    odd(READ_NOW[form])
    got = _statement_alone(scratch, "day", zone)
    assert not isinstance(got, Exception), got
    assert sum(int(r[1]) for r in got) == 8401
    with psycopg.connect(scratch["dsn"], options=scratch["opts"], autocommit=True) as conn:
        py = pyshape.python_pane(conn, _pick("day", zone))
    assert sorted((r["bucket"], int(r["agg"])) for r in py["rows"]) == sorted((r[0], int(r[1])) for r in got)


@needs_db
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", list(ODD))
def test_the_statement_alone_refuses_the_row_by_name(scratch, odd, form, zone):
    odd(ODD[form])
    got = _statement_alone(scratch, "day", zone)
    assert isinstance(got, Exception), f"the statement alone answered {sum(int(r[1]) for r in got):,}, the row left out"
    assert got.sqlstate == "XPR06", (got.sqlstate, str(got)[:200])
    detail = json.loads(got.diag.message_detail)
    assert detail == {"key": KEY, "value": None if ODD[form] is MISSING else ODD[form]}


@needs_db
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", list(ODD))
def test_the_second_engine_refuses_the_same_row_by_name(scratch, odd, form, zone):
    import psycopg
    from demo.server.app import pyshape      # the second engine, as the host loads it
    odd(ODD[form])
    with psycopg.connect(scratch["dsn"], options=scratch["opts"], autocommit=True) as conn:
        with pytest.raises(ValueError) as e:
            pyshape.python_pane(conn, _pick("day", zone))
    assert repr(KEY) in str(e.value), str(e.value)


@needs_db
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", ["em-spaces", "lowercase", "missing"])
def test_the_page_says_which_heartbeat_and_why(scratch, odd, form, zone):
    odd(ODD[form])
    r = _ask(scratch, "day", zone)
    assert r.status_code == 200, r.text[:300]
    a = r.json()
    assert a.get("kind") == "refused" and not a.get("bars"), a.get("kind")
    if ODD[form] is MISSING:
        assert a["message"] == f"Heartbeat {KEY} has no time, so these can't be counted per day."
    else:
        assert a["message"] == f"Heartbeat {KEY} has a time this can't read (“{ODD[form]}”), so these can't be counted per day."


@needs_db
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", ["em-spaces", "lowercase"])
def test_the_two_pane_screen_says_which_heartbeat_and_why(scratch, odd, form, zone):
    # a-chk's round MEDIUM (T-105's class): /api/pick answered 500 on XPR06; it is said in the dashboard's sentence
    odd(ODD[form])
    r = scratch["client"].post("/api/pick", json={"pick": _pick("day", zone)})
    assert r.status_code == 422, (r.status_code, r.text[:200])
    rf = r.json()["refusal"]
    assert (rf["layer"], rf["construct"], rf["statement_sent"]) == (2, "series time", True) and "XPR06" in rf["why"]
    assert rf["body"] == f"Heartbeat {KEY} has a time this can't read (\u201c{ODD[form]}\u201d), so these can't be counted per day."


@needs_db
def test_a_capped_denver_hour_with_a_lowercase_time_refuses(scratch, odd):
    # a-chk's HIGH 2: show 100 of 168 hours on Denver, one Heartbeat 2026-08-14t00:00:00z in the first hour
    # (Aug 13 18:00 there): by hand that hour holds 51, or a refusal under B4; T-109 drew 50, both engines agreeing
    odd("2026-08-14t00:00:00z")
    r = _ask(scratch, "hour", "America/Denver", show=100)
    assert r.status_code == 200, r.text[:300]
    a = r.json()
    assert a.get("kind") == "refused" and not a.get("bars"), (a.get("kind"), (a.get("bars") or [])[:1])


@needs_db
def test_a_capped_denver_hour_with_no_odd_row_still_answers(scratch, odd):
    r = _ask(scratch, "hour", "America/Denver", show=100)
    a = r.json()
    assert a["admin"]["verdict"] == "agree"
    assert [b["value"] for b in a["bars"] if not b.get("empty")][0] == 50


@pytest.mark.parametrize("zone", ZONES)
def test_a_field_with_no_range_is_no_edge(zone):
    # a-chk's MEDIUM: any series time outside the one form makes the field text, with no range: no edge, never a 500
    from demo.server import dashboard
    assert dashboard._span({"ts": {"kind": "text", "range": None}}, "ts", zone) == (None, None)
