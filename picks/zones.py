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
from zoneinfo import ZoneInfo

__all__ = ["ZoneError", "label", "place", "day_span", "wall_instant", "clock_words",
           "refusal_words", "UTC_TEXT"]

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
