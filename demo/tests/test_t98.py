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


def _gaps(**d):
    """A question's zone check (T-101) with D given by hand: zone → D, empty for any other."""
    return env.checking_zones(lambda z: d.get(z.replace("/", "_"), ()))


def test_the_builder_reads_the_clock_checked_only_where_the_clocks_disagree():
    """T-101: Denver with D empty is the plain reading; with a D, the checked one; with no zone
    check at all (a path that forgot), nothing compiles."""
    src = 'time_of_day($.ts, "America/Denver") >= 61200'
    with _gaps():
        built = builder.build(_pick(src), ["ts", "status"])
    assert "xpr.time_of_day(" in built.sql and "float8[]" not in built.sql and "zone_checked" not in built.sql
    assert "America/Denver" in built.params.values()
    with _gaps(America_Denver=((1793520000.0, float("inf")),)):
        built = builder.build(_pick(src), ["ts", "status"])
    assert built.sql.count("::float8[]") == 1 and [1793520000.0] in built.params.values()
    with pytest.raises(gate.Refused) as e:
        builder.build(_pick(src), ["ts", "status"])
    assert "disagreements" in str(e.value)


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
    from picks import view as pview                  # T-114: a day's ends are the view's, as that day's bare date reads
    mark = (lambda t: t[:-1] + ".000000!")
    assert (pview._day_start(day, zone), pview._day_end(day, zone)) == (mark(start), mark(end))


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


def test_a_row_the_check_refused_is_named_in_plain_words():
    """T-101: the zone, the row's date, and why that date matters."""
    msg = ("time zone Europe/Amsterdam: this database's clock differs from the evaluator's on 1916-04-30, "
           "a time this question reads")
    assert zones.refusal_words(msg) == (
        "Amsterdam time can't read these times: this computer and its database disagree about "
        "Amsterdam's clocks on Apr 30, 1916, and this question reads a time from then.")
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


def test_a_wide_time_field_whose_odd_values_sort_late_is_decided_over_every_value():
    """The kind is decided over EVERY value (T-98): the page used to look at the first 2,001 distinct values in sorted
    order, so odd values sorting after them were never seen. T-114 (the foreman's must 2): a field is a time when at
    least one value is readable and MORE than half look like a time -- so here, where most values sort after the first
    2,001 and are not times, it is text, though those 2,001 alone would make it a time."""
    f = _fields_of(_times(2100) + [f"zzz: not a time {i}" for i in range(2200)])["at"]
    assert f["kind"] == "text", f["kind"]


def test_a_wide_time_field_with_one_odd_value_late_in_the_order_is_still_a_time():
    """T-114 (the foreman's must 2): one value that is no time never turns a time field into text -- it is left out
    and counted; the field keeps its charts."""
    f = _fields_of(_times(2100) + ["zzz: not a time"])["at"]
    assert f["kind"] == "time", f["kind"]


def test_a_wide_time_field_is_still_a_time():
    assert _fields_of(_times(2100))["at"]["kind"] == "time"


def test_a_time_written_in_other_digits_is_not_a_time():
    """A time is written in ASCII digits (T-114's rule, both engines): a full-width-digit value is no readable time and
    doesn't look like one -- among times it is left out (the field stays a time, must 2); alone it is text."""
    from picks import times
    assert times.instant("２０２６-01-01T00:00:00Z") is None and not times.looks_like("２０２６-01-01T00:00:00Z")
    assert _fields_of(_times(5) + ["２０２６-01-01T00:00:00Z"])["at"]["kind"] == "time"
    f = _fields_of(["２０２６-01-01T00:00:00Z"] * 3 + _times(1))["at"]
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


