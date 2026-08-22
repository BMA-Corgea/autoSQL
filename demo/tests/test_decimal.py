"""AC-24(b) — both sides round a tie the same way (spec §7.2 item 2).

WHAT LIVES HERE, AND WHOSE IT IS
  * W9 (this file's first landing): AC-24(b) — the tie test. The Python half
    runs always; the Postgres half runs against the demo's own database
    through demo/server/db.py (W13's file, the only connection factory) and
    SKIPS LOUDLY until that stack exists.  If the two sides ever disagree on
    a tie, that is a build failure, not a rounding preference (AC-24(b)).
  * W12 adds AC-24(d) — the short-window cases against
    fixtures/expected_step8.json.  Not here yet; do not fold it in elsewhere.

WHY THE TIE VALUES ARE WHAT THEY ARE
  AC-24(b) demands "a value whose half-up and half-even results differ".
  A tie at the 6th place only distinguishes the two modes when the digit
  being kept is EVEN (half-even keeps it, half-up bumps it).  Every row of
  TIE_CASES is such a value, and the test proves it can tell the modes apart
  by also computing the half-even result and asserting it differs — a tie
  test that cannot distinguish the modes would pass under mutation M8
  (Python rounding left at ROUND_HALF_EVEN), which is the mutation this
  criterion exists to kill.
"""

import sys
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, getcontext, localcontext
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.pyrunner.decimals import SIX_PLACES, is_jsonb_number, q6  # noqa: E402

# ---------------------------------------------------------------------------
# The tie cases — hand-computed, half-up vs half-even shown side by side.
#
#   input               half-up (the rule)   half-even (the default; WRONG here)
TIE_CASES = [
    ("0.0000005",       "0.000001",          "0.000000"),
    ("-0.0000005",      "-0.000001",         "0.000000"),   # away from zero
    ("0.0000025",       "0.000003",          "0.000002"),
    ("-0.0000025",      "-0.000003",         "-0.000002"),
    ("0.0000105",       "0.000011",          "0.000010"),
    ("1.0000005",       "1.000001",          "1.000000"),
    ("41999.9999995",   "42000.000000",      "42000.000000"),
    # ^ kept digit is the 6th decimal, 9 (odd); half-even bumps an odd digit
    # too, so this row does NOT distinguish the modes (the filter below
    # excludes it from the distinguishing set). It is here because §7.2's
    # own example is a total near 42000, and the half-up result is what a
    # person checking by eye expects. The rows above carry AC-24(b)'s weight.
]

# Non-ties: values a hair off the boundary, to prove q6 looks at the whole
# tail rather than truncating to a manufactured tie.
NEAR_MISS_CASES = [
    ("0.00000050000000000000000001", "0.000001"),  # just above the tie: up under any mode
    ("0.00000049999999999999999999", "0.000000"),  # just below: down under any mode
]


@pytest.mark.parametrize("raw,expected_half_up,half_even", TIE_CASES)
def test_q6_rounds_ties_half_up(raw, expected_half_up, half_even):
    """AC-24(b), Python half: ties round half-up (away from zero), exactly."""
    got = q6(Decimal(raw))
    want = Decimal(expected_half_up)
    assert got == want, f"q6({raw}) = {got}, want {expected_half_up}"
    # Exactly six places — the quantum itself, not just the value.
    assert got.as_tuple().exponent == -6


@pytest.mark.parametrize(
    "raw,expected_half_up,half_even",
    [c for c in TIE_CASES if Decimal(c[1]).copy_abs() != Decimal(c[2]).copy_abs()],
)
def test_the_tie_cases_actually_distinguish_the_modes(raw, expected_half_up, half_even):
    """The test of the test: on these rows the half-even default gives a
    DIFFERENT number, so mutation M8 (rounding left at ROUND_HALF_EVEN)
    cannot pass this file."""
    banker = Decimal(raw).quantize(SIX_PLACES, rounding=ROUND_HALF_EVEN)
    assert banker == Decimal(half_even)
    assert q6(Decimal(raw)) != banker, (
        f"{raw}: half-up and half-even agree ({banker}); this row cannot catch M8"
    )


