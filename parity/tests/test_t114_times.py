"""T-114: the times GIMS writes read as times -- one strict rule, both engines and the setup.

A stored time is READABLE when it is ``YYYY-MM-DD``, ``T`` or a space, ``HH:MM:SS``, 1-6 fraction digits, and ``Z``,
``+-HH:MM`` or ``+-HHMM`` (an offset of at most 14:59), on a real day, its UTC instant inside years 1..9999
(spec §2.1); a bare date reads as its UTC midnight (T-88). Read, it is that instant: compared at one fixed width
(``YYYY-MM-DDTHH:MM:SS.ffffffZ``), labelled in the engine's one fixed form. Anything else -- naive, lowercase, 7+
digits, an offset with seconds, hour 24, a year the instant leaves -- is no readable time: in no bucket (left out,
counted), matching no condition (negated ones included), sorted last; still present, never blank.

A field is a time field when every non-blank value is text, at least one is a readable time and more than half look
like a time (§2.4; exactly half is text).

The tests: the rule's hand truth (Python and SQL), the 250,000-string differential of the two readers, the setup's
counts, both engines' buckets, conditions and sort against hand truth, the second engine alone on GIMS's text (its
SQLite shape), and the dashboard on a scratch copy of the seed. The ones that need Postgres SKIP without
AUTOSQL_PARITY_DSN.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401  (the engine, registered)
from picks import builder, env, view as pview, zones  # noqa: E402
from picks.pyrunner import rows as pyrows, shape as pyshape  # noqa: E402
from picks.records import Records  # noqa: E402

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres")
T, TABLE = "noun:T", "t114v"
KEYS = ["when", "s", "note"]
DENVER = "America/Denver"


def _times():
    from picks import times
    return times


# ── the rule's hand truth: each string → its UTC instant to the microsecond, or no readable time ──
HAND = [
    ("2026-07-09T05:03:48Z", "2026-07-09T05:03:48.000000Z"),
    ("2026-07-09T05:03:48+00:00", "2026-07-09T05:03:48.000000Z"),
    ("2026-07-09T05:03:48.123456+00:00", "2026-07-09T05:03:48.123456Z"),
    ("2026-07-09T05:03:48.5+00:00", "2026-07-09T05:03:48.500000Z"),              # +00:00 with 1 and 3 digits
    ("2026-07-09T05:03:48.123+00:00", "2026-07-09T05:03:48.123000Z"),
    ("2026-07-09T05:03:48.123Z", "2026-07-09T05:03:48.123000Z"),
    ("2026-07-09T05:03:48.1Z", "2026-07-09T05:03:48.100000Z"),
    ("2026-07-09T05:03:48.000000Z", "2026-07-09T05:03:48.000000Z"),
    ("2026-07-09T05:03:48-0600", "2026-07-09T11:03:48.000000Z"),
    ("2026-07-09T05:03:48+0530", "2026-07-08T23:33:48.000000Z"),
    ("2026-07-09T23:30:00-06:00", "2026-07-10T05:30:00.000000Z"),
    ("2026-07-09T05:03:48-00:00", "2026-07-09T05:03:48.000000Z"),
    ("2026-07-09T05:03:48+14:00", "2026-07-08T15:03:48.000000Z"),
    ("2026-07-09T05:03:48-12:00", "2026-07-09T17:03:48.000000Z"),
    ("2026-07-09T05:03:48+14:59", "2026-07-08T14:04:48.000000Z"),
    ("2026-07-09 05:03:48+00:00", "2026-07-09T05:03:48.000000Z"),
    ("2026-01-31T23:59:59.999999-07:00", "2026-02-01T06:59:59.999999Z"),
    ("2028-02-29T05:03:48Z", "2028-02-29T05:03:48.000000Z"),
    ("2000-02-29T00:00:00Z", "2000-02-29T00:00:00.000000Z"),
    ("2026-03-08T02:30:00-07:00", "2026-03-08T09:30:00.000000Z"),
    ("0001-01-01T00:00:00Z", "0001-01-01T00:00:00.000000Z"),
    ("9999-12-31T23:59:59.999999Z", "9999-12-31T23:59:59.999999Z"),
    ("9999-12-31T22:59:59.999999-01:00", "9999-12-31T23:59:59.999999Z"),
    ("0001-01-01T00:59:00+00:59", "0001-01-01T00:00:00.000000Z"),
    ("2026-07-09", "2026-07-09T00:00:00.000000Z"),                      # a bare date: its UTC midnight (T-88)
    ("2026-07-09T05:03:48+15:00", None),
    ("2026-07-09T05:03:48+23:59", None),
    ("2026-07-09t05:03:48z", None),
    ("2026-07-09T05:03:48z", None),
    ("2026-07-09t05:03:48Z", None),
    ("2026-07-09T05:03:48.1234567Z", None),
    ("2026-07-09T05:03:48.9999995Z", None),
    ("2026-07-09T05:03:48+05:30:15", None),
    ("2026-07-09T05:03:48+05", None),
    ("2026-07-09T05:03Z", None),
    ("2026-07-09T05:03", None),
    ("2026-07-09 05:03:48", None),
    ("2026-07-09T05:03:48", None),
    ("2026-07-09T24:00:00Z", None),
    ("2026-07-09T05:03:60Z", None),
    ("2026-02-29T05:03:48Z", None),
    ("2100-02-29T00:00:00Z", None),
    ("2026-06-31T00:00:00Z", None),
    ("2026-13-01T00:00:00Z", None),
    ("2026-00-10T00:00:00Z", None),
    ("0001-01-01T00:30:00+01:00", None),
    ("0001-01-01T00:30:00+00:31", None),
    ("9999-12-31T23:30:00-01:00", None),
    ("0000-12-31T23:59:59Z", None),
    (" 2026-07-09T05:03:48Z", None),
    ("2026-07-09T05:03:48Z ", None),
    ("2026-07-09T05:03:48,5Z", None),
    ("20260709T050348Z", None),
    ("+2026-07-09T05:03:48Z", None),
    ("２０２６-07-09T05:03:48Z", None),
    ("2026-07-09T05:03:48+00", None),
    ("2026-02-30", None),
    ("not a time", None),
    ("", None),
]

#: what looks like a time (§2.3): it decides whether a field is a time field, read or not
LOOKS = [
    ("2026-07-09T05:03:48Z", True), ("2026-07-09T05:03", True), ("2026-07-09 05:03:48", True),
    ("2026-07-09t05:03:48z", True), ("2026-07-09T05:03:48.1234567Z", True), ("2026-07-09T05:03:48+05:30:15", True),
    ("2026-07-09T24:00:00Z", True), ("2026-02-30T00:00:00Z", True), ("2026-07-09", True),
    ("2026-07-09T05:03:48-0600", True), ("2026-07-09T05:03:48,5Z", True),
    (" 2026-07-09T05:03:48Z", False), ("20260709T050348Z", False), ("not a time", False), ("", False),
    ("２０２６-07-09T05:03:48Z", False), ("2026-07-09 is the day", False),
]

#: the field kind, both directions (§2.4): values → the kind the setup gives
KIND_CASES = {
    "one readable, one junk: exactly half is text": (["2026-07-09T05:03:48Z", "n/a"], "text"),
    "two readable, one junk: a time field": (["2026-07-09T05:03:48Z", "2026-07-10T05:03:48+00:00", "n/a"], "time"),
    "one readable, nine naive: a time field": (["2026-07-09T05:03:48Z"] + ["2026-07-09T05:03"] * 9, "time"),
    "free text with one readable time among three words": (["fine", "late", "2026-07-09T05:03:48Z", "ok"], "text"),
    "only naive times: text": (["2026-07-09T05:03", "2026-07-09 05:03:48"], "text"),
    "blank strings are not counted": (["2026-07-09T05:03:48Z", "", "", "", "n/a", "2026-07-10T00:00:00Z"], "time"),
    "dates and times: a time field": (["2026-07-09", "2026-07-10", "2026-07-11T05:03:48+00:00"], "time"),
    "dates only: a date field": (["2026-07-09", "2026-07-10"], "date"),
    "GIMS's mix: +00:00 whole and 6 digits, Z": (["2026-07-09T05:03:48+00:00", "2026-07-09T05:03:48.123456+00:00",
                                                  "2026-07-09T05:03:48Z"], "time"),
    "the old form alone: a time field, as before": (["2026-08-14T00:00:00Z", "2026-08-20T23:00:00Z"], "time"),
}


@pytest.mark.parametrize("text, want", HAND)
def test_the_rule_in_python(text, want):
    t = _times()
    got = t.instant(text)
    assert (t.utc_text(got) if got is not None else None) == want, (text, got)


@pytest.mark.parametrize("text, want", LOOKS)
def test_what_looks_like_a_time(text, want):
    assert _times().looks_like(text) is want, text


@pytest.mark.parametrize("case", list(KIND_CASES))
def test_the_field_kind_both_directions(case):
    values, want = KIND_CASES[case]
    assert pview._kind({"string"}, _times().kind_counts(values)) == want, (case, _times().kind_counts(values))


def test_a_number_among_the_strings_is_mixed_and_a_reading_keeps_present_apart_from_blank():
    t = _times()
    assert pview._kind({"string", "number"}, t.kind_counts(["2026-07-09T05:03:48Z"])) == "mixed"
    assert t.reading("2026-07-09T05:03:48+00:00") == "2026-07-09T05:03:48.000000Z"
    assert t.reading("2026-07-09T05:03") is False and t.reading(5) is False and t.reading("") is False
    assert t.reading(None) is None


# ── the rows both engines read: their stored times and, by hand, each one's UTC instant and Denver day ──
#: key → (stored "when" (MISSING: no field), its UTC instant by hand or None, its day on Denver's clock or None)
MISSING = object()
ROWS = {
    "a1": ("2026-07-09T23:30:00-06:00", "2026-07-10T05:30:00.000000Z", "2026-07-09"),
    "a2": ("2026-07-09T23:59:59.999999Z", "2026-07-09T23:59:59.999999Z", "2026-07-09"),
    "a3": ("2026-07-10T00:00:00Z", "2026-07-10T00:00:00.000000Z", "2026-07-09"),
    "a4": ("2026-07-09T05:03:48+00:00", "2026-07-09T05:03:48.000000Z", "2026-07-08"),
    "a5": ("2026-07-09T05:03:48.123456+00:00", "2026-07-09T05:03:48.123456Z", "2026-07-08"),
    "a6": ("2026-07-09 12:00:00+00:00", "2026-07-09T12:00:00.000000Z", "2026-07-09"),
    "a7": ("2026-07-09T12:00:00-0600", "2026-07-09T18:00:00.000000Z", "2026-07-09"),
    "a8": ("2026-07-09T12:00:00-00:00", "2026-07-09T12:00:00.000000Z", "2026-07-09"),
    "a9": ("2026-07-10T01:00:00+14:00", "2026-07-09T11:00:00.000000Z", "2026-07-09"),
    "a10": ("2026-07-09T01:00:00-12:00", "2026-07-09T13:00:00.000000Z", "2026-07-09"),
    "m1": ("2026-01-31T23:59:59.999999-07:00", "2026-02-01T06:59:59.999999Z", "2026-01-31"),
    "m2": ("2028-02-29T12:00:00Z", "2028-02-29T12:00:00.000000Z", "2028-02-29"),
    "u1": ("2026-07-09T05:03:48+15:00", None, None),
    "u2": ("2026-07-09T05:03:48.1234567Z", None, None),
    "u3": ("2026-07-09t05:03:48z", None, None),
    "u4": ("2026-07-09T05:03:48+05:30:15", None, None),
    "u5": ("2026-07-09T05:03", None, None),
    "u6": ("2026-07-09 05:03:48", None, None),
    "u7": ("2026-07-09T24:00:00Z", None, None),
    "u8": ("0001-01-01T00:30:00+01:00", None, None),
    "b1": (None, None, None),
    "b2": (MISSING, None, None),
}
READ = {k: v[1] for k, v in ROWS.items() if v[1]}
UNREADABLE = [k for k, v in ROWS.items() if v[0] not in (None, MISSING) and not v[1]]


def _doc(k):
    stored = ROWS[k][0]
    d = {"s": "y" if k in ("a1", "a4", "u1", "b1") else "x"}
    if stored is not MISSING:
        d["when"] = stored
    return d


def _records(alone=False):
    return Records(table=TABLE, sources={T: ", ".join(KEYS)})


def _pick(**kw):
    p = {"source": T, "computed": [], "filter": None, "sort": None, "cap": None, "window": None,
         "changed": False, "bucket": "off", "aggregate": None}
    p.update(kw)
    return p


def _bucket_pick(per, zone=None, field="when"):
    p = _pick(aggregate={"fn": "count", "field": None}, bucket=per, bucket_field=field)
    if zone:
        p["bucket_zone"] = zone
    return p


#: the field the view's conditions read, as the setup gives it
WHEN = {"path": "when", "label": "When", "kind": "time", "ops": ["on", "after", "before", "between", "present", "blank"]}
S = {"path": "s", "label": "S", "kind": "text", "ops": ["eq", "ne", "in", "present", "blank"]}
FIELDS = {"when": WHEN, "s": S}


def _filter_pick(items, join="all", zone=None, **kw):
    """The view's own filter for these cards, as the dashboard and GIMS build it, and the time fields it reads."""
    holder = {"filter": {"version": pview.FILTER_VERSION, "join": join, "items": items}}
    expr, _words = pview.filter_parts(holder, FIELDS, zone=zone)
    # 6dd0eb8 -- 4d93236 had no such reading: there the view's text comparison stands, as it did
    read = getattr(pview, "time_fields_read", lambda _h, _f: [])
    return _pick(filter=expr, times=read(holder, FIELDS), **kw)


