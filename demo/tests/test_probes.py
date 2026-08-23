"""AC-17, AC-18 — layer 2, the runtime probes (demo/probes.py; spec §4.5,
plan §4.3, W11).

AC-17, member (a) — out-of-range magnitude, tested from BOTH sides of the
boundary, because a probe that refuses both sides is broken:

  * `$.huge * 1` over noun:EdgeCase is refused — edge-03 carries 1e400 (401
    digits of raw JSON), above the largest double — and the refusal names
    the cause and the row.
  * `$.a * 1` is NOT refused — edge-00 carries 1e300, representable, and
    §5's twelve-decade defect has to stay visible (walkthrough step 11).
  * `$.g * 1` is NOT refused — edge-04 and edge-05 straddle the SHIPPED
    297-digit guard (1.7976931348623157e+296): xpr.f8 already nulls edge-05's
    value, yet the probe stays quiet, which proves its threshold is the
    309-digit DBL_MAX and not the guard it must never be routed through.
  * The generated condition, run over literal values, flips exactly at
    1.7976931348623157e+308 — `>=`, so the boundary value itself refuses
    (B15's deliberate conservatism; never "fixed" into a `>`).

AC-18, member (b) — an ==/!= operand that really is a container:

  * walkthrough step 12's filter `$.where == "alpha"` is refused and NAMES
    row edge-02, whose `where` is {"code": "alpha", "n": 7};
  * walkthrough steps 3 and 4 — `$.status == "ok"`, `$.status != "ok"` over
    all 8,400 noun:Heartbeat rows — are NOT refused.  This is the half that
    proves §4.6's reading A was implemented rather than reading B (a static
    over-approximation would refuse every field reference beside `==`).

Plus the mechanics the plan pins: the probe never routes through xpr.f8 or
xpr.num (the named wrong way — the guard answers NULL, not true), the probe
never looks inside containers (max($.l) with [1e300, 1] inside is step 11's
shown disagreement, not a refusal), and every compiled operand carries its
own B11 prefix so merged bind parameters cannot silently overwrite.

These tests need the seeded database on 127.0.0.1:55440 (`./run-demo up`);
the structural ones at the end do not touch it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo import probes  # noqa: E402
from demo.gate import Refused, gate  # noqa: E402
from demo.probes import (  # noqa: E402
    DBL_MAX_LITERAL,
    RuntimeRefusal,
    build_probes,
    check,
)
from demo.vendor.expr import parse  # noqa: E402

EDGE = "noun:EdgeCase"
HEARTBEAT = "noun:Heartbeat"

# The walkthrough's own expressions, exactly as §10 types them.
STEP_3 = '$.status == "ok"'      # computed column `alive` — accepted
STEP_4 = '$.status != "ok"'      # filter — accepted
STEP_11 = "max($.l)"             # the shown disagreement — NOT refused
STEP_12 = '$.where == "alpha"'   # member (b) fires, names edge-02
STEP_13 = "$.huge * 1"           # member (a) fires, names edge-03


def _gated(src: str):
    """Parse and gate — layer 2 only ever sees expressions layer 1 accepted."""
    ast = parse(src)
    gate(ast)
    return ast


# =================================================================================
# AC-17 — member (a), both sides of the boundary
# =================================================================================
class TestAC17:
    def test_1e400_refuses_naming_cause_and_row(self, db):
        """Walkthrough step 13: edge-03's huge = 1e400 is above the largest
        double, so the pick is refused before its own query runs."""
        with pytest.raises(RuntimeRefusal) as exc:
            check(db, EDGE, [_gated(STEP_13)])
        refusal = exc.value
        assert refusal.member == "a"
        assert refusal.row_key == "edge-03"
        assert DBL_MAX_LITERAL in refusal.cause  # names the magnitude
        assert refusal.probe.member == "a"

    def test_1e300_does_NOT_refuse(self, db):
        """The other side of the boundary: edge-00's a = 1e300 is
        representable.  A probe that refuses both sides is broken — §5's
        defect (the 297-digit guard nulling 1e300) must stay visible."""
        outcomes = check(db, EDGE, [_gated("$.a * 1")])
        fired_a = [o for o in outcomes if o.probe.member == "a"]
        assert len(fired_a) == 1, "the member (a) probe must actually run"
        assert fired_a[0].fired is False

    def test_threshold_is_dbl_max_not_the_shipped_guard(self, db):
        """edge-04 and edge-05 straddle the shipped 297-digit guard.  The
        guard itself nulls edge-05's value (measured here), yet the probe
        does not fire on either — its threshold is the 309-digit DBL_MAX."""
        # The shipped guard genuinely bites between edge-04 and edge-05 …
        cur = db.execute(
            "SELECT key, xpr.f8(data->'g') IS NULL FROM demo.records"
            " WHERE collection = %(c)s AND key IN ('edge-04','edge-05')"
            " ORDER BY key", {"c": EDGE})
        assert cur.fetchall() == [("edge-04", False), ("edge-05", True)]
        # … and the probe, asked over the same rows, stays quiet on both.
        outcomes = check(db, EDGE, [_gated("$.g * 1")])
        assert [(o.probe.member, o.fired) for o in outcomes] == [("a", False)]

    def test_boundary_exact_from_both_sides(self, db):
        """The generated condition itself, at the boundary: one step below
        DBL_MAX does not fire; DBL_MAX exactly, and anything above, does
        (`>=` — B15's deliberate conservatism, not to be 'fixed' into >)."""
        term = probes._term_a("v.j")
        cur = db.execute(
            "SELECT " + term + " FROM (VALUES"
            " ('1.7976931348623156e+308'::jsonb),"
            " ('1.7976931348623157e+308'::jsonb),"
            " ('1.7976931348623158e+308'::jsonb),"
            " ('-1e400'::jsonb),"
            " ('1e300'::jsonb)"
            ") AS v(j)")
        below, at_max, above, negative, e300 = [r[0] for r in cur.fetchall()]
        assert below is False
        assert at_max is True      # >= : exactly DBL_MAX refuses, by ruling
        assert above is True
        assert negative is True    # abs(): the magnitude, either sign
        assert e300 is False

    def test_probe_is_never_routed_through_xpr_f8_or_num(self):
        """The one named wrong way: xpr.f8 / xpr.num return NULL for exactly
        the values that are too big, and NULL >= x is never true.  The probe
        must read the raw jsonb and cast through numeric."""
        (probe,) = build_probes([_gated(STEP_13)])
        assert "xpr.f8" not in probe.sql
        assert "xpr.num" not in probe.sql
        assert "::numeric" in probe.sql
        assert DBL_MAX_LITERAL + "::numeric" in probe.sql
        assert ">=" in probe.sql
        # And never the shipped guard's rendering, in either spelling:
        assert "e+296" not in probe.sql
        assert "179769313486231570000" not in probe.sql  # 297-digit expansion

    def test_step_11_array_operand_is_not_refused(self, db):
        """§4.3's second way to get it wrong: `max($.l)` over
        {"l": [1e300, 1]} must NOT be refused — the operand is an array, not
        a number, and step 11 exists to SHOW the disagreement (Python 1e+300
        beside SQL 1).  A probe 'improved' to look inside containers would
        turn the asserted disagreement of AC-22 into a refusal."""
        outcomes = check(db, EDGE, [_gated(STEP_11)])
        assert [(o.probe.member, o.fired) for o in outcomes] == [("a", False)]


# =================================================================================
# AC-18 — member (b): the container refuses, and steps 3 and 4 do not
# =================================================================================
class TestAC18:
    def test_step_12_container_operand_refuses_and_names_the_row(self, db):
        """edge-02's `where` is {"code": "alpha", "n": 7}: the filter's ==
        operand resolves to an object on that row, and the refusal says so
        by name."""
        with pytest.raises(RuntimeRefusal) as exc:
            check(db, EDGE, [_gated(STEP_12)])
        refusal = exc.value
        assert refusal.member == "b"
        assert refusal.row_key == "edge-02"
        assert "edge-02" in refusal.cause  # the row is NAMED to the person

    def test_steps_3_and_4_are_NOT_refused(self, db):
        """The half that proves §4.6's reading A: `$.status` beside == / !=
        over all 8,400 noun:Heartbeat rows resolves to a string every time,
        so nothing fires.  Under reading B (refuse any field reference beside
        ==) both steps would have been refused here — the single most
        ordinary thing a dashboard does, on data where nothing goes wrong."""
        for src in (STEP_3, STEP_4):
            outcomes = check(db, HEARTBEAT, [_gated(src)])
            fired_b = [o for o in outcomes if o.probe.member == "b"]
            assert len(fired_b) == 1, f"{src}: the (b) probe must actually run"
            assert fired_b[0].fired is False, f"{src} must not be refused"

    def test_container_under_a_DIFFERENT_key_does_not_fire(self, db):
        """The probe reads the operand, not the row: edge-02 and edge-09
        carry containers under other keys, but `$.label` is a string on
        every row, so `$.label == "x"` is not refused."""
        outcomes = check(db, EDGE, [_gated('$.label == "x"')])
        fired_b = [o for o in outcomes if o.probe.member == "b"]
        assert len(fired_b) == 1
        assert fired_b[0].fired is False

    def test_empty_containers_still_refuse(self, db):
        """Container-ness is a type, not a truthiness: edge-09's obj = {} and
        arr = [] are containers, so ==/!= over them refuses — and names
        edge-09."""
        for src in ('$.obj != "x"', '$.arr == "x"'):
            with pytest.raises(RuntimeRefusal) as exc:
                check(db, EDGE, [_gated(src)])
            assert exc.value.member == "b", src
            assert exc.value.row_key == "edge-09", src


# =================================================================================
# The mechanics the plan pins — no database needed below this line
# =================================================================================
class TestMechanics:
    def test_probe_sql_is_the_plan_shape(self):
        """Plan §4.3's statement, shape for shape: EXISTS over demo.records
        AS r, the collection as a bind parameter, terms OR-ed."""
        (probe,) = build_probes([_gated(STEP_13)])
        assert probe.sql.startswith("SELECT EXISTS (")
        assert "SELECT 1 FROM demo.records AS r" in probe.sql
        assert "WHERE r.collection = %(collection)s" in probe.sql
        assert "jsonb_typeof(" in probe.sql
        # Two operands ($.huge and the literal 1), so exactly one OR:
        assert probe.sql.count("\n        OR ") == 1
        assert len(probe.operands) == 2

    def test_member_a_precedes_member_b(self):
        """When a pick carries both kinds of operand, the (a) probe is built
        and answered first — the refusal precedence check() relies on."""
        built = build_probes([_gated("$.n * 1 == $.m")])
        assert [p.member for p in built] == ["a", "b"]

    def test_b11_namespacing_keeps_three_literals_distinct(self):
        """The probe compiles operand sub-ASTs separately and ORs them into
        ONE statement — B11's exact hazard.  Two different literals must
        survive the merge under distinct prefixed keys, and every
        placeholder must carry its own fragment's prefix."""
        import re

        (probe,) = build_probes([_gated("$.d * 2 + $.z * 3")])
        values = list(probe.params.values())
        assert 2.0 in values and 3.0 in values
        # No unprefixed p0 survives, and nothing but prbA*/collection binds:
        placeholders = set(re.findall(r"%\((\w+)\)s", probe.sql))
        assert "p0" not in placeholders
        assert all(n == "collection" or re.fullmatch(r"prbA\d+_p\d+", n)
                   for n in placeholders)
        # Each operand fragment's placeholders all carry that fragment's own
        # index — the property that makes overwriting impossible:
        for i, frag_sql in enumerate(probe.operands):
            for name in re.findall(r"%\((\w+)\)s", frag_sql):
                assert name.startswith(f"prbA{i}_"), (i, name, frag_sql)

    def test_numeric_roots_are_probed(self, db):
        """Ops 6/7/8 feed a whole expression to the builder's numeric_read();
        handed to the probes as a numeric root, `$.huge` alone refuses."""
        with pytest.raises(RuntimeRefusal) as exc:
            check(db, EDGE, [], numeric_roots=[_gated("$.huge")])
        assert exc.value.member == "a"
        assert exc.value.row_key == "edge-03"

    def test_no_operands_builds_no_probe_and_touches_no_database(self):
        """A pick with nothing to ask sends nothing: conn=None would explode
        on any execute, and does not."""
        assert build_probes([_gated("$.status")]) == []
        assert check(None, HEARTBEAT, [_gated("$.status")]) == []

    def test_runtime_refusal_is_named_catchable_and_not_layer_1(self):
        """The 'raises a named error' half of the loud-refusal ruling: a
        catchable exception carrying member, cause, row and probe — and a
        different shape from layer 1's Refused, because the screen renders
        the two differently (spec §4.5: layer 1 empties both panes; layer 2
        is the labelled fallback)."""
        assert issubclass(RuntimeRefusal, Exception)
        assert not issubclass(RuntimeRefusal, Refused)
        assert not issubclass(Refused, RuntimeRefusal)