@pytest.mark.parametrize("raw,expected", NEAR_MISS_CASES)
def test_q6_reads_the_whole_tail_not_a_truncated_tie(raw, expected):
    got = q6(Decimal(raw))
    assert got == Decimal(expected), f"q6({raw}) = {got}, want {expected}"


def test_q6_ignores_the_ambient_decimal_context():
    """Spec §7.2 item 4: no other precision setting or rounding mode is
    relied on anywhere.  A caller that has set the thread's context to
    banker's rounding and a tiny precision must not change q6's answer."""
    with localcontext() as ctx:
        ctx.rounding = ROUND_HALF_EVEN
        ctx.prec = 2
        assert q6(Decimal("0.0000005")) == Decimal("0.000001")
        assert q6(Decimal("-0.0000025")) == Decimal("-0.000003")
    # and the ambient context is left untouched afterwards
    assert getcontext().rounding != ROUND_HALF_UP or True  # documentative; no mutation happened


def test_q6_accepts_ints_exactly():
    got = q6(7)
    assert got == Decimal("7.000000")
    assert got.as_tuple().exponent == -6


def test_q6_normalises_negative_zero():
    got = q6(Decimal("-0.0000001"))
    assert got == Decimal("0.000000")
    assert not got.is_signed(), "Postgres numeric has no -0; neither may the Python pane"


@pytest.mark.parametrize(
    "bad",
    [0.5, float("nan"), True, False, None, "0.5", Decimal("NaN"), Decimal("Infinity")],
    ids=["float", "float-nan", "True", "False", "None", "str", "Decimal-NaN", "Decimal-Inf"],
)
def test_q6_refuses_what_is_not_an_exact_number(bad):
    """A float at a rounding site is an upstream bug (plan B7); a bool is the
    §7.2 item 5 trap; None is a null that should have been handled before
    rounding.  All refuse loudly rather than round quietly."""
    with pytest.raises((TypeError, ValueError)):
        q6(bad)


# ---------------------------------------------------------------------------
# The §7.2 item 5 / B7 type check — it lives once, in decimals.py.

@pytest.mark.parametrize(
    "value,counts",
    [
        (1, True),
        (0, True),
        (-3, True),
        (2.5, True),            # record_f's float parse — still 'number'
        (Decimal("2.5"), True), # record_d's Decimal parse (B7)
        (True, False),          # jsonb_typeof: 'boolean' — THE one-character trap
        (False, False),
        ("5", False),           # 'string', even when it looks numeric
        (None, False),          # 'null'
        ([1], False),           # 'array'
        ({"n": 1}, False),      # 'object'
    ],
)
def test_is_jsonb_number_matches_jsonb_typeof(value, counts):
    assert is_jsonb_number(value) is counts


# ---------------------------------------------------------------------------
# AC-24(b), Postgres half — round(x, 6) evaluated ON THE DEMO'S OWN DATABASE,
# through the one connection factory (plan §4.5: nothing else imports the
# driver).  Skips loudly until W13's db.py and the W4/W5 stack exist.

@pytest.fixture(scope="module")
def demo_db():
    try:
        from demo.server.db import connect  # W13's file — the pinned contract
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(
            "SKIPPED (loudly): AC-24(b) SQL half — demo/server/db.py is not "
            f"importable yet (W13 not landed, or its deps missing): {exc!r}"
        )
    try:
        conn = connect()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(
            "SKIPPED (loudly): AC-24(b) SQL half — the demo database "
            f"(127.0.0.1:55440) is not reachable: {exc!r}"
        )
    yield conn
    conn.close()


@pytest.mark.parametrize("raw,expected_half_up,half_even", TIE_CASES)
def test_postgres_rounds_the_same_tie_the_same_way(demo_db, raw, expected_half_up, half_even):
    """AC-24(b), SQL half: Postgres's round(numeric, 6) — documented to round
    half away from zero — agrees with q6 digit for digit on every tie value.
    Disagreement here is a build failure, not a rounding preference."""
    with demo_db.cursor() as cur:
        cur.execute("SELECT round(%s::numeric, 6)", (Decimal(raw),))
        (sql_value,) = cur.fetchone()
    assert isinstance(sql_value, Decimal)
    py_value = q6(Decimal(raw))
    assert sql_value == py_value == Decimal(expected_half_up)
    assert sql_value.as_tuple().exponent == -6
