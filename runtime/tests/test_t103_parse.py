"""T-103: the date parse without capture groups, one parse a row -- held to the wrong-number bar.

xpr.pdate_ms validates the text with ~ (the same pattern, no capture groups) and reads its fields by position;
xpr.pdate_only and xpr.time_of_day decide "has a time part" from the same text (its length after Python's whitespace
trim is over 10) instead of a second and third parse. This file holds that to:

  * a differential against the parser as it was on main 0fbf225 -- loaded into pg_temp ONLY, from
    fixtures/old_parser_0fbf225.sql -- float8 for float8 and NULL for NULL, on at least 200,000 generated strings
    (every shape of the grammar, every field at and past its edges, every separator and offset form, fractions of
    0-7 digits, Unicode digits and whitespace, and one-character mutations of valid strings); any difference fails
    and is printed;
  * the one new rule pinned at its edge with the trims that differ (a trailing NBSP, an ideographic space, a string
    10 long after Python's trim but not after a naive btrim), against Python's own _parse_date_ms;
  * every NULL rule at its exact edge, written by hand, in both engines;
  * the clock read at DST edges both ways (Denver; Lord Howe's half hour), the hand value in both engines.

Database tests: AUTOSQL_RUNTIME_DSN, a throwaway Postgres; each installs this tree's runtime first. SKIP without it.
T103_DIFF_N sets the differential's size (default 200,000).
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")
OLD = Path(__file__).resolve().parent / "fixtures" / "old_parser_0fbf225.sql"
N = int(os.environ.get("T103_DIFF_N", "200000"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t103_expr", "demo/vendor/expr.py")


@pytest.fixture(scope="module")
def db():
    import psycopg
    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    cx = psycopg.connect(DSN, autocommit=True)
    if int(cx.info.port) in (55433, 55440):
        cx.close()
        raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
    this_runtime.install(cx)
    cx.execute(OLD.read_text())          # the old parser, in this session's pg_temp only
    yield cx
    cx.close()


def _sql(db, fn, values, *extra):
    """fn over each value, in order (values as Python objects, sent as jsonb)."""
    args = "".join(f", %s" for _ in extra)
    return [db.execute(f"SELECT {fn}(%s::jsonb{args})", (json.dumps(v), *extra)).fetchone()[0] for v in values]


def _py_ms(v):
    p = EXPR._parse_date_ms(v)
    return None if p is None else p[0]


def _py_only(v):
    p = EXPR._parse_date_ms(v)
    return None if p is None else p[1]


def _py_tod(v, zone):
    return EXPR.evaluate(EXPR.parse(f'time_of_day($.t, "{zone}")'), {"t": v})


def _utc_ms(*a):
    """The rule, by hand: a UTC calendar time as epoch milliseconds (Python's datetime, not either engine)."""
    return datetime(*a, tzinfo=timezone.utc).timestamp() * 1000.0


# ── the one new rule: "has a time part" from the length after Python's trim ────────────────────────

HAS_TIME_EDGE = [
    # (text, date_only by hand)
    ("2026-08-20 ", True),          # a trailing NBSP: Python strips it; the ASCII trim does not
    ("2026-08-20　", True),          # a trailing ideographic space
    (" 2026-08-20", True),          # 10 long after Python's trim, 11 after a naive btrim
    ("　2026-08-20 ", True),
    ("2026-08-20 ", True),               # an ASCII space: both trims take it
    ("2026-08-20T10:00 ", False),   # 16 after the trim: a time part
    ("　2026-08-20 10:00", False),
    ("2026-08-20T10:00:00Z　", False),
]


@needs_db
@pytest.mark.parametrize("text, date_only", HAS_TIME_EDGE)
def test_a_time_part_is_decided_after_pythons_trim(db, text, date_only):
    assert _py_only(text) is date_only, "Python itself disagrees with the hand value"
    assert _sql(db, "xpr.pdate_only", [text]) == [date_only]
    assert _sql(db, "xpr.pdate_ms", [text]) == [_py_ms(text)] != [None]
    tod = _sql(db, "xpr.time_of_day", [text], "UTC")[0]
    assert (tod is None) is date_only and tod == _py_tod(text, "UTC")


# ── every NULL rule at its edge, by hand, in both engines ───────────────────────────────────────────

EDGES = [
    # (text, the epoch ms by hand, or None when it must not parse)
    ("2026-12-01", _utc_ms(2026, 12, 1)), ("2026-13-01", None),
    ("2026-01-00", None), ("2026-01-31", _utc_ms(2026, 1, 31)), ("2026-01-32", None),
    ("2026-04-30", _utc_ms(2026, 4, 30)), ("2026-04-31", None),
    ("2026-02-28", _utc_ms(2026, 2, 28)), ("2026-02-29", None),
    ("2024-02-29", _utc_ms(2024, 2, 29)), ("2024-02-30", None),
    ("1900-02-28", _utc_ms(1900, 2, 28)), ("1900-02-29", None),   # 1900 is not a leap year
    ("2000-02-29", _utc_ms(2000, 2, 29)),
    ("2026-08-20T23:00", _utc_ms(2026, 8, 20, 23)), ("2026-08-20T24:00", None),
    ("2026-08-20T10:59", _utc_ms(2026, 8, 20, 10, 59)), ("2026-08-20T10:60", None),
    ("2026-08-20T10:00:59", _utc_ms(2026, 8, 20, 10, 0, 59)), ("2026-08-20T10:00:60", None),
    ("2026-08-20T17:00:00.5Z", _utc_ms(2026, 8, 20, 17, 0, 0, 500000)),
    ("2026-08-20T17:00:00.123456Z", _utc_ms(2026, 8, 20, 17, 0, 0, 123456)),
    ("2026-08-20T17:00:00.1234567Z", None),                        # seven digits of fraction
    ("0001-01-01", _utc_ms(1, 1, 1)), ("0000-01-01", None),
    ("9999-12-31T23:59:59Z", _utc_ms(9999, 12, 31, 23, 59, 59)),
    ("2026-08-20 17:00", _utc_ms(2026, 8, 20, 17)),                 # the space separator
    ("2026-08-20t17:00", None),                                     # a lowercase t is not one
    ("2026-08-20T17:00+0530", _utc_ms(2026, 8, 20, 11, 30)),
    ("2026-08-20T17:00:00+05:30", _utc_ms(2026, 8, 20, 11, 30)),
    ("2026-08-20T17:00:00-07:00", _utc_ms(2026, 8, 21, 0)),
    ("2026-08-20T17:00:00.5-07:00", _utc_ms(2026, 8, 21, 0, 0, 0, 500000)),
    ("2026-08-20T17:00:00+99:99", _utc_ms(2026, 8, 20, 17) - (99 * 60 + 99) * 60000.0),  # whatever the digits say
    ("2026-08-20T17:00:00+05", None), ("2026-08-20T17:00Z", _utc_ms(2026, 8, 20, 17)),
    ("2026-08-20Z", None),                                          # an offset needs a time
    ("２０２６-０８-２０", _utc_ms(2026, 8, 20)),                    # full-width digits (the Unicode path)
    ("٢٠٢٦-٠٨-٢٠T١٠:٠٠", _utc_ms(2026, 8, 20, 10)),                 # Arabic-Indic digits
]


@needs_db
@pytest.mark.parametrize("text, want", EDGES)
def test_every_null_rule_is_held_at_its_edge_in_both_engines(db, text, want):
    assert _py_ms(text) == want, f"Python: {_py_ms(text)!r}, by hand: {want!r}"
    assert _sql(db, "xpr.pdate_ms", [text]) == [want], f"SQL disagrees with the hand value for {text!r}"


#: the instants at years 1 and 9999 that leave Python's range on the clock (T-98's rule): parsed, but no time of day
FAR = [("0001-01-01T00:00:00Z", "UTC", 0.0), ("0001-01-01T00:00:00+14:00", "UTC", None),
       ("9999-12-31T23:59:59Z", "UTC", 86399.0), ("9999-12-31T23:59:59-01:00", "UTC", None),
       ("1900-01-01T12:00:00Z", "UTC", 43200.0)]


@needs_db
@pytest.mark.parametrize("text, zone, want", FAR)
def test_times_far_from_today_read_on_the_clock_as_python_does(db, text, zone, want):
    assert _py_tod(text, zone) == want
    assert _sql(db, "xpr.time_of_day", [text], zone) == [want]


#: (instant, zone, the wall clock's seconds since midnight, worked out by hand from the zone's rules)
DST = [
    ("2026-03-08T08:59:59Z", "America/Denver", 1 * 3600 + 59 * 60 + 59),   # 1:59:59 MST
    ("2026-03-08T09:00:00Z", "America/Denver", 3 * 3600),                  # 3:00 MDT: 2:00-2:59 never shown
    ("2026-11-01T07:59:59Z", "America/Denver", 1 * 3600 + 59 * 60 + 59),   # 1:59:59 MDT
    ("2026-11-01T08:00:00Z", "America/Denver", 1 * 3600),                  # 1:00 MST again
    ("2026-10-03T15:29:59Z", "Australia/Lord_Howe", 1 * 3600 + 59 * 60 + 59),  # 1:59:59 at +10:30
    ("2026-10-03T15:30:00Z", "Australia/Lord_Howe", 2 * 3600 + 30 * 60),   # 2:30 at +11: half an hour skipped
]


@needs_db
@pytest.mark.parametrize("text, zone, want", DST)
def test_the_clock_at_dst_edges_both_ways_is_the_hand_value_in_both_engines(db, text, zone, want):
    assert _py_tod(text, zone) == float(want)
    assert _sql(db, "xpr.time_of_day", [text], zone) == [float(want)]


# ── the differential ──────────────────────────────────────────────────────────────────────────────

_DIG = "0123456789"
_UNI = ["٠١٢٣٤٥٦٧٨٩", "０１２３４５６７８９", "०१२३४५६७८९"]
_WS = [" ", "\t", "\n", " ", "　", "\u001f", "\u0085", " ", "​", "\u000b"]
_ALPHA = _DIG + "-:T .Z+zt" + " 　a" + "٣４"


def _two(rng, lo, hi):
    return f"{rng.randint(lo, hi):02d}"


def _pick(rng, usual, edges):
    """Mostly a usual value; an edge (or just past one) about one time in seven."""
    return rng.choice(edges) if rng.random() < 0.15 else usual


def _valid(rng):
    y = _pick(rng, f"{rng.randint(1, 9999):04d}", ["0000", "0001", "1900", "1970", "2000", "2024", "2026", "9999"])
    s = f"{y}-{_pick(rng, _two(rng, 1, 12), ['00', '01', '12', '13'])}-{_pick(rng, _two(rng, 1, 28), ['00', '28', '29', '30', '31', '32'])}"
    if rng.random() < 0.85:
        s += _pick(rng, "T", [" ", "t", "_"]) + _pick(rng, _two(rng, 0, 23), ["00", "23", "24"]) + ":" + _pick(rng, _two(rng, 0, 59), ["59", "60"])
        if rng.random() < 0.8:
            s += ":" + _pick(rng, _two(rng, 0, 59), ["59", "60"])
            if rng.random() < 0.4:
                s += "." + "".join(rng.choice(_DIG) for _ in range(rng.randint(0, 7)))
        r = rng.random()
        if r < 0.3:
            s += "Z"
        elif r < 0.6:
            s += rng.choice("+-") + _two(rng, 0, 14) + rng.choice([":", ""]) + rng.choice(["00", "30", "45", _two(rng, 0, 99)])
        elif r < 0.66:
            s += rng.choice(["z", "+5", "+0530:", "UTC", "+05:3", "-", "Z "])
    if rng.random() < 0.12:
        s = rng.choice(_WS) + s
    if rng.random() < 0.12:
        s = s + rng.choice(_WS)
    if rng.random() < 0.06:
        uni = rng.choice(_UNI)
        s = "".join(uni[int(ch)] if ch in _DIG and rng.random() < 0.8 else ch for ch in s)
    return s


def _mutate(rng, s):
    i = rng.randrange(len(s) + 1)
    op = rng.random()
    ch = rng.choice(_ALPHA)
    if op < 0.34 and s:
        return s[:i % len(s)] + ch + s[i % len(s) + 1:]
    if op < 0.67:
        return s[:i] + ch + s[i:]
    return s[:i % max(len(s), 1)] + s[i % max(len(s), 1) + 1:] if s else s


def _strings(n):
    rng = random.Random(103)
    out = [_valid(rng) for _ in range(n * 6 // 10)]
    out += [_mutate(rng, rng.choice(out)) for _ in range(n - len(out))]
    return out


def _py_trim_len(s):
    return len(s.strip())


@needs_db
def test_the_new_parser_equals_the_old_one_on_every_generated_string(db):
    """Old (0fbf225, pg_temp) against new, float8 for float8, NULL for NULL: pdate_ms, pdate_only and the clock
    read through time_of_day on two zones. Any difference is printed in full and fails the test."""
    strings = _strings(N)
    values = [json.dumps(s) for s in strings] + ["1", "null", "true", "[]", '{"a": 1}', "1e400", '""']
    db.execute("DROP TABLE IF EXISTS pg_temp.t103")
    db.execute("CREATE TEMP TABLE t103 (i int, j jsonb)")
    with db.cursor() as cur, cur.copy("COPY t103 (i, j) FROM STDIN") as copy:
        for i, v in enumerate(values):
            copy.write_row((i, v))
    diff = db.execute("""
        SELECT i, j::text,
               pg_temp.old_pdate_ms(j), xpr.pdate_ms(j), pg_temp.old_pdate_only(j), xpr.pdate_only(j),
               pg_temp.old_time_of_day(j, 'America/Denver'), xpr.time_of_day(j, 'America/Denver'),
               pg_temp.old_time_of_day(j, 'Pacific/Kiritimati'), xpr.time_of_day(j, 'Pacific/Kiritimati')
          FROM t103
         WHERE pg_temp.old_pdate_ms(j) IS DISTINCT FROM xpr.pdate_ms(j)
            OR pg_temp.old_pdate_only(j) IS DISTINCT FROM xpr.pdate_only(j)
            OR pg_temp.old_time_of_day(j, 'America/Denver') IS DISTINCT FROM xpr.time_of_day(j, 'America/Denver')
            OR pg_temp.old_time_of_day(j, 'Pacific/Kiritimati') IS DISTINCT FROM xpr.time_of_day(j, 'Pacific/Kiritimati')
         ORDER BY i""").fetchall()
    parsed = db.execute("SELECT count(*) FILTER (WHERE xpr.pdate_ms(j) IS NOT NULL), "
                        "count(*) FILTER (WHERE xpr.pdate_only(j)) FROM t103").fetchone()
    # what the generated strings covered, for the report (the edges note 1 asks about)
    trims_differ = [s for s in strings if _py_trim_len(s) != len(s.strip(" \t\n\r\f\x0b"))]
    ten = [s for s in trims_differ if _py_trim_len(s) == 10]
    print(f"\nT-103 differential: {len(values):,} values ({len(strings):,} generated strings); "
          f"{parsed[0]:,} parse, {parsed[1]:,} of them bare dates; {len(diff)} differ.")
    print(f"  strings whose Python trim and ASCII trim differ: {len(trims_differ):,}; "
          f"of those exactly 10 long after Python's trim: {len(ten):,} "
          f"(parsing: {sum(1 for s in ten if _py_ms(s) is not None):,})")
    for row in diff[:50]:
        print("  DIFFERS:", row)
    assert not diff, f"{len(diff)} values differ between the old parser and the new (printed above)"
    assert len(strings) >= min(N, 200000) and parsed[0] > len(strings) // 5
