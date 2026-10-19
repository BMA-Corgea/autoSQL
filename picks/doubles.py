"""picks/doubles.py — T-112: when a double HOLDS a number.

GIMS's expression language computes and compares in doubles, on both engines (R7, T-61). A stored number a double
can't hold has no honest reading there: the statement refuses some of them (past DBL_MAX, XPR01; below the smallest
double, 22003) and rounds the rest, and the second engine read them all silently (``1e-400`` as ``0.0``). The rule:

    A number is HELD when the double nearest to it, written the way Postgres writes a double, is the same number.

Postgres's way (``float8out`` at ``extra_float_digits`` >= 1) is the shortest decimal STRICTLY inside the double's
rounding interval -- of that length, the closest to the double, a tie to the even digit. Python's ``repr`` differs on
exact midpoints (``1e23``, and integral doubles between 1e16 and 1e18: Python takes a midpoint when the double is
even, Postgres never does), so one printer is used by everything that decides "held": this emulation, measured equal
to the live ``float8out`` on 1,201,488 doubles (``.autodev/evidence/T-112/``) and pinned by a differential test.
The statement side asks the database itself (probe member d, ``probes.py``); the second engine asks this module.

``-0`` is ``0``. The literal ``1.7976931348623157e+308`` and beyond is LARGE (B15's threshold, member a's literal);
a nonzero number whose double is 0 is SMALL; anything else not held has more DIGITS than a double holds.
"""

from __future__ import annotations

import math
import re
import struct
from decimal import Decimal
from fractions import Fraction
from typing import Optional

__all__ = ["DBL_MAX_TEXT", "LARGE", "SMALL", "DIGITS", "pg_shortest", "kind", "numeric_text"]

#: member a's literal (B15): at or past it a number is LARGE, conservatively, exactly as the magnitude probe refuses
DBL_MAX_TEXT = "1.7976931348623157e+308"
_DBL_MAX = Decimal(DBL_MAX_TEXT)
_TWO_53 = 2 ** 53

LARGE, SMALL, DIGITS = "large", "small", "digits"

#: A number written as text, as the language reads one (``expr._to_num``): inside Python's ``strip()`` spaces (29 of
#: them, not only ASCII's six), digits of any script (``\d``, as ``float()`` and ``Decimal()`` read them), an
#: optional sign, point and exponent. The runtime's ``xpr.num`` reads the same since T-6 variant C (a-chk's H2).
_TEXT_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _bits(d: float) -> int:
    return struct.unpack("<q", struct.pack("<d", d))[0]


def _from_bits(b: int) -> float:
    return struct.unpack("<d", struct.pack("<q", b))[0]


def _interval(a: float):
    """The exact rounding interval (open) of the positive finite double ``a``: its two midpoints, as Fractions."""
    b = _bits(a)
    d = Fraction(a)
    lo = Fraction(_from_bits(b - 1)) if b > 0 else Fraction(0)
    hi = Fraction(_from_bits(b + 1)) if a != 1.7976931348623157e308 else d + (d - lo)
    return (lo + d) / 2, (d + hi) / 2


def pg_shortest(x: float) -> str:
    """``x`` (a finite double) written as Postgres's ``float8out`` writes it.

    Python's ``repr`` is the shortest decimal that reads back as ``x``; when it lies strictly inside ``x``'s rounding
    interval it is Postgres's choice too. Only when it sits exactly on a midpoint (Postgres won't take one) is the
    next candidate searched for: per length, the decimals just below and just above ``x``, strictly inside, the
    closer. Two never tie here: equidistant neighbours of ``x`` both inside its interval need a spacing below the
    double's gap, which (``2x = (2n+1)*10**b``) means a gap below 1, and there a midpoint has more digits than ``x``
    itself, so ``repr`` is never on one and this search never runs (0 such on the differential's 222,730)."""
    if x == 0:
        return "-0" if math.copysign(1.0, x) < 0 else "0"
    if math.isinf(x) or x != x:
        raise ValueError(f"not a finite double: {x!r}")
    a = abs(x)
    sign = "-" if x < 0 else ""
    r = repr(a)
    m_lo, m_hi = _interval(a)
    if m_lo < Fraction(Decimal(r)) < m_hi:
        return sign + r
    d = Fraction(a)
    e = Decimal(a).adjusted()                       # the exponent of the leading digit (exact: no context)
    for k in range(1, 18):
        q = Fraction(10) ** (e - k + 1)             # one unit in the k-th significant digit
        n_down = math.floor(d / q)
        candidates = [n for n in (n_down, n_down + 1) if m_lo < n * q < m_hi]
        if candidates:
            n = min(candidates, key=lambda c: abs(c * q - d))
            s = format(Decimal(n).scaleb(e - k + 1), "e")
            return sign + s
    return sign + r                                 # unreachable: 17 digits always reach the interval


def kind(v) -> Optional[str]:
    """``None`` when the number ``v`` (an ``int`` or a ``Decimal``, never a ``bool``) is held; else LARGE, SMALL or
    DIGITS. Fast where it can be: every integer up to 2^53 is a double, and a decimal of at most 15 significant digits
    below 1e15 and at or above 1e-307 survives one (DBL_DIG) without lying on a midpoint (those need >= 2^56)."""
    if isinstance(v, int):
        if -_TWO_53 <= v <= _TWO_53:
            return None
        d = Decimal(v)
    else:
        d = v
        if not d.is_finite():
            return LARGE
        if d.is_zero():
            return None
        digits = d.as_tuple().digits
        significant = len(digits)
        while significant > 1 and digits[significant - 1] == 0:
            significant -= 1
        if significant <= 15 and -307 <= d.adjusted() <= 14:
            return None
    if d.copy_abs() >= _DBL_MAX:                    # exact: abs() rounds to the default context's 28 digits (M1)
        return LARGE
    f = float(d)                                    # correctly rounded, half to even, as Postgres reads it
    if f == 0.0:
        return SMALL
    return None if Decimal(pg_shortest(f)) == d else DIGITS


def numeric_text(s: str) -> Optional[Decimal]:
    """The number a text value reads as where the language coerces text to a number (Python's ``strip()``, then
    its pattern), or ``None`` when the language reads none there."""
    t = s.strip()
    if not _TEXT_NUMBER.fullmatch(t):
        return None
    return Decimal(t)