def _gims_text(doc) -> str:
    """GIMS's served text for one stored record (its SQLite shape: str(Decimal) re-dump; times are text, unchanged)."""
    return json.dumps(doc)


def _py(pick, text=_gims_text, keys=None):
    rows = [pyrows.source_row(T, k, text(_doc(k))) for k in sorted(keys or ROWS)]
    return pyshape.answer(rows, pick, _records())["rows"]


# ── the second engine alone, on GIMS's text (its SQLite shape): every reading against the hand truth ──

def _per_day_hand(zone=None):
    out = {}
    for k, (_s, utc, denver) in ROWS.items():
        if utc:
            day = (denver if zone else utc[:10])
            label = f"{day}T00:00:00" + ("" if zone else "Z")
            out[label] = out.get(label, 0) + 1
    return out


@pytest.mark.parametrize("zone", [None, DENVER])
def test_the_second_engine_alone_buckets_every_readable_time_by_its_instant(zone):
    got = {r["bucket"]: int(r["agg"]) for r in _py(_bucket_pick("day", zone))}
    assert got == _per_day_hand(zone), got
    kept = int(_py(_pick(aggregate={"fn": "count", "field": None}))[0]["agg"])
    assert kept - sum(got.values()) == len(UNREADABLE) + 2          # left out: unreadable, blank, missing


