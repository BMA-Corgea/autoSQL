"""picks/zones.py — the clock a pick reads its times on (T-98, GA-68 Q7).

A pick names its zone ("America/Denver"); every reading of a time in that zone that the pick's
expression does NOT do per row is done here, once, in Python, with the same ``zoneinfo`` data
GIMS's evaluator reads:

* a picked wall time ("after Aug 20, 5:00 PM") becomes one UTC instant: on a day the clocks go
  back, the FIRST of the two; a time the clocks skip is refused in plain words;
* a time of day and a zone read as a person says them ("5:00 PM", "Denver time").

The per-row reading — ``time_of_day(t, zone)`` — is the expression language's, in both
engines. T-101: where this database's clock and Python's disagree (D, :func:`disagreements`), a
row's reading is checked against D and refused by name (``xpr.clock``); :func:`refusal_words`
turns that refusal into the sentence the screen shows.
"""

from __future__ import annotations

import datetime as _dt
import re
import threading
import zoneinfo
from zoneinfo import ZoneInfo

from . import times as _times

__all__ = ["ZoneError", "label", "place", "wall_instant", "clock_words",
           "refusal_words", "offered", "links", "marks", "note_words", "UNKNOWN_WORDS",
           "disagreements", "clock_check", "ZoneUnknown"]

_UTC = _dt.timezone.utc
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ZoneError(ValueError):
    """A reading of a time this zone's clock can't give, in words a person reads."""


def place(zone: str) -> str:
    """The place a zone is named for: ``America/Argentina/Buenos_Aires`` → ``Buenos Aires``."""
    return zone.rsplit("/", 1)[-1].replace("_", " ")


def label(zone: str) -> str:
    """How the screen names a zone: ``Denver time``, ``UTC``; a fixed offset with no place
    (``Etc/GMT+12``, whose sign runs backwards) as ``UTC−12``."""
    if zone in ("UTC", "Etc/UTC", "Etc/UCT", "Etc/Universal", "Etc/Zulu", "Etc/GMT", "Etc/GMT0",
                "Etc/GMT+0", "Etc/GMT-0", "Etc/Greenwich"):
        return "UTC"
    m = re.fullmatch(r"Etc/GMT([+-])(\d{1,2})", zone)
    if m:
        return f"UTC{'−' if m.group(1) == '+' else '+'}{int(m.group(2))}"
    return f"{place(zone)} time"


def _text(moment: _dt.datetime) -> str:
    """An instant in the data's fixed form, its year at four digits (t98-24: strftime writes year 1 as "1", which
    compares after every fixed-width time; a day's ends are ``picks.view._day_start`` and ``_day_end``)."""
    return _times.fixed_text(moment.astimezone(_UTC))


def _span_words(seconds: int) -> str:
    if seconds % 3600 == 0:
        h = seconds // 3600
        return "an hour" if h == 1 else f"{h} hours"
    return f"{seconds // 60} minutes"


def wall_instant(day: _dt.date, hh: int, mm: int, ss: int, zone: str) -> str:
    """A wall time on ``zone``'s clock → its UTC text.  Twice that day (the clocks went back):
    the first.  Never that day (the clocks skipped it): refused, in words.  Its instant before
    year 1 or after 9999 (on the calendar's first or last day, t98-23): refused, in words."""
    z = ZoneInfo(zone)
    wall = _dt.datetime(day.year, day.month, day.day, hh, mm, ss)
    first = wall.replace(tzinfo=z, fold=0)
    try:
        back = first.astimezone(_UTC).astimezone(z).replace(tzinfo=None)
    except OverflowError:
        raise ZoneError(
            f"{clock_words(hh * 3600 + mm * 60 + ss)} on {_MONTHS[day.month - 1]} {day.day}, {day.year} "
            f"in {label(zone)} is outside the years 1 to 9999 that times are read in."
        ) from None
    if back != wall:
        jump = int((wall.replace(tzinfo=z, fold=1).utcoffset() - first.utcoffset()).total_seconds())
        jump = abs(jump) or 3600
        raise ZoneError(
            f"{clock_words(hh * 3600 + mm * 60 + ss)} doesn't happen on "
            f"{_MONTHS[day.month - 1]} {day.day} in {label(zone)}: the clocks go forward "
            f"{_span_words(jump)}."
        )
    return _text(first)


