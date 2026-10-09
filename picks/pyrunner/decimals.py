"""The exact-decimal rule, Python half — T-2 spec §7.2, plan B7, ruling R7's edge.

Two things live here and nowhere else (plan §4.5):

  * ``q6(x)``          — round half-up to exactly 6 decimal places.  The SQL
                         side's twin is ``round(x, 6)`` on a ``numeric``.
  * ``is_jsonb_number``— the one type check deciding whether a value counts as
                         a number, matching ``jsonb_typeof(v) = 'number'``.
                         Plan B7: "the check lives once, in
                         demo/pyrunner/decimals.py, and every caller uses it."

Why this module is strict to the point of rudeness
--------------------------------------------------
This demo's failure mode is a subtly wrong number that still runs clean.  The
two classic ways to produce one on the Python side are:

  1. rounding a tie to even (Python's default, ``ROUND_HALF_EVEN``) where a
     person checking by hand rounds it away from zero — caught here by pinning
     ``ROUND_HALF_UP`` explicitly (spec §7.2 item 2; mutation M8 is exactly
     "leave the default in place");
  2. letting a binary ``float`` stand in for a decimal value — caught here by
     ``q6`` *refusing* floats outright rather than converting them.  A float
     reaching a rounding site means an upstream caller did arithmetic outside
     ``Decimal`` (e.g. ``sum(ints) / count`` — true division returns a float),
     which is precisely the drift B7 exists to prevent.  Loud failure now
     beats a quiet wrong digit later.

Nothing here reads the ambient ``decimal`` context (spec §7.2 item 4: no
other precision setting or rounding mode is relied on anywhere).  ``q6``
carries its own explicit ``Context``, so a caller that has fiddled with
``getcontext()`` cannot change what this function returns.
"""

from decimal import Context, Decimal, ROUND_HALF_UP

__all__ = ["q6", "is_jsonb_number", "SIX_PLACES"]

#: The quantum: six decimal places, exactly (spec §7.2 item 2).
SIX_PLACES = Decimal("0.000001")

# An explicit context so q6 depends on nothing ambient.  prec=1000 is far
# beyond any magnitude this demo can produce (the runtime guard refuses
# |x| >= 1e400 and admits 1e300, spec AC-17; a 1e300 quantized to 6 places
# needs ~307 significant digits), so quantize is always exact here, and a
# value that somehow exceeds it raises rather than rounding silently:
# every trap is left at the Context default (InvalidOperation traps).
_Q6_CONTEXT = Context(prec=1000, rounding=ROUND_HALF_UP)


def q6(x):
    """Round *x* half-up to exactly 6 decimal places. Ties go away from zero.

    Spec §7.2 item 2: every division is followed immediately by this call, on
    both panes; both panes display and compare the rounded value and nothing
    compares unrounded intermediates.  Postgres's twin is ``round(x, 6)`` on a
    ``numeric``, documented to round half away from zero — AC-24(b) is the
    test that the two halves agree on a tie.

    Accepts ``Decimal`` and ``int`` (ints are exact).  Refuses ``bool``,
    ``float``, ``None`` and everything else — see the module docstring for
    why refusal is the correct behaviour and not a convenience trade-off.

    Returns a ``Decimal`` with exponent -6 (i.e. exactly six places, trailing
    zeros kept), negative zero normalised to zero.
    """
    if isinstance(x, bool):
        # bool subclasses int; jsonb_typeof calls it 'boolean' (§7.2 item 5).
        raise TypeError("q6() refuses bool: booleans are not numbers here (spec §7.2 item 5)")
    if isinstance(x, float):
        raise TypeError(
            "q6() refuses float: a float at a rounding site means arithmetic "
            "left Decimal upstream (plan B7). Fix the caller; do not convert."
        )
    if isinstance(x, int):
        x = Decimal(x)  # exact by construction
    if not isinstance(x, Decimal):
        raise TypeError(f"q6() takes Decimal or int, got {type(x).__name__}")
    if not x.is_finite():
        # JSON has no NaN/Infinity and jsonb cannot hold one; a non-finite
        # Decimal here is an upstream bug, not a value to round.
        raise ValueError(f"q6() refuses non-finite Decimal {x!r}")
    result = x.quantize(SIX_PLACES, rounding=ROUND_HALF_UP, context=_Q6_CONTEXT)
    if result.is_zero() and result.is_signed():
        # Decimal("-0.0000001") quantizes to Decimal("-0.000000"); Postgres's
        # numeric has no negative zero, so normalise before display/compare.
        result = -result
    return result


def is_jsonb_number(v):
    """True iff Postgres's ``jsonb_typeof`` would call *v* ``'number'``.

    The one-character trap this exists for (spec §7.2 item 5, plan B7):
    Python's ``bool`` subclasses ``int``, so a bare
    ``isinstance(v, (int, float))`` scores ``True`` as 1 while the SQL side's
    ``jsonb_typeof`` calls it ``'boolean'`` and scores it as nothing — a real
    and unexplainable disagreement between the panes.  So: a value counts
    only if it is an ``int``, ``float`` or ``Decimal`` **and is not a bool**.

    (``float`` is accepted because ``record_f`` — the plain ``json.loads``
    parse that feeds the vendored expr.py — represents JSON numbers as
    floats; the *classification* must agree between both parses even though
    the arithmetic path only ever uses the Decimal parse, B7.)
    """
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)