@pytest.mark.parametrize("first, last, to_end, words", [
    (_dt.date(1800, 1, 1), _dt.date(1937, 6, 1), False, "Times before 1970 can't be read on this clock."),
    (_dt.date(2026, 11, 26), _dt.date(2100, 12, 1), True, "Times from November 2026 on can't be read on this clock."),
    (_dt.date(1800, 1, 1), _dt.date(2027, 1, 1), False, "Times before January 2027 can't be read on this clock."),
    (_dt.date(2026, 9, 20), _dt.date(2027, 3, 1), False, "Times from September 2026 to March 2027 can't be read on this clock."),
])
def test_a_zone_the_clocks_disagree_on_in_some_period_says_which_in_one_line(first, last, to_end, words):
    """T-101: such a zone stays selectable, with the period it can't read."""
    assert zones.note_words(first, last, to_end) == words
    assert "tzdata" not in words and "backzone" not in words and len(words) <= 90
    assert zones.UNKNOWN_WORDS == "Not available: this computer's database doesn't know it."


def test_the_marks_come_from_both_clocks(monkeypatch):
    """Read against the demo's own database with built-in SQL only (no runtime function): UTC
    and Denver agree; a zone whose Python clock is moved an hour from Nov 2026 is marked."""
    from demo.server import db
    conn = db.connect(application_name="autosql-t98-marks")
    try:
        marks = zones.marks(conn, ["UTC", "America/Denver"])
        assert marks == {"UTC": (None, None), "America/Denver": (None, None)}
        real = zones._python_offsets
        monkeypatch.setattr(zones, "_python_offsets", lambda z, ts: [
            o + 3600 if t >= 1793520000 else o for t, o in zip(ts, real(z, ts))])
        moved = zones.marks(conn, ["America/Denver"], cache=False)
        assert moved["America/Denver"] == (None, "Times from November 2026 on can't be read on this clock.")
        assert zones.marks(conn, ["Mars/Olympus"], cache=False)["Mars/Olympus"] == (zones.UNKNOWN_WORDS, None)
    finally:
        conn.rollback()
        conn.close()


def _client():
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    return TestClient(server_app.app)


def test_the_page_gets_the_list_with_each_zones_mark(monkeypatch):
    """T-101: greyed (why) only when the database doesn't know a zone; a period's line (note) else."""
    monkeypatch.setattr(zones, "marks", lambda conn, names, cache=True: {
        z: ((zones.UNKNOWN_WORDS, None) if z == "Europe/Amsterdam"
            else (None, "Times before 1970 can't be read on this clock.") if z == "Europe/Oslo" else (None, None))
        for z in names})
    r = _client().get("/api/dashboard/zones")
    assert r.status_code == 200
    body = r.json()
    by = {e["zone"]: e for e in body["zones"]}
    assert body["zones"][0]["zone"] == "UTC"
    assert by["America/Denver"] == {"zone": "America/Denver", "label": "Denver time", "place": "Denver",
                                     "area": "America", "why": None, "note": None}
    assert by["Europe/Amsterdam"]["why"] == "Not available: this computer's database doesn't know it."
    assert by["Europe/Oslo"]["why"] is None and by["Europe/Oslo"]["note"] == "Times before 1970 can't be read on this clock."
    # every name both engines accept reaches a listed place: listed itself, or by its old name
    others = {e["zone"]: e for e in body["others"]}
    accepted = set(by) | set(body["aliases"]) | set(others)
    assert set(ZONES) <= accepted          # and old names beyond them, aliased to their place (a-chk, T-98 c)
    assert not (set(body["aliases"]) & set(by)) and not (set(others) - set(ZONES))
    assert all(t in by for t in body["aliases"].values())
    # an alias is the same clock under another name, never a guess: UTC-12 is not UTC
    assert body["aliases"].get("Etc/UTC") == "UTC"
    assert "Etc/GMT+12" not in body["aliases"] and others["Etc/GMT+12"]["label"] == "UTC−12"


def test_the_list_is_the_same_for_either_view():
    c = _client()
    a, b = c.get("/api/dashboard/zones"), c.get("/api/dashboard/zones?view=admin")
    assert a.status_code == b.status_code == 200 and a.json() == b.json()


# ═════════════════════════════════════════════════════════════════════════
# b2 · a question's zone, and what a card means on its clock
# ═════════════════════════════════════════════════════════════════════════

from picks import view as pview  # noqa: E402

