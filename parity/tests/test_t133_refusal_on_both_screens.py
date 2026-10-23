"""T-133's bar 3 (a-chk's reading of 4600939): the clock list went quiet, and the refusal at use did not move.

The refusal is the statement's. A Heartbeat on Apr 30, 1916 read on Amsterdam's clock is refused in one sentence on
both screens: the dashboard answers 422 with it, and the two-pane screen refuses at layer 2 with it while its second
engine's pane answers on its own clock (T-105). On the dashboard the second engine doesn't run once the statement
refuses. Amsterdam's two clocks differ on this computer only before 1970, so the list now gives it no line; this
behaviour is the same before and after.

Needs a throwaway Postgres (AUTOSQL_PARITY_DSN). The test builds its own scratch database there (the demo's seed,
this tree's runtime, the one extra row), points the app's connection at it for the test, and drops it after. SKIPS
without a DSN, and skips (saying so) where this database reads Amsterdam's 1916 clock as Python does.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres")
SCRATCH = "t133_zone_scratch"
AMS = "Europe/Amsterdam"
WHEN = "1916-04-30T12:00:00Z"
WORDS = ("Amsterdam time can't read these times: this computer and its database disagree about "
         "Amsterdam's clocks on Apr 30, 1916, and this question reads a time from then.")


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
        cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', 'hb-t133-1916', %s::jsonb)",
                   (json.dumps({"ts": WHEN, "status": "ok", "sender_id": "hb-01",
                                "payload": {"load": 10, "note": "history"}}),))
        cx.commit()
    yield dsn
    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


@needs_db
def test_the_1916_row_on_amsterdams_clock_is_refused_by_the_statement_in_one_sentence_on_both_screens(
        scratch_dsn, monkeypatch):
    import psycopg
    from fastapi.testclient import TestClient

    from demo.server import app as server_app, db, settings
    from picks import legality

    with psycopg.connect(scratch_dsn) as cx:
        theirs = cx.execute("SELECT extract(epoch FROM ((%(t)s::timestamptz AT TIME ZONE %(z)s) "
                            "- (%(t)s::timestamptz AT TIME ZONE 'UTC')))::int", {"t": WHEN, "z": AMS}).fetchone()[0]
    ours = int(dt.datetime(1916, 4, 30, 12, tzinfo=dt.timezone.utc).astimezone(ZoneInfo(AMS)).utcoffset().total_seconds())
    if theirs == ours:
        pytest.skip("this database reads Amsterdam's 1916 clock as Python does: nothing to refuse here")
    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    monkeypatch.setattr(db, "connect", lambda *, application_name=None, autocommit=False:
                        psycopg.connect(scratch_dsn, autocommit=autocommit, options=opts))
    second = []
    real = server_app.pyshape.python_pane
    monkeypatch.setattr(server_app.pyshape, "python_pane", lambda *a, **k: second.append(1) or real(*a, **k))
    c = TestClient(server_app.app, raise_server_exceptions=False)

    # the dashboard: the statement refuses, the answer is that sentence, and the second engine never runs
    setup = c.get("/api/dashboard/setup?view=admin").json()
    hb = next(x for x in setup["datasets"] if x["id"] == "heartbeats")
    view = {"dataset": "heartbeats", "columns": list(hb["default_columns"]), "sort": None, "show": None,
            "summary": None, "zone": AMS, "filter": {"version": 1, "join": "all", "items": [
                {"field": "ts", "op": "from", "value": "17:00", "value2": "", "values": [], "part": "time_of_day"}]}}
    r = c.post("/api/dashboard/answer", json={"view": view, "page": 0, "admin": True})
    assert second == [], f"the second engine ran on the dashboard: {len(second)}"
    assert (r.status_code, r.json().get("message")) == (422, WORDS), (r.status_code, r.text[:300])

    # the two-pane screen: the statement refuses at layer 2 in the same sentence; the second engine's pane answers
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "filter": f'time_of_day($.ts, "{AMS}") >= 61200'})
    r = c.post("/api/pick", json={"pick": p})
    assert r.status_code == 422, (r.status_code, r.text[:300])
    body = r.json()
    rf = body["refusal"]
    assert (rf["layer"], rf["construct"]) == (2, "time zone") and "XPR05" in rf["why"], rf
    assert rf["body"] == WORDS, rf["body"]
    py = body["panes"]["python"]
    assert body["panes"]["sql"]["state"] == "raised" and py["state"] == "answered" and py["row_count"] > 0, (
        "the second engine's pane didn't answer on its own clock", body["panes"]["sql"]["state"], py["state"],
        py["row_count"])