def test_the_last_instant_of_a_week_and_a_month_is_in_it():
    rows = {"w1": "2026-07-12T23:59:59.999999Z", "w2": "2026-07-13T00:00:00Z",
            "w3": "2026-07-31T23:59:59.999999+00:00", "w4": "2026-08-01T00:00:00-00:00"}
    src = [pyrows.source_row(T, k, json.dumps({"when": v})) for k, v in rows.items()]
    weeks = {r["bucket"]: int(r["agg"]) for r in pyshape.answer(src, _bucket_pick("week"), _records())["rows"]}
    months = {r["bucket"]: int(r["agg"]) for r in pyshape.answer(src, _bucket_pick("month"), _records())["rows"]}
    assert weeks == {"2026-07-06T00:00:00Z": 1, "2026-07-13T00:00:00Z": 1, "2026-07-27T00:00:00Z": 2}, weeks
    assert months == {"2026-07-01T00:00:00Z": 3, "2026-08-01T00:00:00Z": 1}, months


#: DST on Denver's clock, per hour: by hand
DST = {"d1": "2026-03-08T08:30:00Z", "d2": "2026-03-08T09:30:00Z", "d3": "2026-03-08T02:30:00-07:00",
       "d4": "2026-11-01T07:30:00Z", "d5": "2026-11-01T08:30:00Z", "d6": "2026-11-01T01:30:00-07:00",
       "d7": "2026-11-01T01:30:00-06:00"}
DST_HAND = {"2026-03-08T01:00:00": 1, "2026-03-08T03:00:00": 2, "2026-11-01T01:00:00": 4}


def test_dst_on_the_questions_clock_per_hour():
    src = [pyrows.source_row(T, k, json.dumps({"when": v})) for k, v in DST.items()]
    got = {r["bucket"]: int(r["agg"]) for r in pyshape.answer(src, _bucket_pick("hour", DENVER), _records())["rows"]}
    assert got == DST_HAND, got


#: a board's latest / earliest of a time field (T-114: by instant, in the engine's fixed form to the second), by hand
BOARD = {"source": T, "group": "s", "filter": None, "counts": [], "time": {"fn": "max", "field": "when"},
         "measure": None, "sort": None, "cap": None, "count_times": ["when"]}
BOARD_HAND = {"max": {"x": "2028-02-29T12:00:00Z", "y": "2026-07-10T05:30:00Z"},
              "min": {"x": "2026-02-01T06:59:59Z", "y": "2026-07-09T05:03:48Z"}}


@pytest.mark.parametrize("fn", ["max", "min"])
def test_the_second_engine_alone_reads_a_boards_latest_and_earliest_by_instant(fn):
    from picks.pyrunner import group as pygroup
    rows = [pyrows.source_row(T, k, _gims_text(_doc(k))) for k in sorted(ROWS)]
    got = {r["grp"]: r["time"] for r in pygroup.answer(rows, dict(BOARD, time={"fn": fn, "field": "when"}), (),
                                                         _records())["rows"]}
    assert got == BOARD_HAND[fn], got


#: a time whose reading on a clock leaves year 1 is in no bucket, on both engines (Python's datetime holds no year 0)
YEARS = {"e1": "0001-01-02T00:00:00+14:59", "e2": "0001-01-03T12:00:00Z"}
YEARS_HAND = {"0001-01-03T00:00:00": 1}


def test_the_second_engine_alone_leaves_a_clock_reading_before_year_1_out():
    src = [pyrows.source_row(T, k, json.dumps({"when": v})) for k, v in YEARS.items()]
    got = {r["bucket"]: int(r["agg"]) for r in pyshape.answer(src, _bucket_pick("day", "Etc/GMT+12"), _records())["rows"]}
    assert got == YEARS_HAND, got