TS = {"path": "ts", "label": "Time", "kind": "time",
      "ops": ["on", "after", "before", "between", "present", "blank"]}
DUE = {"path": "due_date", "label": "Due date", "kind": "date",
       "ops": ["on", "after", "before", "between", "present", "blank"]}
STATUS = {"path": "status", "label": "Status", "kind": "text", "ops": ["eq", "ne", "in", "present", "blank"]}
DEN = "America/Denver"
TOD = 'time_of_day($.ts, "America/Denver")'


def c(field, op, value="", value2="", **kw):
    return {"field": field, "op": op, "value": value, "value2": value2, "values": [], **kw}


def tod(op, value="", value2=""):
    return c("ts", op, value, value2, part="time_of_day")


@pytest.mark.parametrize("zone, out", [(None, None), (DEN, DEN), ("UTC", "UTC"), ("Etc/GMT+12", "Etc/GMT+12")])
def test_a_questions_zone_is_one_both_engines_read(zone, out):
    v = {} if zone is None else {"zone": zone}
    assert pview.view_zone(v) == out


@pytest.mark.parametrize("zone", ["Mars/Olympus", "america/denver", "EST5EDT", "+05:30", "", 5, ["UTC"], None])
def test_any_other_zone_is_refused_in_words(zone):
    with pytest.raises(pview.ViewError) as e:
        pview.view_zone({"zone": zone})
    assert "time zone" in str(e.value) and "Pick one from the list." in str(e.value)


@pytest.mark.parametrize("cond, zone, expr, words", [
    (c("ts", "on", "2026-08-20"), DEN,
     '$.ts >= "2026-08-20T06:00:00.000000!" and $.ts < "2026-08-21T06:00:00.000000!"', "Time is on Aug 20"),
    (c("ts", "on", "2026-03-08"), DEN,
     '$.ts >= "2026-03-08T07:00:00.000000!" and $.ts < "2026-03-09T06:00:00.000000!"', "Time is on Mar 8"),
    (c("ts", "on", "2026-11-01"), DEN,
     '$.ts >= "2026-11-01T06:00:00.000000!" and $.ts < "2026-11-02T07:00:00.000000!"', "Time is on Nov 1"),
    (c("ts", "on", "2026-08-21"), "Pacific/Kiritimati",
     '$.ts >= "2026-08-20T10:00:00.000000!" and $.ts < "2026-08-21T10:00:00.000000!"', "Time is on Aug 21"),
    (c("ts", "after", "2026-08-20T17:00"), DEN, '$.ts > "2026-08-20T23:00:00.000000Z"', "Time is after Aug 20, 5:00 PM"),
    (c("ts", "before", "2026-11-01T01:30"), DEN, '$.ts < "2026-11-01T07:30:00.000000!"', "Time is before Nov 1, 1:30 AM"),
    (c("ts", "between", "2026-08-20T17:00", "2026-08-20T09:00"), DEN,
     '$.ts >= "2026-08-20T15:00:00.000000!" and $.ts <= "2026-08-20T23:00:00.000000Z"',
     "Time is between Aug 20, 9:00 AM and Aug 20, 5:00 PM"),
    (c("ts", "after", "2026-08-20T23:00:00Z"), DEN,
     '$.ts > "2026-08-20T23:00:00.000000Z"',
     "Time is after Aug 20, 5:00 PM"),
    # no zone: exactly as before T-98
    (c("ts", "on", "2026-08-20"), None,
     '$.ts >= "2026-08-20T00:00:00.000000!" and $.ts < "2026-08-21T00:00:00.000000!"', "Time is on Aug 20"),
    (c("ts", "after", "2026-08-20T17:00"), None, '$.ts > "2026-08-20T17:00:00.000000Z"', "Time is after Aug 20, 17:00 UTC"),
    # a calendar date is its own day, on any clock
    (c("due_date", "on", "2026-09-03"), DEN, '$.due_date == "2026-09-03"', "Due date is on Sep 3, 2026"),
    # time of day
    (tod("from", "17:00"), DEN, f"{TOD} >= 61200", "Time (time of day) from 5:00 PM"),
    (tod("until", "17:00"), DEN, f"{TOD} < 61200", "Time (time of day) until 5:00 PM"),
    (tod("from", "17:00:15"), DEN, f"{TOD} >= 61215", "Time (time of day) from 5:00:15 PM"),
    (tod("between", "22:00", "02:00"), DEN, f"({TOD} >= 79200 or {TOD} < 7200)",
     "Time (time of day) between 10:00 PM and 2:00 AM"),
    (tod("between", "09:00", "17:00"), DEN, f"({TOD} >= 32400 and {TOD} < 61200)",
     "Time (time of day) between 9:00 AM and 5:00 PM"),
    (tod("from", "00:00"), None, 'time_of_day($.ts, "UTC") >= 0', "Time (time of day) from 12:00 AM"),
])
def test_a_card_means_this_on_the_questions_clock(cond, zone, expr, words):
    field = {"ts": TS, "due_date": DUE}[cond["field"]]
    assert pview.condition(field, cond, zone) == (expr, words)


