"""T-104 — a summary's time axis has a width limit.

The axis lays one slot for every hour, day, week or month of the data set's span (T-88).  With no limit,
one stray reading in 1900 laid 1.11 M hourly slots (865 MB), and a zero date (0001-01-01) ran a 4 GB cap
out.  On a question's clock (T-100) a reading the clock can't show became the edge 0001-01-01.

Now an edge the clock can't show is no edge, and past ``AXIS_SLOTS`` the axis narrows to the answer's own
buckets; past that too, the summary is refused in plain words, never a crash.

Each case adds ONE Heartbeat inside a transaction this file rolls back: the shared data never changes.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import demo.picks_host  # noqa: E402,F401
from demo.server import dashboard as D  # noqa: E402
from demo.server import db  # noqa: E402

AUG20 = {"version": 1, "join": "all",
         "items": [{"field": "ts", "op": "on", "value": "2026-08-20", "value2": "", "values": []}]}


@pytest.fixture
def stray(monkeypatch):
    """``stray(ts)``: one extra Heartbeat at ``ts``, in a transaction rolled back after the test.  The setup is
    read once per process (``_SETUP``) and answers are remembered (``_CACHE``): both start afresh on this
    connection, and the process's own setup is put back after (monkeypatch), so no other test sees the row."""
    c = db.connect(application_name="autosql-demo-t104")
    D._CACHE.clear()

    def add(ts: str | None):
        monkeypatch.setattr(D, "_SETUP", None)
        D._CACHE.clear()
        if ts is not None:
            c.execute("INSERT INTO demo.records (collection, key, data) VALUES ('noun:Heartbeat', 't104-stray', %s::jsonb)",
                      (json.dumps({"ts": ts, "status": "ok", "payload": {"load": 1, "note": "lima"},
                                   "sender_id": "hb-01"}),))
        return c
    yield add
    c.rollback()
    c.close()
    D._CACHE.clear()


def ask(conn, per: str, zone: str | None = None, flt=None, show=None) -> dict:
    view = {"dataset": "heartbeats", "columns": [], "sort": None, "show": show, "filter": flt,
            "summary": {"fn": "count", "field": None, "per": per}}
    if zone is not None:
        view["zone"] = zone
    return D.answer(conn, D.setup(conn), view, 0, admin=True)


def refused(conn, *args, **kw) -> str:
    try:
        a = ask(conn, *args, **kw)
    except D.ViewError as exc:
        return str(exc)
    raise AssertionError(f"answered with {a.get('total')} slots instead of a refusal: {a.get('sentence')}")


HOURS = "This summary spans too many hours to draw. Pick “Per day”, or filter it to a shorter time in step 3."
DAYS = "This summary spans too many days to draw. Filter it to a shorter time in step 3."


@pytest.mark.parametrize("zone", [None, "UTC"])
def test_a_reading_in_1900_per_hour_is_refused_in_words(stray, zone):
    assert refused(stray("1900-01-01T00:00:00Z"), "hour", zone) == HOURS


@pytest.mark.parametrize("per, words", [("day", DAYS), ("hour", HOURS)])
@pytest.mark.parametrize("zone", [None, "UTC"])
def test_the_zero_date_is_refused_in_words(stray, per, words, zone):
    assert refused(stray("0001-01-01T00:00:00Z"), per, zone) == words


def test_show_does_not_lift_the_limit(stray):
    """With Show, the axis runs between the first and last bucket shown: 1900 to 2026 is still too wide."""
    assert refused(stray("1900-01-01T00:00:00Z"), "hour", "UTC", show=25) == HOURS


def test_a_filter_to_a_short_time_answers_again(stray):
    """Past the limit the axis is the answer's own span, so the refusal's advice works: a filter to one day
    answers, hour by hour, both engines agreeing — the same 24 hours as with no stray reading."""
    conn = stray("1900-01-01T00:00:00Z")
    try:
        a = ask(conn, "hour", "UTC", flt=AUG20)
    except D.ViewError as exc:
        raise AssertionError(f"refused with a filter to one day: {exc}") from None
    assert a["total"] == 24 and a["admin"]["verdict"] == "agree", (a["total"], a["sentence"])
    assert a["bars"][0]["start"] == "2026-08-20T00:00:00" and a["bars"][-1]["start"] == "2026-08-20T23:00:00"


def test_on_a_clock_that_cannot_show_the_zero_date_the_axis_is_the_data_s_own(stray):
    """On Denver the zero date is 1 BC: in no bucket (T-100).  Its edge is no edge, so a per-month axis is the
    demo's own months — not 24,308 months from year 1."""
    want = ask(stray(None), "month", "America/Denver")
    got = ask(stray("0001-01-01T00:00:00Z"), "month", "America/Denver")
    assert got["total"] == want["total"] and [b["start"] for b in got["bars"]] == [b["start"] for b in want["bars"]], \
        f"the axis ran {got['total']:,} months, not the data's own {want['total']}"
    assert got["admin"]["verdict"] == "agree"


def test_within_the_limit_nothing_changes(stray):
    """1900 to 2026 is 46,253 days: inside the limit, the axis is the data set's whole span, as since T-88."""
    a = ask(stray("1900-01-01T00:00:00Z"), "day", "UTC")
    assert a["total"] == 46_253 and a["admin"]["verdict"] == "agree", (a["total"], a["sentence"])
    assert a["bars"][0]["start"] == "1900-01-01T00:00:00"


# ── the limit, exactly: AXIS_SLOTS slots draw, one more is refused (a-chk's MX1 moved it by one) ──

def _last_reading(conn) -> "_dt.datetime":
    ds = next(d for d in D.setup(conn)["datasets"] if d["id"] == "heartbeats")
    top = next(f for f in ds["fields"] if f["path"] == "ts")["range"]["max"]
    return _dt.datetime.strptime(top, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)


def _hours_before(conn, n: int, zone: str) -> str:
    """The instant whose hour is ``n`` hours on ``zone``'s wall clock before the data's last reading's, so a
    per-hour axis from it to the end spans ``n + 1`` wall hours.  (A whole hour, far from any clock change.)"""
    tz = ZoneInfo(zone)
    wall = _last_reading(conn).astimezone(tz).replace(tzinfo=None, minute=0, second=0) - _dt.timedelta(hours=n)
    t = wall.replace(tzinfo=tz)
    assert t.astimezone(_dt.timezone.utc).astimezone(tz).replace(tzinfo=None) == wall, f"{wall} isn't on {zone}'s clock"
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("zone, laid", [("UTC", D.AXIS_SLOTS),
                                        # six spring-forward nights in the span: counted by the limit, not laid
                                        ("America/Denver", D.AXIS_SLOTS - 6)])
def test_exactly_the_limit_draws(stray, zone, laid):
    conn = stray(None)
    ts = _hours_before(conn, D.AXIS_SLOTS - 1, zone)
    try:
        a = ask(stray(ts), "hour", zone)
    except D.ViewError as exc:
        raise AssertionError(f"exactly {D.AXIS_SLOTS:,} wall hours on {zone} were refused: {exc}") from None
    assert a["total"] == laid and a["admin"]["verdict"] == "agree", (a["total"], a["sentence"])


@pytest.mark.parametrize("zone", ["UTC", "America/Denver"])
def test_one_more_than_the_limit_is_refused(stray, zone):
    conn = stray(None)
    ts = _hours_before(conn, D.AXIS_SLOTS, zone)
    assert refused(stray(ts), "hour", zone) == HOURS