#: the view's conditions over ROWS, and by hand the keys each keeps
CONDITIONS = {
    "on Jul 9 (UTC)": ([{"field": "when", "op": "on", "value": "2026-07-09"}], "all", None,
                       {k for k, v in READ.items() if v[:10] == "2026-07-09"}),
    "on Jul 9 (Denver)": ([{"field": "when", "op": "on", "value": "2026-07-09"}], "all", DENVER,
                          {k for k in READ if ROWS[k][2] == "2026-07-09"}),
    "after 05:03:48 UTC": ([{"field": "when", "op": "after", "value": "2026-07-09T05:03:48Z"}], "all", None,
                           {k for k, v in READ.items() if v > "2026-07-09T05:03:48.000000Z"}),
    "before 05:03:48 UTC": ([{"field": "when", "op": "before", "value": "2026-07-09T05:03:48Z"}], "all", None,
                            {k for k, v in READ.items() if v < "2026-07-09T05:03:48.000000Z"}),
    "between 05:03:48 and 12:00 UTC": ([{"field": "when", "op": "between", "value": "2026-07-09T05:03:48Z",
                                        "value2": "2026-07-09T12:00:00Z"}], "all", None,
                                       {k for k, v in READ.items()
                                        if "2026-07-09T05:03:48.000000Z" <= v <= "2026-07-09T12:00:00.000000Z"}),
    "a day's last microsecond, inclusive (GIMS's day end)": (
        [{"field": "when", "op": "between", "value": "2026-07-09T00:00:00Z",
          "value2": "2026-07-09T23:59:59.999999Z"}], "all", None,
        {k for k, v in READ.items() if v[:10] == "2026-07-09"}),
    "present: an unreadable value is present": ([{"field": "when", "op": "present"}], "all", None,
                                                set(READ) | set(UNREADABLE)),
    "blank: never an unreadable value": ([{"field": "when", "op": "blank"}], "all", None, {"b1", "b2"}),
    "time of day from 05:00 UTC: no naive one": (
        [{"field": "when", "part": "time_of_day", "op": "from", "value": "05:00"}], "all", None,
        {k for k, v in READ.items() if v[11:16] >= "05:00"}),
    # ruling 3: negated, an unreadable time matches nothing; a blank keeps today's meaning (it holds no time: false)
    "all or none (after X, S is y): no unreadable row": (
        [{"field": "when", "op": "after", "value": "2026-07-09T05:03:48Z"}, {"field": "s", "op": "eq", "value": "y"}],
        "allnone", None,
        {k for k in READ if (READ[k] > "2026-07-09T05:03:48.000000Z") == (_doc(k)["s"] == "y")} | {"b2"}),
    "exactly one (before X, S is y): no unreadable row": (
        [{"field": "when", "op": "before", "value": "2026-07-09T05:03:48Z"}, {"field": "s", "op": "eq", "value": "y"}],
        "one", None,
        {k for k in READ if (READ[k] < "2026-07-09T05:03:48.000000Z") != (_doc(k)["s"] == "y")} | {"b1"}),
    "all or none of a group (any(not-between)) and S: no unreadable row": (
        [{"join": "any", "items": [{"field": "when", "op": "before", "value": "2026-07-09T05:03:48Z"},
                                   {"field": "when", "op": "after", "value": "2026-07-09T12:00:00Z"}]},
         {"field": "s", "op": "eq", "value": "y"}], "allnone", None,
        {k for k in READ if (not ("2026-07-09T05:03:48.000000Z" <= READ[k] <= "2026-07-09T12:00:00.000000Z"))
         == (_doc(k)["s"] == "y")} | {"b2"}),
}


@pytest.mark.parametrize("case", list(CONDITIONS))
def test_the_second_engine_alone_compares_instants_and_an_unreadable_time_matches_nothing(case):
    items, join, zone, want = CONDITIONS[case]
    got = {r["key"] for r in _py(_filter_pick(items, join, zone))}
    assert got == want, (case, sorted(got ^ want))


#: ruling 2: a time field sorts by its instant; an unreadable value last in both directions (with the missing, by
#: key); a JSON-null blank keeps its place (first ascending, after the times descending)
SORT_DESC = ["m2", "a1", "a3", "a2", "a7", "a10", "a6", "a8", "a9", "a5", "a4", "m1", "b1",
             "b2", "u1", "u2", "u3", "u4", "u5", "u6", "u7", "u8"]
SORT_ASC = ["b1", "m1", "a4", "a5", "a9", "a6", "a8", "a10", "a7", "a2", "a3", "a1", "m2",
            "b2", "u1", "u2", "u3", "u4", "u5", "u6", "u7", "u8"]


@pytest.mark.parametrize("direction, want", [("desc", SORT_DESC), ("asc", SORT_ASC)])
def test_the_second_engine_alone_sorts_a_time_field_by_its_instant_and_caps_it(direction, want):
    pick = _filter_pick([], sort={"field": "$.when", "dir": direction}, cap=8)
    pick["times"] = ["when"]
    assert [r["key"] for r in _py(pick)] == want[:8]
    pick["cap"] = None
    assert [r["key"] for r in _py(pick)] == want


def test_the_view_writes_bounds_at_one_width_and_names_the_fields_it_reads():
    pick = _filter_pick([{"field": "when", "op": "on", "value": "2026-07-09"}])
    assert pick["times"] == ["when"]
    assert '"2026-07-09T00:00:00.000000Z"' in pick["filter"] and '"2026-07-10T00:00:00.000000Z"' in pick["filter"]
    assert pview.time_fields_read({"filter": {"version": pview.FILTER_VERSION, "join": "all", "items": [
        {"field": "when", "op": "present"}]}}, FIELDS) == []        # present/blank read no instant


# ── the statement, on the throwaway: the same rows, the same hand truth ──

@pytest.fixture(scope="module")
def conn():
    import psycopg

    import this_runtime
    with psycopg.connect(DSN, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
        this_runtime.install(cx)
    c = psycopg.connect(DSN)
    c.execute("SET TimeZone = 'UTC'")
    c.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    for k in ROWS:
        c.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps(_doc(k))))
    yield c
    c.rollback()
    c.close()


def _sql(conn, pick):
    with conn.transaction():                       # a savepoint: one failing statement fails only its test
        with env.checking_zones(zones.clock_check(conn)):
            b = builder.build(pick, KEYS, records=_records())
        cur = conn.execute(b.sql, b.params)
        names = [d.name for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


@needs_db
@pytest.mark.parametrize("text, want", HAND)
def test_the_rule_in_sql(conn, text, want):
    with conn.transaction():
        got = conn.execute("SELECT to_char(xpr.time_at(%s) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')",
                           (text,)).fetchone()[0]
    assert got == want, (text, got)


@needs_db
@pytest.mark.parametrize("zone", [None, DENVER])
def test_the_statement_buckets_every_readable_time_by_its_instant(conn, zone):
    got = {r["bucket"]: int(r["agg"]) for r in _sql(conn, _bucket_pick("day", zone))}
    assert got == _per_day_hand(zone), got
    kept = int(_sql(conn, _pick(aggregate={"fn": "count", "field": None}))[0]["agg"])
    assert kept - sum(got.values()) == len(UNREADABLE) + 2


@needs_db
def test_the_statement_cuts_dst_hours_on_the_questions_clock(conn):
    with conn.transaction():
        conn.execute(f"DELETE FROM {TABLE}")
        for k, v in DST.items():
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps({"when": v})))
        got = {r["bucket"]: int(r["agg"]) for r in _sql(conn, _bucket_pick("hour", DENVER))}
        conn.execute(f"DELETE FROM {TABLE}")
        for k in ROWS:
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps(_doc(k))))
    assert got == DST_HAND, got