@pytest.mark.parametrize("field, cond, words", [
    (TS, c("ts", "after", "2026-03-08T02:30"),
     "2:30 AM doesn't happen on Mar 8 in Denver time: the clocks go forward an hour."),
    (TS, tod("between", "17:00", "17:00"), "Pick two different times for Time (time of day)."),
    (TS, tod("from", "24:00"), "A time of day is picked as hours and minutes, such as 17:00."),
    (TS, tod("from", "5pm"), "A time of day is picked as hours and minutes, such as 17:00."),
    (TS, tod("from", 61200), "A time of day is picked as hours and minutes, such as 17:00."),
    (TS, tod("eq", "17:00"), "Time (time of day) can't be matched that way."),
    (TS, tod("on", "2026-08-20"), "Time (time of day) can't be matched that way."),
    (TS, tod("from", "17:00", "18:00"), "“Time (time of day) from” takes no second value."),
    (TS, c("ts", "on", "2026-08-20", part="date"), "A condition reads a field, or a time field's time of day."),
    (DUE, {**c("due_date", "from", "17:00"), "part": "time_of_day"}, "Due date has no time of day."),
    (STATUS, {**c("status", "from", "17:00"), "part": "time_of_day"}, "Status has no time of day."),
])
def test_a_card_its_clock_cant_read_is_refused_in_words(field, cond, words):
    with pytest.raises(pview.ViewError) as e:
        pview.condition(field, cond, DEN)
    assert str(e.value) == words


def test_the_tree_and_its_count_columns_read_the_questions_zone():
    fields = {"ts": TS, "status": STATUS}
    v = {"zone": DEN, "filter": {"version": 1, "join": "all", "items": [
        c("ts", "on", "2026-08-20"), tod("from", "17:00")]}}
    assert pview.filter_expression(v, fields) == (
        f'($.ts >= "2026-08-20T06:00:00.000000!" and $.ts < "2026-08-21T06:00:00.000000!") and ({TOD} >= 61200)')
    assert pview.filter_words(v, fields) == "Time is on Aug 20 and Time (time of day) from 5:00 PM"


@pytest.mark.parametrize("text, zone, words", [
    ("2026-08-20T23:00:00Z", DEN, "Aug 20, 5:00 PM"), ("2026-08-21T05:59:59Z", DEN, "Aug 20, 11:59:59 PM"),
    ("2026-08-20T23:00:00Z", "UTC", "Aug 20, 11:00 PM"), ("2026-08-20T23:00:00Z", None, "Aug 20, 23:00 UTC"),
    ("2026-08-20", DEN, "2026-08-20"),
])
def test_a_time_reads_on_the_questions_clock(text, zone, words):
    assert pview.fmt_time(text, zone) == words


# ── b2 through the page, on the demo's own data (no runtime function needed) ──

def _ask(c, v, admin=True):
    r = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    return r.status_code, r.json()


