"""T-105 round (a-chk's MEDIUM): T-101's zone refusal on the two-pane screen is said in its own words, not a 500.

A row inside Edmonton's D (2026-11-02; Edmonton's clocks differ between this computer and its database from
November 2026) read by `time_of_day($.ts, "America/Edmonton") >= 61200` on /api/pick: the database refuses the
reading (XPR05, xpr.clock_refused). The dashboard has said that in words since T-101; /api/pick answered 500.

Needs a throwaway Postgres (AUTOSQL_PARITY_DSN). The test builds its own scratch database there (the demo's seed,
this tree's runtime, the one extra row), points the app's connection at it for the test, and drops it after.
SKIPS without a DSN.
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
SCRATCH = "t105_zone_scratch"


@pytest.fixture(scope="module")
def scratch_dsn():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load

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
        cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', 'hb-t105-nov', %s::jsonb)",
                   (json.dumps({"ts": "2026-11-02T12:00:00Z", "status": "ok", "sender_id": "hb-01",
                                "payload": {"load": 10, "note": "november"}}),))
        cx.commit()
    yield dsn
    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


@needs_db
def test_a_row_inside_edmontons_D_is_refused_on_the_two_pane_screen_in_the_dashboards_words(scratch_dsn, monkeypatch):
    import psycopg
    from fastapi.testclient import TestClient

    from demo.server import app as server_app, db, settings
    from picks import legality, zones

    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    monkeypatch.setattr(db, "connect", lambda *, application_name=None, autocommit=False:
                        psycopg.connect(scratch_dsn, autocommit=autocommit, options=opts))
    with psycopg.connect(scratch_dsn) as cx:
        if not zones.disagreements(cx, "America/Edmonton"):
            pytest.skip("Edmonton has no disagreement window on this database (its zone data agrees with Python's)")
    c = TestClient(server_app.app, raise_server_exceptions=False)
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "filter": 'time_of_day($.ts, "America/Edmonton") >= 61200'})
    r = c.post("/api/pick", json={"pick": p})
    assert r.status_code == 422, (r.status_code, r.text[:200])
    rf = r.json()["refusal"]
    assert (rf["layer"], rf["construct"]) == (2, "time zone") and "XPR05" in rf["why"]
    assert rf["body"] == ("Edmonton time can't read these times: this computer and its database disagree about "
                          "Edmonton's clocks on Nov 2, 2026, and this question reads a time from then.")
    # and a question on the same data that reads no row inside D still answers, both engines agreeing
    p.update({"filter": 'time_of_day($.ts, "America/Denver") >= 61200'})
    r = c.post("/api/pick", json={"pick": p})
    assert r.status_code == 200 and r.json()["verdict"] == "agree", r.text[:200]
