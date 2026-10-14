"""T-98 — time of day on any time field, read on a named clock (GA-68 Q6 and Q7).

This file holds the parts that need no database: the gate's rule for ``time_of_day`` and what
the statement builder hands the compiler. The SQL engine is measured against GIMS's evaluator
in ``runtime/tests/test_runtime_time_of_day.py`` and ``compiler/tests/test_compile_time_of_day.py`` (a
throwaway Postgres carrying THIS tree's runtime: the shared demo database carries whatever the
last ``./run-demo up`` installed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401  (the host registers its modules first)
import gate  # noqa: E402
from picks import builder, env  # noqa: E402

EXPR = env.get("parser")
ZONES = env.get("evaluator").TIME_ZONES


def _gate(src, zones=ZONES):
    return gate.gate(EXPR.parse(src), zones=zones)


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_listed_zone_written_in_the_expression_passes():
    _gate('time_of_day($.ts, "America/Denver") >= 61200')
    _gate('(time_of_day($.ts, "UTC") >= 79200) or (time_of_day($.ts, "UTC") < 7200)')


@pytest.mark.parametrize("src, words", [
    ('time_of_day($.ts, "Mars/Olympus") >= 0', "“Mars/Olympus” is not a time zone"),
    ('time_of_day($.ts, "america/denver") >= 0', "“america/denver” is not a time zone"),
    ('time_of_day($.ts, "EST5EDT") >= 0', "“EST5EDT” is not a time zone"),
    ('time_of_day($.ts, $.zone) >= 0', "written in the expression"),
    ('time_of_day($.ts, 5) >= 0', "written in the expression"),
    ('time_of_day($.ts, coalesce("UTC")) >= 0', "written in the expression"),
    ('time_of_day($.ts) >= 0', "takes a time and a time zone"),
    ('time_of_day($.ts, "UTC", "UTC") >= 0', "takes a time and a time zone"),
])
def test_anything_else_is_refused_by_name(src, words):
    with pytest.raises(gate.Refused) as e:
        _gate(src)
    assert e.value.construct == "time_of_day"
    assert words in e.value.why


def test_without_a_zone_list_time_of_day_is_refused():
    """A caller that hands the gate no zone list gets no time_of_day at all (fail closed)."""
    with pytest.raises(gate.Refused) as e:
        gate.gate(EXPR.parse('time_of_day($.ts, "UTC") >= 0'))
    assert e.value.construct == "time_of_day"


def test_the_zone_rule_reaches_inside_any_construct():
    for src in ('if(time_of_day($.ts, $.z) > 1, 1, 0)', 'not (time_of_day($.ts, $.z) > 1)',
                'abs(time_of_day($.ts, $.z)) + 1', '-time_of_day($.ts, $.z) == 1'):
        with pytest.raises(gate.Refused):
            _gate(src)


# ── the statement builder ────────────────────────────────────────────────────

def _pick(flt):
    from picks import legality
    p = legality.default_pick(env.records(None))
    p.update({"source": "noun:Heartbeat", "filter": flt})
    return p


def test_the_builder_compiles_time_of_day_behind_the_zone_guard():
    built = builder.build(_pick('time_of_day($.ts, "America/Denver") >= 61200'), ["ts", "status"])
    assert "xpr.time_of_day(" in built.sql and "xpr.zone_checked(" in built.sql
    assert "America/Denver" in built.params.values()


def test_the_builder_refuses_an_unlisted_zone_before_any_sql():
    with pytest.raises(gate.Refused) as e:
        builder.build(_pick('time_of_day($.ts, "Mars/Olympus") >= 0'), ["ts"])
    assert e.value.construct == "time_of_day"


# ── the layer-2 probes ───────────────────────────────────────────────────────

def test_no_probe_compiles_a_time_of_day_operand():
    """Its value is 0..86399 or null: neither probe can fire on it, and a probe compiled
    without the zone list would refuse the pick (Uncompilable) for nothing."""
    from picks import probes
    ast = EXPR.parse('(time_of_day($.ts, "UTC") >= 61200) and (time_of_day($.ts, "UTC") == 5400)'
                     ' and ($.payload.load > 1)')
    numeric, container = probes.numeric_context_operands(ast), probes.container_check_operands(ast)
    assert EXPR.parse("$.payload.load") in numeric and EXPR.parse("5400") in container
    for op in numeric + container:
        assert "time_of_day" not in repr(op), op


# ── picks/zones.py: the clock, in Python, computed once per pick ─────────────

import datetime as _dt  # noqa: E402

from picks import zones  # noqa: E402

D = _dt.date


@pytest.mark.parametrize("zone, words", [
    ("America/Denver", "Denver time"), ("UTC", "UTC"), ("Etc/UTC", "UTC"),
    ("America/Argentina/Buenos_Aires", "Buenos Aires time"), ("America/Port-au-Prince", "Port-au-Prince time"),
    ("Etc/GMT+12", "UTC−12"), ("Etc/GMT-14", "UTC+14"), ("Etc/GMT", "UTC"),
])
def test_a_zone_reads_as_a_place(zone, words):
    assert zones.label(zone) == words


@pytest.mark.parametrize("day, zone, start, end", [
    (D(2026, 8, 20), "America/Denver", "2026-08-20T06:00:00Z", "2026-08-21T06:00:00Z"),
    (D(2026, 3, 8), "America/Denver", "2026-03-08T07:00:00Z", "2026-03-09T06:00:00Z"),    # 23 hours
    (D(2026, 11, 1), "America/Denver", "2026-11-01T06:00:00Z", "2026-11-02T07:00:00Z"),   # 25 hours
    (D(2026, 8, 21), "Pacific/Kiritimati", "2026-08-20T10:00:00Z", "2026-08-21T10:00:00Z"),
    (D(2026, 8, 20), "Asia/Kathmandu", "2026-08-19T18:15:00Z", "2026-08-20T18:15:00Z"),
    (D(2026, 8, 20), "Etc/GMT+12", "2026-08-20T12:00:00Z", "2026-08-21T12:00:00Z"),
    (D(2026, 8, 20), "UTC", "2026-08-20T00:00:00Z", "2026-08-21T00:00:00Z"),
    # Santiago's clocks go forward at midnight: Sep 6 2026 begins at 01:00, the change itself
    (D(2026, 9, 6), "America/Santiago", "2026-09-06T04:00:00Z", "2026-09-07T03:00:00Z"),
])
def test_a_day_is_its_first_instant_to_the_next_days(day, zone, start, end):
    assert zones.day_span(day, zone) == (start, end)


@pytest.mark.parametrize("day, h, m, s, zone, utc", [
    (D(2026, 8, 20), 17, 0, 0, "America/Denver", "2026-08-20T23:00:00Z"),
    (D(2026, 11, 1), 1, 30, 0, "America/Denver", "2026-11-01T07:30:00Z"),   # twice that day: the first
    (D(2026, 3, 8), 3, 0, 0, "America/Denver", "2026-03-08T09:00:00Z"),
    (D(2026, 8, 20), 4, 30, 0, "Asia/Kolkata", "2026-08-19T23:00:00Z"),
])
def test_a_picked_wall_time_is_one_instant(day, h, m, s, zone, utc):
    assert zones.wall_instant(day, h, m, s, zone) == utc


def test_a_wall_time_the_clocks_skip_is_refused_in_words():
    with pytest.raises(zones.ZoneError) as e:
        zones.wall_instant(D(2026, 3, 8), 2, 30, 0, "America/Denver")
    assert str(e.value) == "2:30 AM doesn't happen on Mar 8 in Denver time: the clocks go forward an hour."
    with pytest.raises(zones.ZoneError) as e:
        zones.wall_instant(D(2026, 10, 4), 2, 15, 0, "Australia/Lord_Howe")
    assert "the clocks go forward 30 minutes" in str(e.value)


@pytest.mark.parametrize("seconds, words", [
    (61200, "5:00 PM"), (0, "12:00 AM"), (43200, "12:00 PM"), (7200, "2:00 AM"),
    (79200, "10:00 PM"), (86399, "11:59:59 PM"), (61215, "5:00:15 PM"),
])
def test_a_time_of_day_reads_on_a_clock_face(seconds, words):
    assert zones.clock_words(seconds) == words


def test_a_zone_the_guard_refused_is_named_in_plain_words():
    msg = "time zone America/Edmonton: this database's clock differs from the evaluator's from 2026-11-01"
    assert zones.refusal_words(msg) == (
        "Edmonton time can't be used yet: this computer and its database disagree about "
        "Edmonton's clocks from Nov 1, 2026.")
    assert zones.refusal_words("time zone Mars/Olympus: this database does not know it") == (
        "Olympus time can't be used yet: this computer's database doesn't know it.")


# ── a field's kind is decided from EVERY value, not the first 2,001 ──────────

def _fields_of(values: list) -> dict:
    from demo.server import db
    from picks import view
    from picks.records import Records
    conn = db.connect(application_name="autosql-t98-kind")
    try:
        conn.execute("CREATE TEMPORARY TABLE t98_kind (collection text, key text, data jsonb)")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO t98_kind VALUES ('noun:K', %s, %s::jsonb)",
                            [(f"k{i:05d}", f'{{"at": "{v}"}}') for i, v in enumerate(values)])
        fields = view._read_fields(conn, "noun:K", records=Records(table="t98_kind", sources={"noun:K": "at"}))
    finally:
        conn.rollback()
        conn.close()
    return {f["path"]: f for f in fields}


def _times(n: int) -> list:
    t0 = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    return [(t0 + _dt.timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(n)]


def test_a_wide_time_field_with_one_odd_value_late_in_the_order_is_text():
    """T-88 ruling 1 says a field is a time only when EVERY value is one. The page used to look
    at the first 2,001 distinct values in sorted order, so an odd value sorting after them was
    never seen: the field was called a time, and time conditions -- and time of day -- were
    offered over text."""
    f = _fields_of(_times(2100) + ["zzz: not a time"])["at"]
    assert f["kind"] == "text", f["kind"]


def test_a_wide_time_field_is_still_a_time():
    assert _fields_of(_times(2100))["at"]["kind"] == "time"


def test_a_time_written_in_other_digits_is_not_a_time():
    """The fixed-width UTC form is ASCII digits: a full-width-digit value makes the field text,
    as the statement's own check reads it."""
    f = _fields_of(_times(5) + ["２０２６-01-01T00:00:00Z"])["at"]
    assert f["kind"] == "text", f["kind"]