def _hb(setup_json, **kw):
    d = next(x for x in setup_json["datasets"] if x["id"] == "heartbeats")
    v = {"dataset": "heartbeats", "columns": list(d["default_columns"]), "sort": None, "show": None,
         "summary": None}
    v.update(kw)
    return v


def _tree(*items):
    return {"version": 1, "join": "all", "items": list(items)}


@pytest.fixture(scope="module")
def page():
    c = _client()
    return c, c.get("/api/dashboard/setup?view=admin").json()


def _hand(where: str) -> int:
    from demo.server import db
    conn = db.connect(application_name="autosql-t98-hand")
    try:
        return conn.execute("SELECT count(*) FROM demo.records WHERE collection = 'noun:Heartbeat' AND "
                            + where).fetchone()[0]
    finally:
        conn.rollback()
        conn.close()


def test_the_setup_names_the_time_of_day_conditions(page):
    _, st = page
    assert st["time_of_day_ops"] == ["from", "until", "between"]
    assert set(st["time_of_day_labels"]) == {"from", "until", "between"}


def test_aug_20_in_denver_is_denvers_day_and_the_rows_read_on_its_clock(page):
    c, st = page
    want = _hand("data->>'ts' >= '2026-08-20T06:00:00Z' AND data->>'ts' < '2026-08-21T06:00:00Z'")
    code, a = _ask(c, _hb(st, zone=DEN, filter=_tree(c_("ts", "on", "2026-08-20"))))
    assert code == 200 and a["admin"]["verdict"] == "agree", a
    assert a["total"] == want == 900
    assert "where Time is on Aug 20 (Denver time)" in a["sentence"], a["sentence"]
    t = a["columns"].index("Time") if "columns" in a and "Time" in a["columns"] else 1
    assert any(row[t] == "Aug 20, 5:00 PM" for row in a["rows"]), a["rows"][:3]


def test_the_same_day_in_utc_moves_the_rows(page):
    c, st = page
    want = _hand("data->>'ts' >= '2026-08-20T00:00:00Z' AND data->>'ts' < '2026-08-21T00:00:00Z'")
    code, a = _ask(c, _hb(st, zone="UTC", filter=_tree(c_("ts", "on", "2026-08-20"))))
    assert code == 200 and a["total"] == want == 1200
    assert "where Time is on Aug 20 (UTC)" in a["sentence"], a["sentence"]


def test_a_question_without_a_zone_reads_as_before(page):
    c, st = page
    code, a = _ask(c, _hb(st, filter=_tree(c_("ts", "on", "2026-08-20"))))
    assert code == 200 and a["total"] == 1200
    assert "where Time is on Aug 20," in a["sentence"] or a["sentence"].endswith("1,200 rows"), a["sentence"]
    assert "(UTC)" not in a["sentence"]


def test_an_unknown_zone_is_refused_in_words(page):
    c, st = page
    code, a = _ask(c, _hb(st, zone="Mars/Olympus"))
    assert code == 422 and a["message"] == "This page doesn't know the time zone “Mars/Olympus”. Pick one from the list."


def test_a_zone_the_clocks_disagree_on_only_long_ago_answers_a_question_about_now(page):
    """T-101: Amsterdam's clocks differ on this machine only before 1937; Aug 20 there (UTC+2) is
    answered: 24 hours of Heartbeats, by hand. (Its day is two instants worked out in Python, so no
    row's clock is read in the database at all.)"""
    c, st = page
    code, a = _ask(c, _hb(st, zone="Europe/Amsterdam", filter=_tree(c_("ts", "on", "2026-08-20"))))
    assert code == 200, a
    assert a["total"] == _hand("data->>'ts' >= '2026-08-19T22:00:00Z' AND data->>'ts' < '2026-08-20T22:00:00Z'") == 1200


def test_the_guards_refusal_reaches_the_page_in_words(page, monkeypatch):
    from demo.server import dashboard

    class Refused(Exception):
        sqlstate = "XPR05"

    def guard(*a, **k):
        raise Refused("time zone America/Edmonton: this database's clock differs from the evaluator's on "
                      "2026-11-02, a time this question reads")
    monkeypatch.setattr(dashboard, "answer", guard)
    c, st = page
    code, a = _ask(c, _hb(st, zone="America/Edmonton"))
    assert code == 422 and a["message"] == (
        "Edmonton time can't read these times: this computer and its database disagree about "
        "Edmonton's clocks on Nov 2, 2026, and this question reads a time from then.")