#: D by hand (T-101: the instants where this database's clock and Python's disagree), one hour on Denver's clock. A time
#: written with an offset is tested against D by its instant, never by its text, whose forms no longer order as time.
D_HOUR = ((datetime(2026, 7, 9, 12, tzinfo=timezone.utc).timestamp(),
           datetime(2026, 7, 9, 13, tzinfo=timezone.utc).timestamp()),)
D_CASES = {
    "inside D by its instant, before it as text": ("2026-07-09T06:30:00-06:00", "refused"),
    "outside D by its instant, inside it as text": ("2026-07-09T12:30:00+02:00", {"2026-07-09T04:00:00": 1}),
}


@needs_db
@pytest.mark.parametrize("case", list(D_CASES))
def test_the_statement_tests_D_against_a_times_instant_never_its_text(conn, case):
    import psycopg
    stored, want = D_CASES[case]
    with conn.transaction():
        conn.execute(f"DELETE FROM {TABLE}")
        conn.execute(f"INSERT INTO {TABLE} VALUES (%s, 'd1', %s::jsonb)", (T, json.dumps({"when": stored})))
        try:
            with conn.transaction():
                with env.checking_zones(lambda z: D_HOUR if z == DENVER else ()):
                    b = builder.build(_bucket_pick("hour", DENVER), KEYS, records=_records())
                got = {r[0]: int(r[1]) for r in conn.execute(b.sql, b.params).fetchall()}
        except psycopg.Error as e:
            got = "refused" if e.sqlstate == "XPR05" else e
        conn.execute(f"DELETE FROM {TABLE}")
        for k in ROWS:
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps(_doc(k))))
    assert got == want, (case, got)


@needs_db
def test_a_probe_never_asks_about_a_time_field_its_truth_reads_as_an_instant(conn):
    """Spec §3's probe row: read as an instant, a time field is text, null or false in both engines, so no member
    can fire on it. Probed raw, a number past a double stored there refused the question; a computed column still
    reads the field raw, and is probed."""
    from picks import probes
    parse = env.get("parser").parse
    pick = _filter_pick([{"field": "when", "op": "after", "value": "2026-07-09T05:00"}])
    truth = parse(pick["filter"])

    def refused(**kw):
        try:
            with conn.transaction():
                probes.check(conn, T, kw.pop("exprs", []), truth_roots=[truth], records=_records(), **kw)
            return None
        except probes.RuntimeRefusal as e:
            return e

    with conn.transaction():
        conn.execute(f"INSERT INTO {TABLE} VALUES (%s, 'zz-big', '{{\"when\": 1e400}}'::jsonb)", (T,))
        raw, read, computed = refused(), refused(times=pick["times"]), refused(times=pick["times"],
                                                                             exprs=[parse("$.when * 1")])
        conn.execute(f"DELETE FROM {TABLE} WHERE key = 'zz-big'")
    assert pick["times"] == ["when"] and getattr(raw, "member", None) == "a", raw
    assert read is None, read
    assert getattr(computed, "member", None) == "a", computed


@needs_db
@pytest.mark.parametrize("fn", ["max", "min"])
def test_the_statement_reads_a_boards_latest_and_earliest_by_instant(conn, fn):
    from picks import group as sgroup
    b = sgroup.build(dict(BOARD, time={"fn": fn, "field": "when"}), records=_records())
    with conn.transaction():
        cur = conn.execute(b.sql, b.params)
        names = [d.name for d in cur.description]
        got = {r["grp"]: r["time"] for r in (dict(zip(names, row)) for row in cur.fetchall())}
    assert got == BOARD_HAND[fn], got


@needs_db
def test_the_statement_leaves_a_clock_reading_before_year_1_out(conn):
    with conn.transaction():
        conn.execute(f"DELETE FROM {TABLE}")
        for k, v in YEARS.items():
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps({"when": v})))
        got = {r["bucket"]: int(r["agg"]) for r in _sql(conn, _bucket_pick("day", "Etc/GMT+12"))}
        conn.execute(f"DELETE FROM {TABLE}")
        for k in ROWS:
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps(_doc(k))))
    assert got == YEARS_HAND, got


@needs_db
@pytest.mark.parametrize("case", list(CONDITIONS))
def test_the_statement_compares_instants_and_an_unreadable_time_matches_nothing(conn, case):
    items, join, zone, want = CONDITIONS[case]
    got = {r["key"] for r in _sql(conn, _filter_pick(items, join, zone))}
    assert got == want, (case, sorted(got ^ want))


@needs_db
@pytest.mark.parametrize("direction, want", [("desc", SORT_DESC), ("asc", SORT_ASC)])
def test_the_statement_sorts_a_time_field_by_its_instant_and_caps_it(conn, direction, want):
    pick = _filter_pick([], sort={"field": "$.when", "dir": direction}, cap=8)
    pick["times"] = ["when"]
    assert [r["key"] for r in _sql(conn, pick)] == want[:8]


@needs_db
@pytest.mark.parametrize("case", list(KIND_CASES))
def test_the_setups_sql_counts_what_its_python_counts(conn, case):
    values, want = KIND_CASES[case]
    with conn.transaction():
        conn.execute("CREATE TEMPORARY TABLE t114k (collection text, key text, data jsonb) ON COMMIT DROP")
        for i, v in enumerate(values):
            conn.execute("INSERT INTO t114k VALUES (%s, %s, %s::jsonb)", (T, f"k{i}", json.dumps({"f": v})))
        rec = Records(table="t114k", sources={T: "f"})
        sql = pview._FORMS_SQL.replace("{table}", "t114k").replace("{scope}", rec.scope("r", {}))
        counts = tuple(conn.execute(sql, {"collection": T, "path": ["f"]}).fetchone())
        conn.execute("DROP TABLE t114k")
    assert counts == tuple(_times().kind_counts(values)), (case, counts)
    assert pview._kind({"string"}, counts) == want


@needs_db
def test_the_python_reader_answers_the_setup_as_postgres_does(conn):
    """GIMS's SQLite mode reads its fields with picks' own Python answer (T-114: moved here from GIMS's _RowsConn), and
    it must answer every reader statement as Postgres does: the kinds, the spans, the values."""
    docs = [_doc(k) for k in ROWS] + [{"f": v} for vals, _want in KIND_CASES.values() for v in vals] + [
        {"g": v} for v in KIND_CASES["two readable, one junk: a time field"][0]]
    with conn.transaction():
        conn.execute("CREATE TEMPORARY TABLE t114r (collection text, key text, data jsonb) ON COMMIT DROP")
        for i, d in enumerate(docs):
            conn.execute("INSERT INTO t114r VALUES (%s, %s, %s::jsonb)", (T, f"r{i:03d}", json.dumps(d)))
        rec = Records(table="t114r", sources={T: "x"})
        in_sql = pview._read_fields(conn, T, records=rec)
        conn.execute("DROP TABLE t114r")
    reader = pview.PythonReader(rec, [json.loads(json.dumps(d), parse_float=Decimal) for d in docs])
    in_python = pview._read_fields(reader, T, records=rec)
    by_path = (lambda fields: {f["path"]: f for f in fields})        # (the order is _TYPES_SQL's rows', unordered)
    assert by_path(in_python) == by_path(in_sql)
    kinds = {f["path"]: f["kind"] for f in in_sql}
    assert kinds["when"] == "time" and kinds["g"] == "time" and kinds["s"] == "text", kinds