def clock_words(seconds: int) -> str:
    """Seconds since midnight as a clock face reads them: ``61200`` → ``5:00 PM``; seconds
    shown only when not zero (``5:00:15 PM``)."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    hour = h % 12 or 12
    tail = f":{s:02d}" if s else ""
    return f"{hour}:{m:02d}{tail} {'AM' if h < 12 else 'PM'}"


_GUARD_DIFFERS = re.compile(r"time zone (.+?): this database's clock differs from the evaluator's on (\d{4})-(\d{2})-(\d{2})")
_GUARD_UNKNOWN = re.compile(r"time zone (.+?): (this database does not know it|no clock was handed over)")


def refusal_words(message: str) -> str:
    """The zone guard's refusal (XPR05) as the screen says it."""
    m = _GUARD_DIFFERS.search(message)
    if m:
        zone, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (f"{label(zone)} can't read these times: this computer and its database disagree "
                f"about {place(zone)}'s clocks on {_MONTHS[mo - 1]} {d}, {y}, and this question reads "
                f"a time from then.")
    m = _GUARD_UNKNOWN.search(message)
    if m:
        return f"{label(m.group(1))} can't be used yet: this computer's database doesn't know it."
    return "That time zone can't be used yet: this computer and its database disagree about it."


# ── the clock setting's list ─────────────────────────────────────────────────

_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")


def links() -> dict:
    """Old names for a place (``Asia/Calcutta`` → ``Asia/Kolkata``), from the zone data
    Python reads; empty when that data carries no list of them."""
    out = {}
    for base in zoneinfo.TZPATH:
        try:
            text = open(f"{base}/tzdata.zi", encoding="utf-8").read()
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "L":
                out[parts[2]] = parts[1]
        break
    return out


def offered(names, link_map=None) -> list:
    """The list the screen offers: one entry per place, UTC first then by area and place. An old
    name whose place is listed under its current name is left out (both engines still accept
    it, so a browser that reports one is still read), and so is every fixed offset but UTC."""
    link_map = links() if link_map is None else link_map
    names = set(names)
    out = []
    for z in names:
        if z != "UTC" and (z.startswith("Etc/") or link_map.get(z) in names):
            continue
        out.append({"zone": z, "label": label(z), "place": "UTC" if z == "UTC" else place(z),
                    "area": "" if z == "UTC" else z.split("/", 1)[0]})
    return sorted(out, key=lambda e: (e["zone"] != "UTC", e["area"], e["place"], e["zone"]))


#: T-101: the one reason a zone is greyed in the list.
UNKNOWN_WORDS = "Not available: this computer's database doesn't know it."


def _when(d) -> str:
    return str(d.year) if d.year < 1970 else f"{_MONTH_NAMES[d.month - 1]} {d.year}"


def note_words(first, last, to_the_end: bool) -> str:
    """T-101: a zone the two clocks disagree on only in some period stays selectable, with that
    period in one line: "Times before 1970 ..." when every difference is history, "Times from
    November 2026 on ..." when they run to the end of what is compared, else from .. to."""
    if last.year < 1970:
        return "Times before 1970 can't be read on this clock."
    if to_the_end:
        return f"Times from {_when(first)} on can't be read on this clock."
    if first.year < 1970:
        return f"Times before {_when(last)} can't be read on this clock."
    return f"Times from {_when(first)} to {_when(last)} can't be read on this clock."


#: The list's lines read both clocks every 30 days at noon from 1800 through 2100 (about 3 s for
#: every zone, once per process). They are advice for the list: each question's own check against
#: D (xpr.clock, T-101) decides, row by row.
_MARK_SAMPLES = tuple(range(-5364662400 + 43200, 4133980800, 30 * 86400))
_MARK_CACHE: dict = {}
_MARK_LOCK = threading.Lock()


def _python_offsets(zone: str, samples) -> list:
    z = ZoneInfo(zone)
    return [int(_dt.datetime.fromtimestamp(t, z).utcoffset().total_seconds()) for t in samples]


_MARK_SQL = """
SELECT z, array_agg(extract(epoch FROM ((to_timestamp(t) AT TIME ZONE z)
                                        - (to_timestamp(t) AT TIME ZONE 'UTC')))::int ORDER BY t)
  FROM unnest(%(zones)s::text[]) AS z, unnest(%(samples)s::bigint[]) AS t
 GROUP BY z
"""


