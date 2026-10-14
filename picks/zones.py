"""picks/zones.py — the clock a pick reads its times on (T-98, GA-68 Q7).

A pick names its zone ("America/Denver"); every reading of a time in that zone that the pick's
expression does NOT do per row is done here, once, in Python, with the same ``zoneinfo`` data
GIMS's evaluator reads:

* a day ("is on Aug 20") becomes its two UTC ends, DST-correct: a day runs from its first
  instant to the next day's first instant (23 or 25 hours on a change day; a day whose midnight
  the clocks skip starts at the change itself);
* a picked wall time ("after Aug 20, 5:00 PM") becomes one UTC instant: on a day the clocks go
  back, the FIRST of the two; a time the clocks skip is refused in plain words;
* a time of day and a zone read as a person says them ("5:00 PM", "Denver time").

The per-row reading — ``time_of_day(t, zone)`` — is the expression language's, in both
engines, behind the compiler's zone guard (``xpr.zone_checked``). When the guard refuses a
zone, :func:`refusal_words` turns its message into the sentence the screen shows.
"""

from __future__ import annotations

import datetime as _dt
import re
import threading
import zoneinfo
from zoneinfo import ZoneInfo

__all__ = ["ZoneError", "label", "place", "day_span", "wall_instant", "clock_words",
           "refusal_words", "UTC_TEXT", "offered", "links", "marks", "mark_words"]

_UTC = _dt.timezone.utc
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: The fixed-width UTC text the data and both engines compare (T-88 ruling 1).
UTC_TEXT = "%Y-%m-%dT%H:%M:%SZ"


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
    return moment.astimezone(_UTC).strftime(UTC_TEXT)


def day_span(day: _dt.date, zone: str) -> tuple[str, str]:
    """The UTC ends of ``day`` on ``zone``'s clock: [its first instant, the next day's)."""
    z = ZoneInfo(zone)

    def first(d: _dt.date) -> _dt.datetime:
        # fold=0: of two midnights, the first; a skipped midnight maps to the change itself
        return _dt.datetime(d.year, d.month, d.day, tzinfo=z)

    return _text(first(day)), _text(first(day + _dt.timedelta(days=1)))


def _span_words(seconds: int) -> str:
    if seconds % 3600 == 0:
        h = seconds // 3600
        return "an hour" if h == 1 else f"{h} hours"
    return f"{seconds // 60} minutes"


def wall_instant(day: _dt.date, hh: int, mm: int, ss: int, zone: str) -> str:
    """A wall time on ``zone``'s clock → its UTC text.  Twice that day (the clocks went back):
    the first.  Never that day (the clocks skipped it): refused, in words."""
    z = ZoneInfo(zone)
    wall = _dt.datetime(day.year, day.month, day.day, hh, mm, ss)
    first = wall.replace(tzinfo=z, fold=0)
    back = first.astimezone(_UTC).astimezone(z).replace(tzinfo=None)
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


_GUARD_DIFFERS = re.compile(r"time zone (.+?): this database's clock differs from the evaluator's from (\d{4})-(\d{2})-(\d{2})")
_GUARD_UNKNOWN = re.compile(r"time zone (.+?): (this database does not know it|no clock was handed over)")


def refusal_words(message: str) -> str:
    """The zone guard's refusal (XPR05) as the screen says it."""
    m = _GUARD_DIFFERS.search(message)
    if m:
        zone, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (f"{label(zone)} can't be used yet: this computer and its database disagree "
                f"about {place(zone)}'s clocks from {_MONTHS[mo - 1]} {d}, {y}.")
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


def mark_words(first, last=None) -> str:
    """Why a zone can't be used, in one short line: "before 1970" when every difference is
    history, else the first date the two clocks differ (a year before 1970, a month after);
    or that the database doesn't know it."""
    if first is None:
        return "Not available: this computer's database doesn't know it."
    if last is not None and last.year < 1970:
        return "Not available: this computer and its database disagree on its clocks before 1970."
    when = str(first.year) if first.year < 1970 else f"{_MONTH_NAMES[first.month - 1]} {first.year}"
    return f"Not available: this computer and its database disagree on its clocks from {when}."


#: The list's marks read both clocks every 30 days at noon from 1800 through 2100 (about 3 s for
#: every zone, once per process). They are advice for the list: the zone guard in each statement
#: (xpr.zone_checked) decides, at the second.
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
    """``{zone: None}`` for a zone both clocks agree on, else ``{zone: mark_words(...)}``.
    Built-in SQL only, so it needs no runtime function; cached per process and database."""
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
                    known[z] = mark_words(None)
            asked = [z for z in todo if z in in_db]
            if asked:
                rows = conn.execute(_MARK_SQL, {"zones": asked, "samples": list(_MARK_SAMPLES)}).fetchall()
                for z, theirs in rows:
                    ours = _python_offsets(z, _MARK_SAMPLES)
                    differ = [t for t, a, b in zip(_MARK_SAMPLES, ours, theirs) if a != b]
                    day = lambda t: _dt.datetime.fromtimestamp(t, _UTC).date()  # noqa: E731
                    known[z] = mark_words(day(differ[0]), day(differ[-1])) if differ else None
        return {z: known[z] for z in names}


def use_words(zone: str, mark: str) -> str:
    """A list mark as the refusal of a question on that clock: ``Amsterdam time can't be used
    yet: this computer and its database disagree on its clocks before 1970.``"""
    return f"{label(zone)} can't be used yet: " + mark.removeprefix("Not available: ")