# ── the clock setting's list (slice c) ───────────────────────────────────────

def test_the_list_offers_one_entry_per_place():
    names = {"UTC", "Etc/UTC", "Etc/GMT+12", "America/Denver", "America/Indiana/Indianapolis",
             "America/Indianapolis", "Asia/Kolkata", "America/Argentina/Buenos_Aires"}
    links = {"America/Indianapolis": "America/Indiana/Indianapolis", "Etc/UTC": "UTC"}
    got = {e["zone"]: e for e in zones.offered(names, links)}
    assert set(got) == {"UTC", "America/Denver", "America/Indiana/Indianapolis", "Asia/Kolkata",
                        "America/Argentina/Buenos_Aires"}
    assert got["America/Argentina/Buenos_Aires"] == {
        "zone": "America/Argentina/Buenos_Aires", "label": "Buenos Aires time", "place": "Buenos Aires",
        "area": "America"}
    assert [e["zone"] for e in zones.offered(names, links)][0] == "UTC"


@pytest.mark.parametrize("first, last, words", [
    (_dt.date(1800, 1, 1), _dt.date(1937, 6, 1), "Not available: this computer and its database disagree on its clocks before 1970."),
    (_dt.date(1916, 5, 1), _dt.date(2027, 1, 1), "Not available: this computer and its database disagree on its clocks from 1916."),
    (_dt.date(2026, 11, 26), _dt.date(2100, 1, 1), "Not available: this computer and its database disagree on its clocks from November 2026."),
    (None, None, "Not available: this computer's database doesn't know it."),
])
def test_a_refused_zone_reads_in_one_short_line(first, last, words):
    assert zones.mark_words(first, last) == words
    assert "tzdata" not in words and "backzone" not in words and len(words) <= 90


