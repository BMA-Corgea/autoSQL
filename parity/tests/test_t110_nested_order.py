"""T-110: on the two-pane screen, a sort over text nested in jsonb is refused in words on a locale database.

The demo's own Heartbeats reach the limit T-106 kept: every row's `$.payload` is an object (`{"load": …, "note": …}`)
whose keys and text values Postgres compares by the database's collation, while the second engine compares code
points. The seed's notes are lowercase words, which en_US happens to order as code points do; two Heartbeats added
here, with the lowest load and the notes "B" and "a", are ordered two ways on a glibc `en_US` database ("a" first
there, "B" first in code points). Now the pick is refused before its statement runs, in its own words; on C it
answers as before, both engines agreeing.

Each database gets a scratch database built from the demo's seed and this tree's runtime, the app pointed at it for
the test, dropped after. AUTOSQL_LOCALE_DSN (postgres:16, `--locale=en_US.utf8`) and AUTOSQL_PARITY_DSN (alpine, C);
SKIPS a database without a DSN.
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
SCRATCH = "t110_nested_scratch"
WORDS = ("These rows can't be sorted by $.payload on this database: some of its values are lists or groups holding "
         "text, and this database orders that text differently from the second engine. Sort by another field.")


@pytest.fixture(scope="module", params=DSNS)
def screen(request):
    dsn = request.param
    if not dsn:
        pytest.skip("set AUTOSQL_LOCALE_DSN / AUTOSQL_PARITY_DSN to throwaway Postgres databases")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    from demo.server import app as server_app, db, settings
    from fastapi.testclient import TestClient

    with psycopg.connect(dsn, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
        cx.execute(f"CREATE DATABASE {SCRATCH}")
    scratch = make_conninfo(**{**conninfo_to_dict(dsn), "dbname": SCRATCH})
    with psycopg.connect(scratch, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(scratch) as cx:
        load.install_schema(cx)
        load.copy_rows(cx)
        for key, note in (("hb-t110-a", "a"), ("hb-t110-b", "B")):
            cx.execute("INSERT INTO demo.records VALUES ('noun:Heartbeat', %s, %s::jsonb)",
                       (key, json.dumps({"ts": "2026-08-14T00:00:00Z", "status": "ok", "sender_id": "hb-01",
                                         "payload": {"load": -1, "note": note}})))
        cx.commit()
        collate = cx.execute("SELECT datcollate FROM pg_database WHERE datname = current_database()").fetchone()[0]
    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    real = db.connect
    db.connect = lambda *, application_name=None, autocommit=False: psycopg.connect(scratch, autocommit=autocommit,
                                                                                    options=opts)
    try:
        yield TestClient(server_app.app, raise_server_exceptions=False), collate
    finally:
        db.connect = real
        with psycopg.connect(dsn, autocommit=True) as cx:
            cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def _pick(sort_field, cap=5, **kw):
    from picks import legality
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "sort": {"field": sort_field, "dir": "asc"}, "cap": cap})
    p.update(kw)
    return p


def test_a_sort_by_the_payload_is_refused_in_words_on_a_locale_database(screen):
    client, collate = screen
    r = client.post("/api/pick", json={"pick": _pick("$.payload")})
    if collate in ("C", "POSIX"):
        assert r.status_code == 200 and r.json()["verdict"] == "agree", r.text[:200]
        return
    assert r.status_code == 422, (r.status_code, r.text[:200])
    rf = r.json()["refusal"]
    assert (rf["layer"], rf["member"], rf["statement_sent"]) == (2, "c", False)
    assert rf["body"] == WORDS
    assert rf["row_key"] and rf["row_key"].startswith("hb-")


def test_a_sort_by_a_number_inside_the_payload_still_answers_everywhere(screen):
    client, _collate = screen
    r = client.post("/api/pick", json={"pick": _pick("$.payload.load")})
    assert r.status_code == 200 and r.json()["verdict"] == "agree", r.text[:200]


def test_each_screen_says_the_sort_refusal_in_its_own_words():
    """T-105's pattern: the two-pane screen names the field; the dashboard (whose sort can't reach a field of lists
    or objects today) has its own plain line for the day it can, and it is not the container operand's."""
    from demo.server import dashboard, errors
    from picks import probes
    exc = probes.SortRefusal("$.tags", "hb-1", probe=None)
    assert errors.sort_order_words("$.tags").startswith("These rows can't be sorted by $.tags on this database:")
    words = dashboard.plain_refusal({"headline": errors.LAYER_2_HEADLINE, "why": exc.cause})
    assert words == ("These rows can't be sorted by this field on this database: some of its values hold text "
                     "inside a list or a group, and this database orders that text differently. Sort by another field.")
    assert words != dashboard.plain_refusal({"why": "container operand: an == or != operand resolved to an object"})
