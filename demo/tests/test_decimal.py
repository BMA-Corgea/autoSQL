"""AC-24(b) — both sides round a tie the same way (spec §7.2 item 2).

WHAT LIVES HERE, AND WHOSE IT IS
  * W9 (this file's first landing): AC-24(b) — the tie test. The Python half
    runs always; the Postgres half runs against the demo's own database
    through demo/server/db.py (W13's file, the only connection factory) and
    SKIPS LOUDLY until that stack exists.  If the two sides ever disagree on
    a tie, that is a build failure, not a rounding preference (AC-24(b)).
  * W12 adds AC-24(d) — the short-window cases against
    fixtures/expected_step8.json.  Not here yet; do not fold it in elsewhere.
  * The B7 / plan §8.2 M9 decimal-AGGREGATE cases (bottom of the file,
    added 2026-08-22): fractional values through ``evaluate.aggregate``,
    the same values through Postgres, and the plan-promised ``noun:Sample``
    aggregate over a 4-decimal ``field_n`` end to end.  Until then every
    aggregated value in the whole suite was a small integer, and a
    float-contaminated aggregate accumulation passed the entire suite.

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

import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, getcontext, localcontext
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.pyrunner import evaluate  # noqa: E402
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
    # And the ambient context really is left untouched afterwards.  Twice:
    #
    # (1) leaning on this file's test order — the tie cases above already
    #     ran q6 many times OUTSIDE any localcontext, so a q6 that switched
    #     the thread's context to its own half-up mode would be caught here.
    #     (This line used to read `... != ROUND_HALF_UP or True`, a
    #     tautology that could not fail; the `or True` is gone.)
    assert getcontext().rounding != ROUND_HALF_UP, (
        "the ambient decimal context is now ROUND_HALF_UP — q6 (or something "
        "it calls) mutated the thread's context instead of using its own"
    )
    # (2) directly, with no dependence on test order: one bare q6 call,
    #     outside any protective localcontext, must leave the ambient
    #     rounding mode and precision exactly as it found them.
    before = (getcontext().rounding, getcontext().prec)
    assert q6(Decimal("0.0000005")) == Decimal("0.000001")
    after = (getcontext().rounding, getcontext().prec)
    assert after == before, (
        f"a single q6 call changed the ambient decimal context: "
        f"{before} -> {after}"
    )


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


# ---------------------------------------------------------------------------
# B7 / plan §8.2 M9 — the decimal-AGGREGATE cases.
#
# Until 2026-08-22 every aggregated value in the whole suite was a small
# integer, so an aggregate accumulation contaminated by float — M9's axis,
# e.g. `total += Decimal(float(v))` in evaluate.aggregate's sum/avg loop —
# passed all 568 tests while returning a subtly wrong number: the project's
# own named failure mode.  Plan §8.2's M9 row promised "a noun:Sample
# aggregate over a 4-decimal field_n is added to the suite (B7)" and it
# never was.  This section is that coverage, in three layers:
#
#   1. evaluate.aggregate directly, on values where float and exact decimal
#      arithmetic diverge at the 6th decimal place or beyond — plus a
#      test-of-the-test proving each case DOES diverge under contamination;
#   2. the same values through Postgres's numeric aggregates, digit for
#      digit against the Python answers (the cross-engine half);
#   3. the plan-promised noun:Sample aggregate over 4-decimal field_1,
#      end to end through POST /api/pick, each pane compared digit for
#      digit against a THIRD computation made here from the stored JSON
#      text (Decimal(text), never Decimal(float)).
#
# Each case's values are written as ONE JSON array literal and parsed the
# way rows.py's record_d parse delivers numbers to the aggregate (B7):
# json.loads(..., parse_float=Decimal) — ints arrive as exact ints,
# fractions as exact Decimals carrying the JSON text's digits.
#
#   fn     values (JSON)                          exact answer   float-routed
AGG_HOSTILE_CASES = [
    ("sum", "[1000000000000.1]",                   "1000000000000.100000"),
    # float: 1000000000000.099976 — wrong from the 6th place on
    ("sum", "[1000000000000.1, -1000000000000.0]", "0.100000"),
    # cancellation: float leaves 0.099976 — wrong from the FIRST place on
    ("sum", "[1, 0.0000005]",                      "1.000001"),
    # a tie born inside the accumulation (int + Decimal mixed, B7's types);
    # float arrives just under the tie and rounds DOWN: 1.000000
    ("avg", "[1000000000000.1, 3000000000000.5]",  "2000000000000.300000"),
    # float: 2000000000000.299988
    ("min", "[-999.9998, 2.5]",                    "-999.9998"),
    # min/max take no round (§7.2), so the DIGITS carry the check: a float
    # detour prints -999.99980000000005020410753786563873291015625
    ("max", "[999.1234, -2.5]",                    "999.1234"),
]

_AGG_IDS = ["sum-large", "sum-cancel", "sum-tie", "avg-large", "min-digits", "max-digits"]


def _record_d_values(json_text: str) -> list:
    """The values exactly as rows.py's exact parse would deliver them."""
    return json.loads(json_text, parse_float=Decimal)