def marks(conn, names, cache: bool = True) -> dict:
    """``{zone: (why, note)}``: ``why`` greys a zone this database doesn't know (UNKNOWN_WORDS);
    ``note`` is the one line for a zone the two clocks disagree on in some period, which stays
    selectable (T-101); both None for a zone they agree on. Built-in SQL only, so it needs no
    runtime function; cached per process and database."""
    key = (conn.info.host, conn.info.port, conn.info.dbname)
    names = sorted(set(names))
    with _MARK_LOCK:
        known = _MARK_CACHE.setdefault(key, {}) if cache else {}
        todo = [z for z in names if z not in known]
        if todo:
            in_db = {r[0] for r in conn.execute(
                "SELECT name FROM pg_timezone_names WHERE name = ANY(%(z)s)", {"z": todo}).fetchall()}
            for z in todo:
                if z not in in_db:
                    known[z] = (UNKNOWN_WORDS, None)
            asked = [z for z in todo if z in in_db]
            if asked:
                rows = conn.execute(_MARK_SQL, {"zones": asked, "samples": list(_MARK_SAMPLES)}).fetchall()
                for z, theirs in rows:
                    ours = _python_offsets(z, _MARK_SAMPLES)
                    differ = [t for t, a, b in zip(_MARK_SAMPLES, ours, theirs) if a != b]
                    day = lambda t: _dt.datetime.fromtimestamp(t, _UTC).date()  # noqa: E731
                    known[z] = ((None, note_words(day(differ[0]), day(differ[-1]), differ[-1] == _MARK_SAMPLES[-1]))
                                if differ else (None, None))
        return {z: known[z] for z in names}


# ── D(zone): where this database's clock and Python's disagree (T-101) ─────────────────────────
#
# The statement reads a zone's clock with the SERVER's time-zone data, the second engine with
# Python's. Rather than refuse a zone that differs anywhere in 1800..2100 (T-98's per-statement
# guard), each row's clock reading is checked against D, the instants the two disagree on: a row
# outside D reads the same on both, a row inside it is refused by name (xpr.clock). D is worked
# out once per zone and database -- Python's clock (the compiler's zone_transitions) against the
# server's at the second before and the second of every change of Python's, weekly noons to 1970
# and daily noons from 1970 through 2100 -- as half-open intervals [lo, hi) of epoch seconds, each
# end at the nearest sample the two agree on, +-Infinity where the differences run off either end.
#
# Cached by (host, port, database, pg_postmaster_start_time()) and Python's clock for the zone.
# A system-tzdata Postgres reads zone files as a backend first loads a zone, so a package upgrade
# changes the server's rules with no restart: EVERY question therefore re-reads the server's
# offsets at a few thousand instants (Python's change instants and every fourth week / thirtieth
# day's noon: a fixed amount of work a zone, whatever the collection's size) and works D out
# again when any of them moved.

NEG_INF, POS_INF = float("-inf"), float("inf")


class ZoneUnknown(ZoneError):
    """This computer's database doesn't know a zone the question reads a clock on."""


#: The server's offset at instant {t} on zone {z}, in seconds. One template, so a test can stand a
#: schema-local function in for an upgraded zone file.
_SERVER_OFFSET = ("extract(epoch FROM ((to_timestamp({t}) AT TIME ZONE {z}) "
                  "- (to_timestamp({t}) AT TIME ZONE 'UTC')))::int")

_FULL_SQL = """
WITH c AS (
  SELECT t, want FROM (
    SELECT (%(st)s::bigint[])[i] - 1 AS t, (%(of)s::int[])[i - 1] AS want
      FROM generate_subscripts(%(st)s::bigint[], 1) AS i WHERE i > 1
    UNION ALL
    SELECT (%(st)s::bigint[])[i], (%(of)s::int[])[i] FROM generate_subscripts(%(st)s::bigint[], 1) AS i
    UNION ALL
    SELECT g, (%(of)s::int[])[width_bucket(g, %(st)s::bigint[])] FROM (
        SELECT generate_series(-5364619200::bigint, -1::bigint, 604800::bigint) AS g
        UNION ALL
        SELECT generate_series(43200::bigint, 4133937600::bigint, 86400::bigint)) AS n
  ) AS x
), s AS (
  SELECT t, bool_or({off} IS DISTINCT FROM want) AS bad FROM c GROUP BY t
), w AS (
  SELECT t, bad, lag(t) OVER o AS pt, lead(t) OVER o AS nt,
         coalesce(lag(bad) OVER o, false) AS pb, coalesce(lead(bad) OVER o, false) AS nb
    FROM s WINDOW o AS (ORDER BY t)
)
SELECT t, pt, nt, pb, nb FROM w WHERE bad AND (NOT pb OR NOT nb) ORDER BY t
"""