# ── the two readers, 250,000 generated strings (T-103's way): the same instant, or unreadable on both ──

def _generated(n, seed=114):
    """Half readable times in every form the rule reads (random days in years 1..9999, offsets to 14:59, 0-6
    digits), half with ONE thing wrong -- each near miss the spec names -- plus truncations and junk."""
    rnd = random.Random(seed)
    digits = "0123456789"
    out = []
    for _ in range(n):
        y = rnd.choice([rnd.randint(1, 9999), rnd.randint(1960, 2100), 1, 9999, 2000, 2100, 1900, 2028])
        mo = rnd.randint(1, 12)
        d = rnd.randint(1, 31 if mo in (1, 3, 5, 7, 8, 10, 12) else 30 if mo != 2 else 29)
        hh, mi, ss = rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59)
        sep = rnd.choice("TTT ")
        frac = rnd.choice(["", "", "." + "".join(rnd.choice(digits) for _ in range(rnd.randint(1, 6)))])
        oh, om = rnd.randint(0, 14), rnd.choice([rnd.randint(0, 59), 0, 30, 45])
        off = rnd.choice(["Z", "Z", f"+{oh:02d}:{om:02d}", f"-{oh:02d}:{om:02d}", f"+{oh:02d}{om:02d}",
                          f"-{oh:02d}{om:02d}", "-00:00", "+00:00"])
        if rnd.random() < 0.5:
            miss = rnd.randrange(14)
            if miss == 0:
                mo = rnd.choice([0, 13])
            elif miss == 1:
                d = rnd.choice([0, 29, 30, 31, 32])
            elif miss == 2:
                hh = 24
            elif miss == 3:
                mi = 60
            elif miss == 4:
                ss = 60
            elif miss == 5:
                sep = rnd.choice("t_")
            elif miss == 6:
                frac = "." + "".join(rnd.choice(digits) for _ in range(rnd.randint(7, 9)))
            elif miss == 7:
                frac = "," + rnd.choice(digits)
            elif miss == 8:
                off = rnd.choice(["z", "", ""])
            elif miss == 9:
                off = f"{rnd.choice('+-')}{rnd.randint(15, 23):02d}:{om:02d}"
            elif miss == 10:
                off = f"+{oh:02d}:{om:02d}:{rnd.randint(0, 59):02d}"
            elif miss == 11:
                off = f"{rnd.choice('+-')}{oh:02d}"
            elif miss == 12:                         # the years' edges, an offset either way
                y, mo, d = rnd.choice([(1, 1, 1), (9999, 12, 31)])
                hh = rnd.choice([0, 23])
                off = rnd.choice(["+14:59", "-14:59", "+00:01", "-00:01", "Z"])
            else:
                y = 0
        s = f"{y:04d}-{mo:02d}-{d:02d}{sep}{hh:02d}:{mi:02d}:{ss:02d}{frac}{off}"
        r = rnd.random()
        if r < 0.03:
            s = s[:10]                               # a bare date
        elif r < 0.05:
            s = s[:16]                               # no seconds
        elif r < 0.06:
            s = rnd.choice([" ", "\t"]) + s
        elif r < 0.07:
            s = s.replace("-", "", 2)                # the basic format
        elif r < 0.08:
            s = "".join(rnd.choice("0123456789-:TZ+. ") for _ in range(rnd.randint(0, 30)))
        out.append(s)
    return out


@needs_db
def test_the_two_readers_agree_on_250000_generated_strings(conn):
    t = _times()
    texts = _generated(250_000)
    bad = []
    for i in range(0, len(texts), 50_000):
        chunk = texts[i:i + 50_000]
        with conn.transaction():
            cur = conn.execute(
            "SELECT to_char(xpr.time_at(s) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM unnest(%s::text[]) WITH ORDINALITY AS u(s, o) ORDER BY o", (chunk,))
            sql = [r[0] for r in cur.fetchall()]
        for s, got in zip(chunk, sql):
            py = t.instant(s)
            want = t.utc_text(py) if py is not None else None
            if got != want:
                bad.append((s, got, want))
    readable = sum(1 for s in texts if t.instant(s) is not None)
    assert not bad, bad[:5]
    assert 90_000 < readable < 180_000, readable      # both sides of the rule are exercised


# ── the dashboard, on a scratch copy of the seed: the setup, the span, a summary, conditions and sort ──
SCRATCH = "t114_scratch"


@pytest.fixture(scope="module")
def demo():
    if not DSN:
        pytest.skip("set AUTOSQL_PARITY_DSN to a throwaway Postgres")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    from demo.server import app as server_app, dashboard, db, settings
    from fastapi.testclient import TestClient

    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
        cx.execute(f"CREATE DATABASE {SCRATCH}")
    dsn = make_conninfo(**{**conninfo_to_dict(DSN), "dbname": SCRATCH})
    with psycopg.connect(dsn, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(dsn) as cx:
        load.install_schema(cx)
        load.copy_rows(cx)
        # Edge cases gain a time field in GIMS's forms (ROWS), a free-text field with one time among words, and a
        # field of 2,500 distinct times (the span's cap was 2,001)
        for k in ROWS:
            d = dict(_doc(k), rid=k, note="fine" if k != "a4" else "2026-07-09T05:03:48Z")
            cx.execute("INSERT INTO demo.records VALUES ('noun:EdgeCase', %s, %s::jsonb)", (f"zz-{k}", json.dumps(d)))
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for i in range(2500):
            t = start + timedelta(minutes=5 * i)
            form = (t.strftime("%Y-%m-%dT%H:%M:%SZ") if i % 3 == 0 else
                    t.strftime("%Y-%m-%dT%H:%M:%S+00:00") if i % 3 == 1 else t.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"))
            cx.execute("INSERT INTO demo.records VALUES ('noun:EdgeCase', %s, %s::jsonb)",
                       (f"zy-{i:05d}", json.dumps({"t2500": form})))
        for k, v in BARE.items():                    # a-chk's preview: bare dates beside times, in a field of their own
            cx.execute("INSERT INTO demo.records VALUES ('noun:EdgeCase', %s, %s::jsonb)",
                       (f"zx-{k}", json.dumps({"bd": v, "batch": "bare"})))
        cx.commit()
    opts = f"-c timezone={settings.TIME_ZONE} -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
    real = db.connect
    db.connect = lambda *, application_name=None, autocommit=False: psycopg.connect(dsn, autocommit=autocommit,
                                                                                    options=opts)
    dashboard._CACHE.clear()
    dashboard._SETUP = None                 # the setup is read once a process: read it again, over this copy
    try:
        yield {"client": TestClient(server_app.app, raise_server_exceptions=False)}
    finally:
        db.connect = real
        dashboard._CACHE.clear()
        dashboard._SETUP = None
        with psycopg.connect(DSN, autocommit=True) as cx:
            cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def _setup_fields(demo):
    setup = demo["client"].get("/api/dashboard/setup?view=admin").json()
    ds = next(d for d in setup["datasets"] if d["id"] == "edge")
    return {f["path"]: f for f in ds["fields"]}


def _answer(demo, **view):
    v = {"dataset": "edge", "columns": ["rid"], "conditions": [], "sort": None, "show": None, "summary": None}
    v.update(view)
    r = demo["client"].post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})
    try:
        return r.status_code, r.json()
    except ValueError:                             # a 500's body is no JSON: say what it was
        return r.status_code, {"message": r.text[:200]}