def test_the_marks_come_from_both_clocks(monkeypatch):
    """Read against the demo's own database with built-in SQL only (no runtime function): UTC
    and Denver agree; a zone whose Python clock is moved an hour from Nov 2026 is marked."""
    from demo.server import db
    conn = db.connect(application_name="autosql-t98-marks")
    try:
        marks = zones.marks(conn, ["UTC", "America/Denver"])
        assert marks == {"UTC": None, "America/Denver": None}
        real = zones._python_offsets
        monkeypatch.setattr(zones, "_python_offsets", lambda z, ts: [
            o + 3600 if t >= 1793520000 else o for t, o in zip(ts, real(z, ts))])
        moved = zones.marks(conn, ["America/Denver"], cache=False)
        assert moved["America/Denver"] == "Not available: this computer and its database disagree on its clocks from November 2026."
    finally:
        conn.rollback()
        conn.close()


def _client():
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    return TestClient(server_app.app)


def test_the_page_gets_the_list_with_each_zones_mark(monkeypatch):
    monkeypatch.setattr(zones, "marks", lambda conn, names, cache=True: {
        z: ("Not available: this computer's database doesn't know it." if z == "Europe/Amsterdam" else None)
        for z in names})
    r = _client().get("/api/dashboard/zones")
    assert r.status_code == 200
    body = r.json()
    by = {e["zone"]: e for e in body["zones"]}
    assert body["zones"][0]["zone"] == "UTC"
    assert by["America/Denver"] == {"zone": "America/Denver", "label": "Denver time", "place": "Denver",
                                     "area": "America", "why": None}
    assert by["Europe/Amsterdam"]["why"] == "Not available: this computer's database doesn't know it."
    # every name both engines accept reaches a listed place: listed itself, or by its old name
    others = {e["zone"]: e for e in body["others"]}
    accepted = set(by) | set(body["aliases"]) | set(others)
    assert accepted == set(ZONES)
    assert all(t in by for t in body["aliases"].values())
    # an alias is the same clock under another name, never a guess: UTC-12 is not UTC
    assert body["aliases"].get("Etc/UTC") == "UTC"
    assert "Etc/GMT+12" not in body["aliases"] and others["Etc/GMT+12"]["label"] == "UTC−12"


def test_the_list_is_the_same_for_either_view():
    c = _client()
    a, b = c.get("/api/dashboard/zones"), c.get("/api/dashboard/zones?view=admin")
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
