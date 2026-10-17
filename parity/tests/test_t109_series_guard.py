"""T-109: a summary over the data set's own time never answers 500 on a stored time Postgres can't read (GA-77).

a-chk (T-103's check, LOW outside it): ONE Heartbeat whose time Python reads but Postgres's cast refuses -- a bare date
wrapped in Unicode spaces -- made every summary of Heartbeats answer HTTP 500, with no zone and on every clock
(InvalidDatetimeFormat): the series time was cast with no guard. Now the statement guards it as it guards a date
field, the second engine keeps B4's loud rule, and the page refuses in words. Built on a scratch database of the
throwaway (the demo's seed, this tree's runtime, the one odd row), dropped after. SKIPS without AUTOSQL_PARITY_DSN.
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
SCRATCH = "t109_series_scratch"
ODD = " 2026-08-20 "          # a bare date wrapped in em spaces: Python reads it, the cast does not


@pytest.fixture(scope="module")
def client():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    from demo.server import app as server_app, db, settings
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
        cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', 'hb-t109-odd', %s::jsonb)",
                   (json.dumps({"ts": ODD, "status": "ok", "sender_id": "hb-01", "payload": {"load": 10, "note": "odd"}}),))
        cx.commit()
    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    real = db.connect
    db.connect = lambda *, application_name=None, autocommit=False: psycopg.connect(dsn, autocommit=autocommit, options=opts)
    server_app_dashboard = __import__("demo.server.dashboard", fromlist=["x"])
    server_app_dashboard._CACHE.clear()
    try:
        yield TestClient(server_app.app, raise_server_exceptions=False)
    finally:
        db.connect = real
        server_app_dashboard._CACHE.clear()
        with psycopg.connect(DSN, autocommit=True) as cx:
            cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def _ask(client, per, zone=None):
    v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": None,
         "summary": {"fn": "count", "field": None, "per": per}}
    if zone:
        v["zone"] = zone
    return client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})


@needs_db
@pytest.mark.parametrize("per, zone", [("day", None), ("hour", None), ("day", "America/Denver"),
                                        ("hour", "Asia/Kolkata"), ("day", "UTC")])
def test_a_summary_over_a_series_holding_an_unreadable_time_refuses_in_words(client, per, zone):
    r = _ask(client, per, zone)
    assert r.status_code != 500, r.text[:300]
    a = r.json()
    assert a.get("kind") == "refused" and a.get("message"), a.get("kind")
    assert "bars" not in a or not a["bars"], "no number is shown from an answer that couldn't be double-checked"


@needs_db
def test_the_rows_of_the_same_data_set_still_answer(client):
    v = {"dataset": "heartbeats", "columns": ["ts", "status"], "sort": None, "show": None, "summary": None}
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})
    assert r.status_code == 200 and r.json()["admin"]["verdict"] == "agree", r.text[:200]
