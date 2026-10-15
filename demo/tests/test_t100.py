"""T-100 — a summary cuts its hours, days, weeks and months on the question's clock (GA-70; T-98's follow-up).

A day's bar matches that day's filter: on Denver's clock Aug 20's bar is 900, as "Time is on Aug 20" is. Every
expected number here is from hand-written SQL on the demo's Heartbeats (2026-10-14, recorded in the spec).
The edges (DST days, week start, month ends, +5:30, +5:45, +14, -12, a date) are in
parity/pick-vectors-in-zone.json, run through both engines in parity/tests/test_t100_vectors.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401
from picks import view as pview  # noqa: E402

DEN = "America/Denver"


@pytest.fixture(scope="module")
def page():
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    c = TestClient(server_app.app)
    return c, c.get("/api/dashboard/setup?view=admin").json()


def _per(c, per, zone=None, fn="count", field=None, filt=None, ds="heartbeats", time=None):
    v = {"dataset": ds, "columns": [], "sort": None, "show": None,
         "summary": {"fn": fn, "field": field, "per": per, **({"time": time} if time else {})}}
    if zone is not None:
        v["zone"] = zone
    if filt is not None:
        v["filter"] = filt
    r = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})
    assert r.status_code == 200, r.text[:300]
    a = r.json()
    assert a["kind"] == "chart" and a["admin"]["verdict"] == "agree", a.get("message") or a["admin"].get("verdict")
    return a


def _bars(a):
    return [(b["start"], b["value"]) for b in a["bars"] if not b["empty"]]


DAYS = {
    DEN: [("2026-08-13", 300)] + [(f"2026-08-{d}", 1200) for d in range(14, 20)] + [("2026-08-20", 900)],
    "Asia/Kolkata": [("2026-08-14", 950)] + [(f"2026-08-{d}", 1200) for d in range(15, 21)] + [("2026-08-21", 250)],
    "Asia/Kathmandu": [("2026-08-14", 950)] + [(f"2026-08-{d}", 1200) for d in range(15, 21)] + [("2026-08-21", 250)],
    "Pacific/Kiritimati": [("2026-08-14", 500)] + [(f"2026-08-{d}", 1200) for d in range(15, 21)] + [("2026-08-21", 700)],
    "Etc/GMT+12": [("2026-08-13", 600)] + [(f"2026-08-{d}", 1200) for d in range(14, 20)] + [("2026-08-20", 600)],
}


@pytest.mark.parametrize("zone", list(DAYS))
def test_a_days_bars_are_that_clocks_days(page, zone):
    c, _ = page
    assert _bars(_per(c, "day", zone)) == [(f"{d}T00:00:00", float(n)) for d, n in DAYS[zone]]


def test_denvers_aug_20_bar_is_aug_20s_filter(page):
    """The outcome, in his terms: a day's bar matches that day's filter."""
    c, _ = page
    bar = dict(_bars(_per(c, "day", DEN)))["2026-08-20T00:00:00"]
    card = {"field": "ts", "op": "on", "value": "2026-08-20", "value2": "", "values": []}
    v = {"dataset": "heartbeats", "columns": ["sender_id"], "sort": None, "show": None, "summary": None, "zone": DEN,
         "filter": {"version": 1, "join": "all", "items": [card]}}
    kept = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True}).json()["total"]
    assert bar == kept == 900


def test_weeks_start_on_denvers_monday(page):
    c, _ = page
    assert _bars(_per(c, "week", DEN)) == [("2026-08-10T00:00:00", 3900.0), ("2026-08-17T00:00:00", 4500.0)]


def test_kolkatas_hours_are_its_own(page):
    c, _ = page
    bars = _bars(_per(c, "hour", "Asia/Kolkata"))
    assert len(bars) == 168 and {n for _, n in bars} == {50.0}
    assert bars[0][0] == "2026-08-14T05:00:00" and bars[-1][0] == "2026-08-21T04:00:00"


def test_a_total_per_day_on_denvers_clock(page):
    c, _ = page
    got = _bars(_per(c, "day", DEN, fn="sum", field="payload.load"))
    want = [13753, 55556, 59149, 58951, 56442, 56369, 58093, 41894]
    assert [n for _, n in got] == [float(x) for x in want]


def test_utc_as_a_zone_cuts_utc_days_with_zoned_labels(page):
    c, _ = page
    assert _bars(_per(c, "day", "UTC")) == [(f"2026-08-{d}T00:00:00", 1200.0) for d in range(14, 21)]


def test_a_question_without_a_zone_is_as_before(page):
    c, _ = page
    a = _per(c, "day")
    assert _bars(a) == [(f"2026-08-{d}T00:00:00Z", 1200.0) for d in range(14, 21)]
    assert "(UTC)" not in a["sentence"] and "time)" not in a["sentence"], a["sentence"]


def test_the_sentence_names_the_clock_its_buckets_are_on(page):
    c, _ = page
    a = _per(c, "day", DEN)
    assert a["sentence"].startswith("Number of Heartbeats, per day (Denver time)"), a["sentence"]
    assert "(UTC)" not in a["sentence"]


def test_a_date_field_is_its_own_day_on_any_clock(page):
    c, _ = page
    far = _bars(_per(c, "day", "Pacific/Kiritimati", ds="samples", time="due_date"))
    utc = _bars(_per(c, "day", "UTC", ds="samples", time="due_date"))
    assert far == utc and far, (far[:3], utc[:3])


def test_the_pick_carries_the_zone_its_buckets_are_cut_on():
    from demo.server import dashboard
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    st = TestClient(server_app.app).get("/api/dashboard/setup?view=admin").json()
    v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": None, "zone": DEN,
         "summary": {"fn": "count", "field": None, "per": "day"}}
    pick = dashboard.to_pick(dashboard.setup_for(dashboard.setup(dashboard._connect()), True), v)
    assert pick["bucket_zone"] == DEN and pick["bucket"] == "day"


def test_the_axis_has_no_slot_for_an_hour_the_clock_skips():
    """Mar 8 in Denver has no 2:00 AM, so the hour axis draws no empty bar for it; Nov 1's two 1:00s
    are one bucket and one slot."""
    from demo.server import dashboard as d
    spring = d._slots("hour", "2026-03-08T00:00:00", "2026-03-08T04:00:00", DEN)
    assert spring == ["2026-03-08T00:00:00", "2026-03-08T01:00:00", "2026-03-08T03:00:00", "2026-03-08T04:00:00"]
    fall = d._slots("hour", "2026-11-01T00:00:00", "2026-11-01T03:00:00", DEN)
    assert fall == ["2026-11-01T00:00:00", "2026-11-01T01:00:00", "2026-11-01T02:00:00", "2026-11-01T03:00:00"]
    assert len(d._slots("hour", "2026-03-08T00:00:00", "2026-03-08T04:00:00", "UTC")) == 5