_RECHECK_SQL = ("SELECT 1, array_agg({off} ORDER BY t) "
                "FROM unnest(%(ts)s::bigint[]) AS t")
_NAMES: dict = {}


def _known_names(conn, started: str) -> frozenset:
    """The zones this database knows, read once per server start (pg_timezone_names reads every
    zone file: too dear for each question). A zone file a package upgrade REMOVES without a restart
    is not seen until the next one; the reading then fails loudly in the database, never quietly."""
    key = (conn.info.host, conn.info.port, conn.info.dbname, started)
    if key not in _NAMES:
        _NAMES[key] = frozenset(r[0] for r in conn.execute("SELECT name FROM pg_timezone_names").fetchall())
    return _NAMES[key]

_GAP_CACHE: dict = {}
_GAP_LOCK = threading.Lock()
#: How many full comparisons have run (a test reads it: a second question reads D from the cache).
full_comparisons = 0


def _python_clock(zone: str):
    from . import env
    starts, offsets = env.get("compiler").zone_transitions(zone)
    return tuple(starts), tuple(offsets)


def _recheck_samples(starts) -> tuple:
    """Python's change instants (the second before and the second of each), every fourth weekly
    noon before 1970 and every thirtieth daily noon from 1970: all of them instants the full
    comparison reads, so a re-check can only see what the full comparison would."""
    out = set()
    for s in starts[1:]:
        out.update((s - 1, s))
    out.update(range(-5364619200, 0, 4 * 604800))
    out.update(range(43200, 4133937600 + 1, 30 * 86400))
    return tuple(sorted(out))


def _off_sql(sql: str) -> str:
    return sql.replace("{off}", _SERVER_OFFSET.format(t="t", z="%(z)s::text"))


def _gaps_from(rows) -> tuple:
    gaps, lo = [], None
    for t, pt, nt, pb, nb in rows:
        if not pb:
            lo = NEG_INF if pt is None else float(pt + 1)
        if not nb:
            gaps.append((lo, POS_INF if nt is None else float(nt)))
    return tuple(gaps)


def disagreements(conn, zone: str, transitions=None) -> tuple:
    """D(zone) on ``conn``'s database: ``((lo, hi), ...)``, empty when the two clocks agree at every
    instant compared. Re-checks the server cheaply first; works D out again only when it moved."""
    global full_comparisons
    starts, offsets = _python_clock(zone) if transitions is None else map(tuple, transitions(zone))
    samples = _recheck_samples(starts)
    started = conn.execute("SELECT pg_postmaster_start_time()::text").fetchone()[0]
    if zone not in _known_names(conn, started):
        raise ZoneUnknown(f"{label(zone)} can't be used yet: this computer's database doesn't know it.")
    now = conn.execute(_off_sql(_RECHECK_SQL), {"ts": list(samples), "z": zone}).fetchone()[1]
    key = (conn.info.host, conn.info.port, conn.info.dbname, zone)
    with _GAP_LOCK:
        hit = _GAP_CACHE.get(key)
        if hit and hit["started"] == started and hit["python"] == (starts, offsets) and hit["seen"] == tuple(now):
            return hit["gaps"]
        rows = conn.execute(_off_sql(_FULL_SQL), {"st": list(starts), "of": list(offsets), "z": zone}).fetchall()
        full_comparisons += 1
        gaps = _gaps_from(rows)
        _GAP_CACHE[key] = {"started": started, "python": (starts, offsets), "seen": tuple(now), "gaps": gaps}
        return gaps


def clock_check(conn, transitions=None):
    """The resolver one question compiles with (``picks.env.checking_zones``): zone → D, re-checked
    once per zone per question. ``transitions`` stands in for the compiler's (its own tests)."""
    memo: dict = {}

    def gaps(zone: str) -> tuple:
        if zone not in memo:
            memo[zone] = disagreements(conn, zone, transitions)
        return memo[zone]
    return gaps