def c_(field, op, value="", value2="", **kw):
    return c(field, op, value, value2, **kw)


def test_a_boards_sentence_names_the_clock_too(page):
    c, st = page
    sb = {"by": "sender_id", "count_from": None, "counts": [], "time": None, "measure": None, "sort": None}
    code, a = _ask(c, _hb(st, zone=DEN, columns=[], filter=_tree(c_("ts", "on", "2026-08-20")), scoreboard=sb))
    assert code == 200, a
    assert "where Time is on Aug 20 (Denver time)" in a["sentence"], a["sentence"]


def test_a_summary_per_day_names_the_clock_its_days_are_on(page):
    """T-100 (superseding T-98's interim "(UTC)" note): a summary's days are cut on the question's
    clock, and the sentence names that clock once."""
    c, st = page
    code, a = _ask(c, _hb(st, zone=DEN, columns=[], summary={"fn": "count", "field": None, "per": "day"}))
    assert code == 200, a
    assert a["sentence"].startswith("Number of Heartbeats, per day (Denver time)"), a["sentence"]
    code, a = _ask(c, _hb(st, zone="UTC", columns=[], summary={"fn": "count", "field": None, "per": "day"}))
    assert a["sentence"].startswith("Number of Heartbeats, per day (UTC)"), a["sentence"]


@pytest.mark.parametrize("zone, start, end", [
    (DEN, "2026-08-20T06:00:00Z", "2026-08-21T06:00:00Z"),
    ("UTC", "2026-08-20T00:00:00Z", "2026-08-21T00:00:00Z"),
])
def test_a_count_column_reads_its_questions_clock(page, zone, start, end):
    from demo.server import db
    conn = db.connect(application_name="autosql-t98-count")
    try:
        want = dict(conn.execute(
            "SELECT data->>'sender_id', count(*) FILTER (WHERE data->>'ts' >= %(a)s AND data->>'ts' < %(b)s)"
            " FROM demo.records WHERE collection = 'noun:Heartbeat' GROUP BY 1", {"a": start, "b": end}).fetchall())
    finally:
        conn.rollback()
        conn.close()
    c, st = page
    count = {"label": "On Aug 20", "pct": False, "filter": _tree(c_("ts", "on", "2026-08-20"))}
    v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": None, "summary": None, "zone": zone,
         "scoreboard": {"by": "sender_id", "counts": [count]}}
    code, a = _ask(c, v)
    assert code == 200 and a["admin"]["verdict"] == "agree", a
    ids = [col["id"] for col in a["columns"]]
    got = {r[ids.index("group")]: int(r[ids.index("count:1")]) for r in a["rows"]}
    assert got == want and set(want.values()) == {18 if zone == DEN else 24}, (got, want)


# ── every compile path gets the zone list (a-chk's MEDIUM on b1) ─────────────

#: time_of_day inside every kind of operand a probe compiles: arithmetic, the
#: functions whose argument is a number, coalesce, if, a negation, an equality.
PROBED = [
    'time_of_day($.ts, "UTC") * 2 > 100',
    'coalesce(time_of_day($.ts, "UTC"), 0) > 5',
    'abs(time_of_day($.ts, "America/Denver") - 43200) < 3600',
    '-time_of_day($.ts, "UTC") < 0',
    'if(time_of_day($.ts, "UTC") > 0, time_of_day($.ts, "UTC"), 1) / 60 > 1',
    'time_of_day($.ts, "UTC") + $.payload.load > 61200',
    'min(time_of_day($.ts, "UTC"), 7200) == 7200',
    'time_of_day($.ts, "UTC") / 3600 == 17',
]


D_UTC = ((-float("inf"), -2208988800.0),)    # a D by hand: before 1900