@pytest.mark.parametrize("fn,json_text,expected", AGG_HOSTILE_CASES, ids=_AGG_IDS)
def test_aggregate_stays_exact_on_float_hostile_values(fn, json_text, expected):
    """The aggregate path itself, on values float64 cannot carry: the answer
    is the exact decimal one, digit for digit, scale included."""
    values = _record_d_values(json_text)
    got = evaluate.aggregate(fn, values, len(values))
    assert isinstance(got, Decimal), f"aggregate returned {type(got).__name__}"
    assert got == Decimal(expected)
    assert str(got) == expected, (
        f"{fn}({json_text}) = {got}, want {expected} digit for digit"
    )
    if fn in ("sum", "avg"):
        assert got.as_tuple().exponent == -6  # q6's quantum, not just the value


@pytest.mark.parametrize("fn,json_text,expected", AGG_HOSTILE_CASES, ids=_AGG_IDS)
def test_the_hostile_values_actually_expose_float_contamination(fn, json_text, expected):
    """The test of the test: rerun each case with M9's contamination —
    every value routed through Decimal(float(v)) — inside evaluate's own
    arithmetic context, and prove the answer COMES OUT DIFFERENT.  A case
    that cannot tell the two routes apart carries no weight here."""
    values = _record_d_values(json_text)
    contaminated = [Decimal(float(v)) for v in values]
    if fn in ("sum", "avg"):
        with localcontext(evaluate._ARITH):
            total = Decimal(0)
            for v in contaminated:
                total += v
            if fn == "avg":
                total /= Decimal(len(contaminated))
            wrong = q6(total)
    else:
        wrong = min(contaminated) if fn == "min" else max(contaminated)
    assert str(wrong) != expected, (
        f"{fn}({json_text}): the float route also gives {expected} — this "
        f"case cannot catch a contaminated aggregate and must be replaced"
    )


@pytest.mark.parametrize("fn,json_text,expected", AGG_HOSTILE_CASES, ids=_AGG_IDS)
def test_postgres_agrees_digit_for_digit_on_the_hostile_aggregates(
        demo_db, fn, json_text, expected):
    """The cross-engine half: Postgres's numeric aggregate of the same
    values equals evaluate.aggregate's answer digit for digit — sum/avg
    through round(…, 6) exactly as the builder emits them, min/max bare."""
    values = _record_d_values(json_text)
    as_numeric = [Decimal(v) for v in values]  # exact for ints and Decimals
    sql_call = {
        "sum": "round( sum(v), 6)",
        "avg": "round( avg(v), 6)",
        "min": "min(v)",
        "max": "max(v)",
    }[fn]
    with demo_db.cursor() as cur:
        cur.execute(
            f"SELECT {sql_call} FROM unnest(%s::numeric[]) AS t(v)",
            (as_numeric,),
        )
        (sql_value,) = cur.fetchone()
    assert isinstance(sql_value, Decimal)
    py_value = evaluate.aggregate(fn, values, len(values))
    assert sql_value == py_value == Decimal(expected)
    assert str(sql_value) == str(py_value) == expected