@needs_db
def test_the_dashboards_setup_calls_a_mixed_field_a_time_and_free_text_text(demo):
    f = _setup_fields(demo)
    assert f["when"]["kind"] == "time", f["when"]
    assert f["note"]["kind"] == "text", f["note"]
    assert f["t2500"]["kind"] == "time"
    assert f["t2500"]["range"] == {"min": "2026-07-01T00:00:00Z", "max": "2026-07-09T16:15:00Z"}, f["t2500"]["range"]


@needs_db
def test_a_time_field_with_more_than_2001_distinct_times_is_charted_whole(demo):
    status, a = _answer(demo, columns=[], summary={"fn": "count", "field": None, "per": "day", "time": "t2500"})
    assert status == 200 and a.get("kind") == "chart", (status, str(a)[:300])
    bars = {b["start"]: b["value"] for b in a["bars"] if not b.get("empty")}
    assert sum(bars.values()) == 2500 and max(bars) == "2026-07-09T00:00:00Z", (len(bars), max(bars))


@needs_db
def test_the_dashboard_counts_a_mixed_field_per_day_by_instant(demo):
    status, a = _answer(demo, columns=[], summary={"fn": "count", "field": None, "per": "day", "time": "when"})
    assert status == 200 and a.get("kind") == "chart", (status, str(a)[:300])
    bars = {b["start"]: b["value"] for b in a["bars"] if not b.get("empty")}
    assert bars == {k: float(v) for k, v in _per_day_hand().items()}, bars


@needs_db
@pytest.mark.parametrize("case", ["on Jul 9 (UTC)", "on Jul 9 (Denver)", "after 05:03:48 UTC", "present: an unreadable value is present",
                                  "all or none (after X, S is y): no unreadable row"])
def test_the_dashboards_conditions_compare_instants(demo, case):
    items, join, zone, want = CONDITIONS[case]
    # only the rows this test added (they alone hold a Rid): the cards as one group, and Rid has a value
    view = {"filter": {"version": pview.FILTER_VERSION, "join": "all",
                       "items": [{"join": join, "items": items}, {"field": "rid", "op": "present"}]}}
    if zone:
        view["zone"] = zone
    status, a = _answer(demo, show=None, **view)
    assert status == 200 and a.get("kind") == "table", (status, str(a)[:300])
    keys = {r[0] for r in a["rows"]}
    assert keys == want, (case, sorted(keys ^ want), str(a)[:200])


@needs_db
def test_the_dashboard_sorts_a_time_field_by_its_instant_and_shows_the_first_rows(demo):
    status, a = _answer(demo, sort={"field": "when", "dir": "desc"}, show=25,
                        filter={"version": pview.FILTER_VERSION, "join": "all",
                                "items": [{"field": "rid", "op": "present"}]})
    assert status == 200 and a.get("kind") == "table", (status, str(a)[:300])
    assert [r[0] for r in a["rows"]] == SORT_DESC, a["rows"]          # (the cap itself: the engine tests, cap 8)



# ── a-chk's preview of 113a9d1: on a question's clock EVERY reader reads a bare date as that clock's midnight ──
# (spec §2.1, T-100). Its data set: one time field holding bare dates beside times, asked on four clocks.

BARE = {"b0": "2026-07-09", "b1": "2026-07-10", "b2": "2026-07-09T12:00:00Z", "b3": "2026-07-09T23:30:00-06:00",
        "b4": "2026-07-09T02:00:00+05:30", "b5": "2026-10-20", "b6": "2026-10-20T03:00:00Z",
        "b7": "2026-07-09T05:03", "b8": "lunch", "b9": None}
#: by hand: each time's UTC instant, and each bare date; b7 (naive), b8 (words) and b9 (null) read as no time
BARE_TIMES = {"b2": datetime(2026, 7, 9, 12, tzinfo=timezone.utc), "b3": datetime(2026, 7, 10, 5, 30, tzinfo=timezone.utc),
              "b4": datetime(2026, 7, 8, 20, 30, tzinfo=timezone.utc), "b6": datetime(2026, 10, 20, 3, tzinfo=timezone.utc)}
BARE_DATES = {"b0": (2026, 7, 9), "b1": (2026, 7, 10), "b5": (2026, 10, 20)}
CLOCKS = [None, "America/Denver", "Asia/Kolkata", "Pacific/Kiritimati"]


def _tz(zone):
    from zoneinfo import ZoneInfo
    return ZoneInfo(zone) if zone else timezone.utc


def _bare_at(key, zone):
    """The instant a row reads as on the clock: a time is itself, a bare date its own midnight there."""
    if key in BARE_TIMES:
        return BARE_TIMES[key]
    if key in BARE_DATES:
        return datetime(*BARE_DATES[key], tzinfo=_tz(zone))
    return None


def _bare_buckets(per, zone, keys=BARE):
    out = {}
    for k in keys:
        at = _bare_at(k, zone)
        if at is not None:
            local = at.astimezone(_tz(zone))
            start = local.replace(minute=0, second=0) if per == "hour" else local.replace(hour=0, minute=0, second=0)
            label = start.replace(tzinfo=None).isoformat(timespec="seconds") + ("" if zone else "Z")
            out[label] = out.get(label, 0) + 1
    return out


def _wall(zone, *ymdhm):
    return datetime(*ymdhm, tzinfo=_tz(zone))


