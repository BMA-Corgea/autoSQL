"""test_legality.py — punch-list 5's matrix, walked in full (W8).

Every combination of the nine operations across the three sources —
3 sources x 2 (op 2) x 2 (op 3) x 2 (op 4) x 2 (op 5) x 6 (op 6)
x 3 (op 7) x 2 (op 8) x 2 (op 9) = 3,456 picks — through
``legality.evaluate`` AND through ``operations.contract``, asserting
for each one:

  * the exact enabled set, against a hand-written oracle below that is
    NOT derived from the implementation (a mirror-image test proves
    nothing);
  * a NON-EMPTY reason on every disable (B5b / DR-2);
  * the reason names the operation that caused it, and never says
    "invalid combination" (B5b);
  * the violations a hostile, screen-skipping pick would be refused
    with (the pick handler calls the same function — §4.5).

Plus the targeted rules: X1's field-list reasons (B4), B5a's bucketed
extension (three greyed, one more than the mock drew), B5c, the rule
inside operation 6, the closed sets, the cap range, and B22 point 3's
contract assertions.

Needs no database and no container (plan §6.3).
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

_DEMO = Path(__file__).resolve().parent.parent
if str(_DEMO) not in sys.path:
    sys.path.insert(0, str(_DEMO))

import legality  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "demo_server_operations", _DEMO / "server" / "operations.py"
)
operations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(operations)


HB, SMP, EDG = "noun:Heartbeat", "noun:Sample", "noun:EdgeCase"
ALL_OPS = frozenset(range(1, 10))

# ── the oracle, written out by hand from B5a's table ────────────────────
# (shape, on_heartbeat) -> the exact enabled set.  Sources other than
# the heartbeat lose 7, 8 and 9 to X1 on every shape.
EXPECTED_ENABLED = {
    ("ROWS", True): ALL_OPS,                       # B4: all nine
    ("ROWS", False): frozenset({1, 2, 3, 4, 5, 6}),
    ("SCALAR", True): frozenset({1, 2, 3, 6, 7}),  # 4,5,8,9 off
    ("SCALAR", False): frozenset({1, 2, 3, 6}),
    ("BUCKET", True): frozenset({1, 2, 3, 5, 6, 7}),  # 4,8,9 off — B5a's three
    ("BUCKET", False): frozenset({1, 2, 3, 5, 6}),    # unreachable; still answered
}

# X1's reason must state the collection's ACTUAL field list (B4).
FIELD_LIST = {
    SMP: "id, status, due_date, priority, field_0 … field_14",
    EDG: "a, arr, d, g, huge, l, label, n, obj, present, s, t, tags, txt, where, z",
}


def pick_for(source, cc, filt, sort, cap, fn, bucket, window, changed):
    return {
        "source": source,
        "computed": [{"name": "alive", "expr": '$.status == "ok"'}] if cc else [],
        "filter": '$.status != "ok"' if filt else None,
        "sort": {"field": "$.status", "dir": "desc"} if sort else None,
        "cap": 10 if cap else None,
        "aggregate": {
            "fn": fn,
            "field": "$.payload.load" if fn in ("sum", "avg", "min", "max") else None,
        },
        "bucket": bucket,
        "window": {"field": "$.payload.load"} if window else None,
        "changed": changed,
    }


def expected_shape(fn, bucket):
    if bucket != "off":
        return "BUCKET"
    if fn != "none":
        return "SCALAR"
    return "ROWS"


def expected_violation_ops(source, sort, cap, fn, bucket, window, changed):
    """Which operations a screen-skipping pick would be refused on —
    derived here from the rules as written, not from the code."""
    shape = expected_shape(fn, bucket)
    on_hb = source == HB
    v = set()
    if not on_hb:
        if bucket != "off":
            v.add(7)
        if window:
            v.add(8)
        if changed:
            v.add(9)
    if shape == "SCALAR":
        if sort:
            v.add(4)
        if cap:
            v.add(5)
        if window:
            v.add(8)
        if changed:
            v.add(9)
    elif shape == "BUCKET":
        if sort:
            v.add(4)
        if window:
            v.add(8)
        if changed:
            v.add(9)
        if fn == "none":
            v.add(6)  # B5c
    return v


def walk():
    """Every combination of the nine operations across the three sources."""
    return itertools.product(
        (HB, SMP, EDG),           # op 1 — the three sources
        (False, True),            # op 2 — a computed column, or none
        (False, True),            # op 3 — a filter, or none
        (False, True),            # op 4 — a sort, or none
        (False, True),            # op 5 — a cap, or none
        legality.AGG_FNS,         # op 6 — none/count/sum/avg/min/max
        legality.BUCKETS,         # op 7 — off/hour/day
        (False, True),            # op 8 — a rolling window, or none
        (False, True),            # op 9 — changed-only, on or off
    )


# ════════════════════════════════════════════════════════════════════════
# THE WALK — every combination, both through evaluate() and contract()
# ════════════════════════════════════════════════════════════════════════

def test_every_combination():
    count = 0
    for source, cc, filt, sort, cap, fn, bucket, window, changed in walk():
        count += 1
        p = pick_for(source, cc, filt, sort, cap, fn, bucket, window, changed)
        at = (f"source={source} cc={cc} filter={filt} sort={sort} cap={cap} "
              f"fn={fn} bucket={bucket} window={window} changed={changed}")

        lg = legality.evaluate(p)
        shape = expected_shape(fn, bucket)
        on_hb = source == HB
        assert lg["shape"] == shape, at

        # the exact enabled set, against the hand-written oracle
        enabled = {n for n, st in lg["ops"].items() if st["enabled"]}
        assert enabled == set(EXPECTED_ENABLED[(shape, on_hb)]), at

        for n, st in lg["ops"].items():
            if st["enabled"]:
                assert st["why"] == "", at
            else:
                # B5b / DR-2: every disable carries a non-empty reason...
                assert isinstance(st["why"], str) and st["why"].strip(), at
                # ...that never waves at "invalid combination"...
                assert "invalid combination" not in st["why"].lower(), at
                # ...and names the operation that caused it.
                if not on_hb and n in (7, 8, 9):
                    # X1 outranks the shape reasons, as the mock orders it
                    assert "operation 1" in st["why"], at
                    assert "$.ts" in st["why"] and "$.sender_id" in st["why"], at
                    assert FIELD_LIST[source] in st["why"], at
                elif shape == "SCALAR":
                    assert "operation 6" in st["why"], at
                elif shape == "BUCKET":
                    assert "operation 7" in st["why"], at

        # the violations a screen-skipping pick is refused with
        want = expected_violation_ops(source, sort, cap, fn, bucket, window, changed)
        got = sorted(v["operation"] for v in lg["violations"])
        assert got == sorted(want), at
        for v in lg["violations"]:
            assert isinstance(v["why"], str) and v["why"].strip(), at

        # the served contract mirrors the same answer — one function (§4.5)
        c = operations.contract(p)
        assert c["shape"] == shape, at
        assert [e["n"] for e in c["operations"]] == list(range(1, 10)), at
        for e in c["operations"]:
            assert e["enabled"] == lg["ops"][e["n"]]["enabled"], at
            assert e["why"] == lg["ops"][e["n"]]["why"], at
            if not e["enabled"]:
                assert e["why"].strip(), at
                for sub in e["controls"]:
                    assert sub["enabled"] is False, at
                    assert sub["why"].strip(), at
        assert c["violations"] == lg["violations"], at

    # the real combination count, asserted so the walk cannot quietly shrink
    assert count == 3 * 2 * 2 * 2 * 2 * 6 * 3 * 2 * 2 == 3456
    print(f"\nwalked {count} combinations "
          f"(3 sources x 2^5 on/off x 6 aggregates x 3 granularities)")


# ════════════════════════════════════════════════════════════════════════
# The named rules, one by one
# ════════════════════════════════════════════════════════════════════════

def test_rows_on_heartbeat_all_nine_enabled():
    """B4: on noun:Heartbeat, the default view disables nothing."""
    lg = legality.evaluate(legality.default_pick())
    assert lg["shape"] == "ROWS"
    assert all(st["enabled"] for st in lg["ops"].values())
    assert lg["violations"] == []


def test_heartbeat_to_edgecase_disables_exactly_three():
    """The mock's measured behaviour: the source flip takes the
    disabled count 0 -> 3 (B4, design part 11)."""
    p = legality.default_pick()
    assert sum(not st["enabled"] for st in legality.evaluate(p)["ops"].values()) == 0
    p["source"] = EDG
    off = {n for n, st in legality.evaluate(p)["ops"].items() if not st["enabled"]}
    assert off == {7, 8, 9}


def test_bucketed_view_disables_three_not_two():
    """B5a's deliberate excess over the approved drawing: the mock's V2
    greys 4 and 8 (X2's pair); the build greys 9 as well, because a
    window's PARTITION BY reads ungrouped data in a grouped query
    (42803)."""
    p = legality.default_pick()
    p["bucket"] = "day"
    p["aggregate"] = {"fn": "count", "field": None}
    lg = legality.evaluate(p)
    assert lg["shape"] == "BUCKET"
    off = {n for n, st in lg["ops"].items() if not st["enabled"]}
    assert {4, 8} < off          # the two the mock drew...
    assert off == {4, 8, 9}      # ...plus the one B5a adds
    assert "42803" in lg["ops"][8]["why"]
    assert "42803" in lg["ops"][9]["why"]
    assert lg["violations"] == []


def test_scalar_disables_four():
    p = legality.default_pick()
    p["aggregate"] = {"fn": "sum", "field": "$.payload.load"}
    lg = legality.evaluate(p)
    assert lg["shape"] == "SCALAR"
    off = {n for n, st in lg["ops"].items() if not st["enabled"]}
    assert off == {4, 5, 8, 9}
    # B5b's canonical wording for X2's first half
    assert "one statement cannot return both a total and a per-row value" \
        in lg["ops"][8]["why"]
    assert lg["violations"] == []


def test_x1_reason_states_the_actual_field_list():
    for source in (SMP, EDG):
        p = legality.default_pick()
        p["source"] = source
        lg = legality.evaluate(p)
        for n in (7, 8, 9):
            why = lg["ops"][n]["why"]
            assert FIELD_LIST[source] in why
            assert source in why


def test_x1_outranks_x2_off_heartbeat():
    """The mock's locksFor applies X1 first; a scalar pick on the
    sample keeps the field-list reason on op 8, not the aggregate one."""
    p = legality.default_pick()
    p["source"] = SMP
    p["aggregate"] = {"fn": "avg", "field": "$.priority"}
    lg = legality.evaluate(p)
    assert "$.sender_id" in lg["ops"][8]["why"]
    assert "operation 6" not in lg["ops"][8]["why"]


def test_count_disables_the_field_picker():
    """The rule inside operation 6, drawn in the mock (B5a)."""
    p = legality.default_pick()
    p["aggregate"] = {"fn": "count", "field": None}
    lg = legality.evaluate(p)
    assert lg["aggregate_field"]["enabled"] is False
    assert lg["aggregate_field"]["why"] == "count counts rows and takes no field"
    # with a real function the picker is live
    p["aggregate"] = {"fn": "min", "field": "$.payload.load"}
    assert legality.evaluate(p)["aggregate_field"]["enabled"] is True
    # with none there is nothing to read either
    p["aggregate"] = {"fn": "none", "field": None}
    lg = legality.evaluate(p)
    assert lg["aggregate_field"]["enabled"] is False
    assert lg["aggregate_field"]["why"].strip()


def test_b5c_bucket_with_no_aggregate_is_refused():
    """A pick that skips the screen and arrives bucketed over op 6 =
    none is refused, never silently defaulted (B5c)."""
    p = legality.default_pick()
    p["bucket"] = "hour"
    lg = legality.evaluate(p)
    v = [v for v in lg["violations"] if v["operation"] == 6]
    assert len(v) == 1
    assert "count or total" in v[0]["why"]


def test_values_on_disabled_operations_are_refused_with_the_same_words():
    """§4.5: one function — the refusal quotes the reason the screen
    shows beside the greyed control."""
    p = legality.default_pick()
    p["source"] = EDG
    p["changed"] = True
    lg = legality.evaluate(p)
    v = [v for v in lg["violations"] if v["operation"] == 9]
    assert len(v) == 1
    assert v[0]["why"] == lg["ops"][9]["why"]

    p = legality.default_pick()
    p["aggregate"] = {"fn": "sum", "field": "$.payload.load"}
    p["sort"] = {"field": "$.status", "dir": "asc"}
    p["cap"] = 5
    lg = legality.evaluate(p)
    assert sorted(v["operation"] for v in lg["violations"]) == [4, 5]
    for v in lg["violations"]:
        assert v["why"] == lg["ops"][v["operation"]]["why"]


def test_aggregate_field_requiredness():
    """B5a: a field is required unless the function is count — and
    count (or none) must not carry one."""
    p = legality.default_pick()
    p["aggregate"] = {"fn": "sum", "field": None}
    assert [v["operation"] for v in legality.evaluate(p)["violations"]] == [6]

    p["aggregate"] = {"fn": "count", "field": "$.payload.load"}
    v = legality.evaluate(p)["violations"]
    assert [x["operation"] for x in v] == [6]
    assert v[0]["why"] == "count counts rows and takes no field"

    p["aggregate"] = {"fn": "none", "field": "$.payload.load"}
    assert [x["operation"] for x in legality.evaluate(p)["violations"]] == [6]

    p["aggregate"] = {"fn": "count", "field": None}
    assert legality.evaluate(p)["violations"] == []


def test_cap_range():
    """§4.4 row 5: a positive integer no greater than 20,000."""
    for bad in (0, -1, 20001, "10", 3.5, True):
        p = legality.default_pick()
        p["cap"] = bad
        assert [v["operation"] for v in legality.evaluate(p)["violations"]] == [5], bad
    for good in (1, 8, 20000):
        p = legality.default_pick()
        p["cap"] = good
        assert legality.evaluate(p)["violations"] == [], good


def test_closed_sets_fail_closed():
    p = legality.default_pick()
    p["source"] = "noun:Secret"
    assert [v["operation"] for v in legality.evaluate(p)["violations"]] == [1]

    p = legality.default_pick()
    p["aggregate"] = {"fn": "median", "field": "$.payload.load"}
    assert 6 in [v["operation"] for v in legality.evaluate(p)["violations"]]

    p = legality.default_pick()
    p["bucket"] = "week"
    ops6 = [v["operation"] for v in legality.evaluate(p)["violations"]]
    assert 7 in ops6  # week is not a granularity

    p = legality.default_pick()
    p["sort"] = {"field": "$.status", "dir": "sideways"}
    assert [v["operation"] for v in legality.evaluate(p)["violations"]] == [4]


# ════════════════════════════════════════════════════════════════════════
# B22 point 3 — the served contract's own shape
# ════════════════════════════════════════════════════════════════════════

def test_contract_default_state():
    c = operations.contract()
    assert c["source"] == HB and c["shape"] == "ROWS"
    assert len(c["operations"]) == 9                      # AC-25: nine present
    assert [e["n"] for e in c["operations"]] == list(range(1, 10))
    assert all(e["enabled"] for e in c["operations"])
    assert c["violations"] == []
    labels = [e["label"] for e in c["operations"]]
    assert labels == [
        "Choose a source", "Computed columns", "One filter", "Sort field",
        "Row cap", "Aggregate", "Time buckets", "Rolling window",
        "Show only rows that changed",
    ]


def _entry(c, n):
    return next(e for e in c["operations"] if e["n"] == n)


def test_contract_op7_options_exactly_off_hour_day():
    c = operations.contract()
    op7 = _entry(c, 7)
    (ctl,) = op7["controls"]
    assert [o["value"] for o in ctl["options"]] == ["off", "hour", "day"]
    assert op7["ctl_fixed"]  # the dashed note is present and non-empty
    # B5c's visible transition rides on the contract for the screen
    assert op7["transition"]["set"] == {"operation": 6, "fn": "count"}
    assert op7["transition"]["why"].strip()


def test_contract_op8_one_field_control_and_nothing_else():
    """R14: one field control — no width, no direction, no aggregate."""
    op8 = _entry(operations.contract(), 8)
    assert len(op8["controls"]) == 1
    assert op8["controls"][0]["name"] == "field"
    assert op8["controls"][0]["options_from"] == "numeric_fields"
    assert op8["ctl_fixed"]
    names = {c["name"] for c in op8["controls"]}
    assert names.isdisjoint({"width", "direction", "aggregate", "fn"})


def test_contract_op9_toggle_and_no_value_picker():
    """R13 / AC-40(e): a toggle, and nothing to pick."""
    op9 = _entry(operations.contract(), 9)
    assert op9["kind"] == "toggle"
    assert len(op9["controls"]) == 1
    assert op9["controls"][0]["kind"] == "toggle"
    assert op9["ctl_fixed"]


def test_contract_op6_options_lose_none_when_bucketed():
    """B5a: on BUCKET, operation 6 may not be none — the option is not
    offered."""
    c = operations.contract()
    fn_ctl = _entry(c, 6)["controls"][0]
    assert [o["value"] for o in fn_ctl["options"]] == \
        ["none", "count", "sum", "avg", "min", "max"]

    p = legality.default_pick()
    p["bucket"] = "day"
    p["aggregate"] = {"fn": "count", "field": None}
    fn_ctl = _entry(operations.contract(p), 6)["controls"][0]
    assert [o["value"] for o in fn_ctl["options"]] == \
        ["count", "sum", "avg", "min", "max"]


def test_contract_op6_field_picker_states_its_reason():
    p = legality.default_pick()
    p["aggregate"] = {"fn": "count", "field": None}
    field_ctl = _entry(operations.contract(p), 6)["controls"][1]
    assert field_ctl["enabled"] is False
    assert field_ctl["why"] == "count counts rows and takes no field"


def test_contract_op5_range():
    op5 = _entry(operations.contract(), 5)
    assert op5["controls"][0]["range"] == {"min": 1, "max": 20000}


def test_contract_op2_note_when_not_emitted():
    """B2: on SCALAR/BUCKET the computed columns are defined, not
    emitted — the contract says so; on ROWS it says nothing."""
    assert _entry(operations.contract(), 2)["note"] is None
    p = legality.default_pick()
    p["aggregate"] = {"fn": "avg", "field": "$.payload.load"}
    assert "defined, not emitted" in _entry(operations.contract(p), 2)["note"]


def test_contract_sources_are_the_closed_set_of_three():
    src_ctl = _entry(operations.contract(), 1)["controls"][0]
    assert [o["value"] for o in src_ctl["options"]] == [HB, SMP, EDG]