# ---------------------------------------------------------------------------
# Layer 3 — the plan-promised end-to-end case: a noun:Sample aggregate over
# the 4-decimal field_1 (§8.2 M9's own words), through POST /api/pick.

@pytest.fixture(scope="module")
def app_client(demo_db):
    """POST /api/pick in-process.  Depends on demo_db so the no-stack case
    is the same loud skip as the rest of this file's SQL half."""
    try:
        from fastapi.testclient import TestClient

        from demo.server import app as server_app
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(
            "SKIPPED (loudly): the M9/B7 end-to-end case — demo/server/app.py "
            f"is not importable ({exc!r})"
        )
    return TestClient(server_app.app)


def _sample_pick(fn: str) -> dict:
    """The screen's pick shape (legality.default_pick's slots), aimed at
    noun:Sample's field_1 — a 4-decimal float on the rows where the seed
    made field_1 numeric (generate.py's t == 1 arm)."""
    return {
        "source": "noun:Sample",
        "computed": [],
        "filter": None,
        "sort": None,
        "cap": None,
        "aggregate": {"fn": fn, "field": "$.field_1"},
        "bucket": "off",
        "window": None,
        "changed": False,
    }


def test_sample_4_decimal_aggregates_end_to_end(demo_db, app_client):
    """Plan §8.2 M9 / B7: sum, avg, min and max of noun:Sample's field_1,
    driven through the API.  Both panes must equal — digit for digit — a
    third computation made HERE from the JSON text the database stores,
    parsed with Decimal(text) and accumulated in exact decimal.  min/max
    carry the parse check (no round hides a float's digit tail); sum/avg
    carry the accumulation and the 6-place half-up round."""
    with demo_db.cursor() as cur:
        cur.execute(
            "SELECT data #>> '{field_1}', jsonb_typeof(data #> '{field_1}') "
            "FROM demo.records WHERE collection = 'noun:Sample'"
        )
        rows = cur.fetchall()
    texts = [t for t, ty in rows if ty == "number"]
    # The case must not hold vacuously: plenty of contributing rows, and
    # genuinely fractional values (the seed writes round(uniform, 4)).
    assert len(rows) == 2000, f"noun:Sample is {len(rows)} rows, expected 2000"
    assert len(texts) >= 100, f"only {len(texts)} numeric field_1 values"
    assert any("." in t for t in texts), "no fractional field_1 value at all"

    vals = [Decimal(t) for t in texts]  # the exact digits the DB stores
    with localcontext(evaluate._ARITH):
        total = Decimal(0)
        for v in vals:
            total += v
        expected = {
            "sum": q6(total),
            "avg": q6(total / Decimal(len(vals))),
            "min": min(vals),
            "max": max(vals),
        }

    # And the values must be able to EXPOSE a float parse: the extremes'
    # float round-trips print different digits (else min/max prove nothing).
    for extreme in (expected["min"], expected["max"]):
        assert str(Decimal(float(extreme))) != str(extreme), (
            f"{extreme} is float-exact; this seed cannot distinguish "
            f"Decimal(text) from Decimal(float) here"
        )

    for fn, want in expected.items():
        body = app_client.post("/api/pick", json=_sample_pick(fn)).json()
        assert body["accepted"] is True, (fn, body.get("refusal"))
        sql_cell = body["panes"]["sql"]["rows"][0]["c"][0]
        py_cell = body["panes"]["python"]["rows"][0]["c"][0]
        assert sql_cell == py_cell == str(want), (
            f"{fn}: SQL pane {sql_cell!r}, Python pane {py_cell!r}, "
            f"independent exact answer {want!r}"
        )
        assert body["verdict"] == "agree", fn