#: the conditions a person picks on the question's clock, and by hand whether an instant on that clock holds them
BARE_CONDS = {
    "on Jul 9": ({"field": "when", "op": "on", "value": "2026-07-09"},
                 lambda at, z: _wall(z, 2026, 7, 9) <= at < _wall(z, 2026, 7, 10)),
    "on Oct 20 (today)": ({"field": "when", "op": "on", "value": "2026-10-20"},
                          lambda at, z: _wall(z, 2026, 10, 20) <= at < _wall(z, 2026, 10, 21)),
    "after Jul 8, 8:00 PM": ({"field": "when", "op": "after", "value": "2026-07-08T20:00"},
                             lambda at, z: at > _wall(z, 2026, 7, 8, 20, 0)),
    "before Jul 9, 12:30 AM": ({"field": "when", "op": "before", "value": "2026-07-09T00:30"},
                               lambda at, z: at < _wall(z, 2026, 7, 9, 0, 30)),
    "between Jul 9, 12:00 AM and 11:59 PM": (
        {"field": "when", "op": "between", "value": "2026-07-09T00:00", "value2": "2026-07-09T23:59"},
        lambda at, z: _wall(z, 2026, 7, 9, 0, 0) <= at <= _wall(z, 2026, 7, 9, 23, 59)),
}


def _bare_kept(holds, zone):
    return {k for k in BARE if _bare_at(k, zone) is not None and holds(_bare_at(k, zone), zone)}


def _with_rows(conn, rows, fn):
    """Run fn with the temporary table holding ``rows`` (key -> stored when), then put ROWS back."""
    with conn.transaction():
        conn.execute(f"DELETE FROM {TABLE}")
        for k, v in rows.items():
            conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps({"when": v})))
        try:
            return fn()
        finally:
            conn.execute(f"DELETE FROM {TABLE}")
            for k in ROWS:
                conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (T, k, json.dumps(_doc(k))))


def _py_rows(rows, pick):
    src = [pyrows.source_row(T, k, json.dumps({"when": v})) for k, v in sorted(rows.items())]
    return pyshape.answer(src, pick, _records())["rows"]


@needs_db
@pytest.mark.parametrize("zone", CLOCKS)
def test_every_reader_reads_a_bare_date_as_its_clocks_midnight(conn, demo, zone):
    """One bare date, every reader, both engines: buckets per day and per hour and their left-out count, the
    conditions on / after / before / between / today, time of day (a bare date has none), the chart's span and axis
    (where the 500 was), the statement's zone-disagreement check and its years shortcut."""
    import psycopg
    bad = []                                       # every reader that reads it otherwise, named, asserted once

    def check(ok, *what):
        if not ok:
            bad.append(what)
    for per in ("day", "hour"):
        want = _bare_buckets(per, zone)
        pick = _bucket_pick(per, zone)
        sql = _with_rows(conn, BARE, lambda: {r["bucket"]: int(r["agg"]) for r in _sql(conn, pick)})
        py = {r["bucket"]: int(r["agg"]) for r in _py_rows(BARE, pick)}
        check(sql == want and py == want, "buckets", per, sql, py, want)
        kept = _with_rows(conn, BARE, lambda: int(_sql(conn, _pick(aggregate={"fn": "count", "field": None}))[0]["agg"]))
        check(kept - sum(want.values()) == 3, "left out", per, kept)                  # b7, b8, b9
    for name, (card, holds) in BARE_CONDS.items():
        want = _bare_kept(holds, zone)
        pick = _filter_pick([card], "all", zone)
        sql = _with_rows(conn, BARE, lambda: {r["key"] for r in _sql(conn, pick)})
        py = {r["key"] for r in _py_rows(BARE, pick)}
        check(sql == want and py == want, name, sorted(sql), sorted(py), sorted(want))
    tod = _filter_pick([{"field": "when", "part": "time_of_day", "op": "from", "value": "05:00"}], "all", zone)
    want = {k for k, at in BARE_TIMES.items() if at.astimezone(_tz(zone)).hour >= 5}     # a bare date has no time of day
    sql = _with_rows(conn, BARE, lambda: {r["key"] for r in _sql(conn, tod)})
    py = {r["key"] for r in _py_rows(BARE, tod)}
    check(sql == want and py == want, "time of day from 05:00", sorted(sql), sorted(py), sorted(want))
    for per in ("day", "hour"):
        status, a = _answer(demo, columns=[], conditions=[{"field": "batch", "op": "eq", "value": "bare"}],
                            summary={"fn": "count", "field": None, "per": per, "time": "bd"},
                            **({"zone": zone} if zone else {}))
        if status != 200 or a.get("kind") != "chart":
            check(False, "chart", per, status, str(a.get("message") or a)[:120])
            continue
        bars = {b["start"]: int(b["value"]) for b in a["bars"] if not b.get("empty")}
        want = _bare_buckets(per, zone)
        check(bars == want, "chart", per, bars, want)
        check((a["bars"][0]["start"], a["bars"][-1]["start"]) == (min(want), max(want)), "axis", per,
              (a["bars"][0]["start"], a["bars"][-1]["start"]))
    f = _setup_fields(demo)
    check(f["bd"]["kind"] == "time" and f["bd"]["range"] == {
        "min": "2026-07-08T20:30:00Z", "max": "2026-10-20T03:00:00Z",
        "dates": {"min": "2026-07-09", "max": "2026-10-20"}}, "the span", f["bd"].get("range"))
    if zone:
        # the zone-disagreement check: a window of disagreement around b0's midnight on this clock refuses no bare
        # date (a date is its own midnight, never read on a clock); the window holds no time
        mid = _bare_at("b0", zone).timestamp()

        def with_d():
            with conn.transaction():
                with env.checking_zones(lambda z: ((mid - 1800, mid + 1800),) if z == zone else ()):
                    b = builder.build(_bucket_pick("hour", zone), KEYS, records=_records())
                return {r[0]: int(r[1]) for r in conn.execute(b.sql, b.params).fetchall()}
        try:
            got = _with_rows(conn, BARE, with_d)
        except psycopg.Error as e:
            got = e.sqlstate
        check(got == _bare_buckets("hour", zone), "zone check", got)
    # the years shortcut: a bare date at either end of years 1..9999 is its own day on every clock
    ends = {"y1": "0001-01-01", "y9": "9999-12-31"}
    want = {"0001-01-01T00:00:00" + ("" if zone else "Z"): 1, "9999-12-31T00:00:00" + ("" if zone else "Z"): 1}
    sql = _with_rows(conn, ends, lambda: {r["bucket"]: int(r["agg"]) for r in _sql(conn, _bucket_pick("day", zone))})
    py = {r["bucket"]: int(r["agg"]) for r in _py_rows(ends, _bucket_pick("day", zone))}
    check(sql == want and py == want, "years", sql, py)
    assert not bad, (zone, bad)
