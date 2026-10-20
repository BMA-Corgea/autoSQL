"""picks/times.py — T-114: when a stored value is a time, as the second engine and the setup's Python side read it.

GIMS writes its times as ``isoformat()`` does (``…+00:00``, whole or with 6 fraction digits), a node writes
``….123456Z``, a browser ``….123Z``, an edited time arrives naive (``…T05:03``), a pass-through anything at all. The
engine read only ``YYYY-MM-DDTHH:MM:SSZ``, so none of the owner's times were times. The rule now (spec §2):

* A string is a READABLE time when it is ``YYYY-MM-DD``, ``T`` or a space, ``HH:MM:SS``, an optional fraction of 1-6
  digits, and ``Z``, ``+-HH:MM`` or ``+-HHMM`` with an offset of at most 14:59 -- in ASCII -- on a real day of the
  calendar, and its UTC instant lies inside years 1..9999. Read, it is that instant, to the microsecond. A bare date
  ``YYYY-MM-DD`` reads as its UTC midnight (T-88).
* Everything else is no readable time: naive forms, lowercase ``t``/``z``, 7+ digits (Postgres would round them and
  Python truncate), an offset with seconds or past 14:59 (Postgres refuses past 15:59), hour 24, a second 60, a day
  the calendar lacks, an instant outside years 1..9999 (Python can't hold one), surrounding space.
* What LOOKS like a time (``looks_like``) is wider -- naive, lowercase, any digits, any offset spelling -- and decides
  only whether a field is a time field (``kind_counts``; ``picks.view._kind``).

T-103's pattern: one pattern decides, then every field is read at its known place. The statement states the same
rule in SQL (runtime ``xpr.time_at``), and nothing here is shared with it (W12), so the two can disagree and be
caught (``parity/tests/test_t114_times.py``'s differential).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Tuple

__all__ = ["READABLE", "LOOKS", "instant", "utc_text", "fixed_text", "has_time", "looks_like", "reading",
           "kind_counts"]

#: a readable time (fullmatch; ASCII digits)
READABLE = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ](?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?"
            r"(?:Z|[+-](?:0[0-9]|1[0-4]):?[0-5][0-9])")
#: what looks like a time (fullmatch): a bare date, or a date with any time-of-day spelling
LOOKS = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:[.,][0-9]+)?)?"
         r"(?:[Zz]|[+-][0-9]{2}(?::?[0-9]{2}(?::?[0-9]{2})?)?)?)?")
_READABLE = re.compile(READABLE)
_LOOKS = re.compile(LOOKS)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def instant(value: Any) -> Optional[datetime]:
    """The UTC instant a stored value reads as (an aware datetime), or ``None`` when it is no readable time."""
    if not isinstance(value, str):
        return None
    if len(value) == 10:
        if not _DATE.fullmatch(value):
            return None
        try:
            return datetime(int(value[0:4]), int(value[5:7]), int(value[8:10]), tzinfo=timezone.utc)
        except ValueError:
            return None                                     # no such day
    if not _READABLE.fullmatch(value):
        return None
    # the pattern matched, so: the date at 0-9, the separator at 10, HH:MM:SS at 11-18, then a fraction, a zone
    try:
        local = datetime(int(value[0:4]), int(value[5:7]), int(value[8:10]),
                         int(value[11:13]), int(value[14:16]), int(value[17:19]))
    except ValueError:
        return None                                         # no such day
    rest = value[19:]
    micro = 0
    if rest[0] == ".":
        k = 1
        while rest[k] in "0123456789":                      # 1-6 digits, then the zone (the pattern says so)
            k += 1
        micro = int(rest[1:k].ljust(6, "0"))
        rest = rest[k:]
    if rest == "Z":
        shift = timedelta(0)
    else:
        sign = 1 if rest[0] == "+" else -1
        shift = sign * timedelta(hours=int(rest[1:3]), minutes=int(rest[-2:]))
    try:
        return (local + timedelta(microseconds=micro) - shift).replace(tzinfo=timezone.utc)
    except OverflowError:
        return None                                         # the instant leaves years 1..9999


def utc_text(at: datetime) -> str:
    """An instant at the one width a time is compared at: ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (text order is time order)."""
    return (f"{at.year:04d}-{at.month:02d}-{at.day:02d}T{at.hour:02d}:{at.minute:02d}:{at.second:02d}"
            f".{at.microsecond:06d}Z")


def fixed_text(at: datetime) -> str:
    """An instant in the engine's one fixed form, to the second (``YYYY-MM-DDTHH:MM:SSZ``): labels, spans."""
    return f"{at.year:04d}-{at.month:02d}-{at.day:02d}T{at.hour:02d}:{at.minute:02d}:{at.second:02d}Z"


def has_time(value: Any) -> bool:
    """A readable time with a time of day (not a bare date)."""
    return isinstance(value, str) and len(value) > 10 and instant(value) is not None


def looks_like(value: Any) -> bool:
    """Does the value look like a time (§2.3) -- read or not?"""
    return isinstance(value, str) and _LOOKS.fullmatch(value) is not None


def reading(value: Any):
    """A time field's value as a filter or a sort reads it (spec §4, (A)): a time's instant at the one width; a bare
    date as itself, ``YYYY-MM-DD``, whose midnight is the question's clock's (spec §2.1: the view compares it as a
    date, and to the language it has no time of day); ``None`` when it is JSON null; ``False`` for anything else --
    present, but no time: it then matches no comparison, and ``present`` / ``blank`` keep their meaning."""
    if value is None:
        return None
    at = instant(value)
    if at is None:
        return False
    return value if len(value) == 10 else utc_text(at)


def kind_counts(values: Iterable[Any]) -> Tuple[int, int, int, int]:
    """What decides a field's kind, over its text values (``""`` is blank, not counted): (how many, how many look
    like a time, how many are readable times with a time of day, how many are NOT a date). ``picks.view._FORMS_SQL``
    counts the same four numbers in SQL."""
    n = looks = readable = not_date = 0
    for v in values:
        if not isinstance(v, str) or v == "":
            continue
        n += 1
        if _LOOKS.fullmatch(v):
            looks += 1
        if len(v) > 10 and instant(v) is not None:
            readable += 1
        if not _DATE.fullmatch(v):
            not_date += 1
    return n, looks, readable, not_date