@pytest.mark.parametrize("src", PROBED)
def test_a_probe_reads_the_clock_checked_as_the_statement_does(src):
    """T-101: a probed operand's clock is read through the same D as the statement's."""
    from picks import probes
    with _gaps(UTC=D_UTC, America_Denver=D_UTC):
        built = probes.build_probes([EXPR.parse(src)])
    assert built, "this expression has an operand a probe asks about"
    assert any("time_of_day" in p.sql for p in built)
    for p in built:
        if "time_of_day" in p.sql:
            assert p.sql.count("xpr.time_of_day(") == p.sql.count("::float8[]"), p.sql


@pytest.mark.parametrize("src", PROBED)
def test_the_statement_compiles_it_too(src):
    with _gaps(UTC=D_UTC, America_Denver=D_UTC):
        built = builder.build(_pick(src), ["ts", "payload"])
    assert built.sql.count("xpr.time_of_day(") == built.sql.count("::float8[]") > 0


# ── the suite says whether the database runs this tree's runtime ─────────────

class _Reporter:
    def __init__(self):
        self.lines = []

    def write_line(self, text, **kw):
        self.lines.append(text)

    def write_sep(self, sep, text, **kw):
        self.lines.append(f"{sep * 8} {text}")


def _conftest():
    import importlib.util
    spec = importlib.util.spec_from_file_location("t98_conftest", Path(__file__).with_name("conftest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_seat_whose_runtime_is_the_databases_sees_one_quiet_line():
    ct = _conftest()
    ct._RUNTIME.update(state="same", words="the database runs demo/vendor/runtime.sql (27 functions, as written)")
    r = _Reporter()
    ct._say_runtime(r)
    assert r.lines == ["runtime check: the database runs demo/vendor/runtime.sql (27 functions, as written)"]


def test_a_seat_whose_runtime_differs_is_told_loudly_which_and_how_to_fix_it():
    ct = _conftest()
    ct._RUNTIME.update(state="differs", words="the database does NOT run demo/vendor/runtime.sql — differs: xpr.truthy")
    r = _Reporter()
    ct._say_runtime(r)
    assert "RUNTIME CHECK: THE DATABASE IS NOT RUNNING THIS TREE'S RUNTIME" in r.lines[0]
    assert r.lines[1] == "the database does NOT run demo/vendor/runtime.sql — differs: xpr.truthy."
    assert "./run-demo up" in r.lines[2]


def test_every_frontend_source_is_in_the_bundles_digest():
    """The stale-bundle check (test_ui's _UI_SOURCES, build.mjs's SOURCES) only sees the files it
    lists: a source missing from it can change without the suite noticing (T-96 found one; T-98's
    clock was the next). Every .jsx / .js under demo/frontend is listed."""
    import test_ui
    on_disk = sorted(str(p.relative_to(test_ui._REPO_ROOT)) for p in (test_ui._REPO_ROOT / "demo" / "frontend").iterdir()
                     if p.suffix in (".jsx", ".js") and p.is_file())
    missing = [p for p in on_disk if p not in test_ui._UI_SOURCES]
    assert not missing, f"not in the bundles' digest: {missing}"


@pytest.mark.parametrize("old, now", [
    ("Asia/Calcutta", "Asia/Kolkata"), ("Asia/Katmandu", "Asia/Kathmandu"), ("Asia/Saigon", "Asia/Ho_Chi_Minh"),
    ("America/Buenos_Aires", "America/Argentina/Buenos_Aires"), ("Europe/Kiev", "Europe/Kyiv"),
    ("Asia/Rangoon", "Asia/Yangon"), ("America/Godthab", "America/Nuuk"),
])
def test_a_browser_that_names_its_zone_the_old_way_reaches_its_place(old, now):
    """a-chk: such a computer got UTC and "isn't one this page knows". tzdata's links (its `backward`
    names) alias to the current name, which is what the question stores and both engines read."""
    body = _client().get("/api/dashboard/zones").json()
    assert body["aliases"].get(old) == now, (old, body["aliases"].get(old))
    assert now in {e["zone"] for e in body["zones"]}
