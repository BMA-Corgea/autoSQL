"""W12's tests — the Python pane, alone, against hand-computed values.

What is owed here (plan §6.2, item W12):

  AC-23(a)(b) — the pane computes from the SOURCE rows in the demo
      database: a direct mutation in Postgres moves its answer (a), and a
      perturbed SQL side cannot move it (b).  (b)'s full end-to-end form —
      a test hook perturbing the compiled expression with both panes wired
      through the API — needs W10's builder and W13's server and lands in
      test_walkthrough.py (plan §7); what W12 can prove, and proves here,
      is the pane's own half: there is NO input channel through which a
      SQL answer could reach it, structurally and functionally.

  AC-24(d) — §7.1's window rule at the short windows, Python pane ALONE,
      against hand-computed literals: divisor 1 at a sender's first beat,
      2 at its second, 3 from the third on — each expected value written
      into this file as a literal with its derivation, never generated
      from the code under test.

  AC-40(a)(b)(d) — operation 9 on the Python pane alone: the kept-row
      band (a), the three two-row unit cases (b), the fifty first beats (d).

House rule (plan §8.1 row 3): there is no tolerance anywhere in this file —
every numeric assertion is exact equality on Decimals, ints or strings.

Read-only DB access uses conftest's session fixture; AC-23(a)'s one
sanctioned write happens on this file's own connection, inside a
transaction that is rolled back (B10's shape — nothing is committed, and
the end-of-session checksum guard would catch it if it were).
"""

from __future__ import annotations

import ast as pyast
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.pyrunner import evaluate as ev  # noqa: E402
from demo.pyrunner.rows import read_rows, source_row  # noqa: E402
from demo.pyrunner.shape import answer, python_pane  # noqa: E402

HEARTBEAT = "noun:Heartbeat"


def hb_pick(**overrides) -> dict:
    """A minimal legal heartbeat pick; overrides set individual operations."""
    pick = {
        "source": HEARTBEAT,
        "computed": [],
        "filter": None,
        "sort": None,
        "cap": None,
        "aggregate": {"fn": "none", "field": None},
        "bucket": "off",
        "window": None,
        "changed": False,
    }
    pick.update(overrides)
    return pick


def hb_row(key: str, sender: str, ts: str, status: str = "ok", payload=None):
    """One synthetic heartbeat row, built from JSON TEXT through the same
    double parse production rows take (B7) — never from a Python dict."""
    raw = json.dumps(
        {
            "sender_id": sender,
            "ts": ts,
            "status": status,
            "payload": payload if payload is not None else {"load": 5, "note": "alpha"},
        }
    )
    return source_row(HEARTBEAT, key, raw)


# ─────────────────────────────────────────────────────────────────────────
# B7 — the double parse (rows.py's whole reason to exist)
# ─────────────────────────────────────────────────────────────────────────

def test_b7_double_parse_keeps_the_decimal_text():
    # 0.1 has no exact binary form; the float parse carries the binary
    # value, the Decimal parse carries the decimal text (B7).
    row = source_row(HEARTBEAT, "x-0000", '{"v": 0.1000, "n": 7}')
    assert isinstance(row.record_f["v"], float)
    assert isinstance(row.record_d["v"], Decimal)
    assert row.record_d["v"] == Decimal("0.1000")
    # ints stay int in BOTH parses — parse_float touches only floats
    assert row.record_f["n"] == 7 and isinstance(row.record_f["n"], int)
    assert row.record_d["n"] == 7 and isinstance(row.record_d["n"], int)
    # and the float world really is lossy where the Decimal world is not:
    assert Decimal(row.record_f["v"]) != Decimal("0.1")


def test_b7_a_number_no_float_can_hold_survives_the_exact_parse():
    # edge-03's shape: jsonb renders 1e400 as digits; json's float parse
    # overflows to inf (which AC-17 wants shown as literal text), while the
    # Decimal parse holds the value exactly.
    row = source_row("noun:EdgeCase", "edge-xx", '{"huge": 1e400}')
    assert row.record_f["huge"] == float("inf")
    assert row.record_d["huge"] == Decimal("1E+400")


# ─────────────────────────────────────────────────────────────────────────
# AC-24(d) — the window rule at the short windows, Python pane alone
# ─────────────────────────────────────────────────────────────────────────

def test_ac24d_seeded_sender_hb18_against_hand_computed_values(db):
    """The named sender is hb-18, whose first three beats carry loads
    27, 88, 88.

    DERIVATION of the fixture (independent of the code under test, two
    ways):
      1. B27's pinned stream, re-derived by hand from the plan's text:
         seed = int.from_bytes(sha256(b"T-2:hb-18").digest()[:8], "big");
         beat 0 draws status ("warn"), load 27, note "papa"; beat 1's
         change coin fires and redraws ("ok", 88, "mike"); beat 2 carries
         forward unchanged.
      2. Read straight off the seeded database (no pane code):
           SELECT data #>> '{payload,load}' FROM demo.records
            WHERE collection = 'noun:Heartbeat'
              AND data ->> 'sender_id' = 'hb-18'
            ORDER BY (data ->> 'ts'), key LIMIT 3;
         → 27, 88, 88.  (AC-10 pins the seed byte-for-byte, so this
         fixture cannot drift silently.)

    DERIVATION of the expected averages (§7.1's window rule + §7.2's
    half-up-to-6), by hand:
      row 1: frame holds 1 row  → 27 ÷ 1               = 27        → "27.000000"
      row 2: frame holds 2 rows → (27 + 88) ÷ 2 = 115/2 = 57.5      → "57.500000"
      row 3: frame holds 3 rows → (27+88+88) ÷ 3 = 203/3 = 67.6666…
             seventh decimal digit is 6 ≥ 5, so half-up → "67.666667"

    A pane that divides by 3 always returns 9.000000 and 38.333333 at
    rows 1–2 (mutant M1); one that emits None until three rows have
    accumulated returns None twice (M2).  Both fail here, by name.
    """
    pick = hb_pick(
        filter='$.sender_id == "hb-18"',
        window={"field": "$.payload.load"},
    )
    result = python_pane(db, pick)
    assert result["shape"] == "ROWS"
    assert result["row_count"] == 168  # one sender's beats survive the filter
    first_three = result["rows"][:3]  # no sort picked → §7.4(2): key ASC
    assert [r["key"] for r in first_three] == [
        "hb-18-0000", "hb-18-0001", "hb-18-0002",
    ]
    # Exact Decimals, asserted as displayed text too — §7.2 item 3: both
    # panes display and compare the rounded value.
    assert first_three[0]["rolling_avg"] == Decimal("27.000000")
    assert first_three[1]["rolling_avg"] == Decimal("57.500000")
    assert first_three[2]["rolling_avg"] == Decimal("67.666667")
    assert [str(r["rolling_avg"]) for r in first_three] == [
        "27.000000", "57.500000", "67.666667",
    ]


def test_ac24d_divisors_one_two_three_synthetic():
    """The same three cases with loads 10, 11, 40, chosen so every wrong
    divisor shows: hand-computed —
      row 1: 10 ÷ 1              = 10       → "10.000000"   (÷3 would say 3.333333)
      row 2: (10+11) ÷ 2 = 21/2  = 10.5     → "10.500000"   (÷3 would say 7.000000)
      row 3: (10+11+40) ÷ 3      = 61/3 = 20.3333… → "20.333333"
    """
    rows = [
        hb_row("hb-90-0000", "hb-90", "2026-08-14T00:00:00Z", payload={"load": 10, "note": "a"}),
        hb_row("hb-90-0001", "hb-90", "2026-08-14T01:00:00Z", payload={"load": 11, "note": "a"}),
        hb_row("hb-90-0002", "hb-90", "2026-08-14T02:00:00Z", payload={"load": 40, "note": "a"}),
    ]
    result = answer(rows, hb_pick(window={"field": "$.payload.load"}))
    got = [r["rolling_avg"] for r in result["rows"]]
    assert got == [Decimal("10.000000"), Decimal("10.500000"), Decimal("20.333333")]


def test_window_rule_divisor_counts_only_non_null_values():
    """§7.1's window rule, verbatim: the divisor is the number of rows
    actually in the frame whose value is non-null — and an all-null frame
    is null, never zero.  Hand-computed —
      beat 0: load is a string → not a number → frame values [null]  → null
      beat 1: load 6           → frame [null, 6]      → 6 ÷ 1        → "6.000000"
      beat 2: load absent      → frame [null, 6, null] → 6 ÷ 1       → "6.000000"
      beat 3: load 9           → frame [6, null, 9]   → (6+9) ÷ 2 = 7.5 → "7.500000"
    """
    rows = [
        hb_row("hb-91-0000", "hb-91", "2026-08-14T00:00:00Z", payload={"load": "warming", "note": "a"}),
        hb_row("hb-91-0001", "hb-91", "2026-08-14T01:00:00Z", payload={"load": 6, "note": "a"}),
        hb_row("hb-91-0002", "hb-91", "2026-08-14T02:00:00Z", payload={"note": "a"}),
        hb_row("hb-91-0003", "hb-91", "2026-08-14T03:00:00Z", payload={"load": 9, "note": "a"}),
    ]
    result = answer(rows, hb_pick(window={"field": "$.payload.load"}))
    got = [r["rolling_avg"] for r in result["rows"]]
    assert got == [None, Decimal("6.000000"), Decimal("6.000000"), Decimal("7.500000")]


# ─────────────────────────────────────────────────────────────────────────
# AC-40(b) — the three two-row cases, Python pane alone
# ─────────────────────────────────────────────────────────────────────────

def _kept_keys(rows) -> list:
    result = answer(rows, hb_pick(changed=True))
    return [r["key"] for r in result["rows"]]


def test_ac40b_ts_only_difference_is_not_kept():
    # Two records identical except ts: the ordering key is excluded from
    # the compared value by construction (§7.1's comparison rule), so the
    # second row is NOT kept.  The first is — it has no predecessor.
    rows = [
        hb_row("hb-92-0000", "hb-92", "2026-08-14T00:00:00Z"),
        hb_row("hb-92-0001", "hb-92", "2026-08-14T01:00:00Z"),
    ]
    assert _kept_keys(rows) == ["hb-92-0000"]


def test_ac40b_payload_load_difference_is_kept():
    rows = [
        hb_row("hb-93-0000", "hb-93", "2026-08-14T00:00:00Z", payload={"load": 5, "note": "alpha"}),
        hb_row("hb-93-0001", "hb-93", "2026-08-14T01:00:00Z", payload={"load": 6, "note": "alpha"}),
    ]
    assert _kept_keys(rows) == ["hb-93-0000", "hb-93-0001"]


def test_ac40b_status_difference_is_kept():
    rows = [
        hb_row("hb-94-0000", "hb-94", "2026-08-14T00:00:00Z", status="ok"),
        hb_row("hb-94-0001", "hb-94", "2026-08-14T01:00:00Z", status="warn"),
    ]
    assert _kept_keys(rows) == ["hb-94-0000", "hb-94-0001"]


# ─────────────────────────────────────────────────────────────────────────
# AC-40(a) and (d) — operation 9 over the seeded data, Python pane alone
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def changed_result(db):
    """Operation 9 on noun:Heartbeat with no other pick, computed once."""
    return python_pane(db, hb_pick(changed=True))


def test_ac40a_kept_row_count_lands_in_the_band(db, changed_result):
    # The band §8.3's repeat rate implies and B27 re-derives: 50 first
    # beats + ≈ 0.10 × 8,350 change events ⇒ expected ≈ 885, asserted at
    # 700–1,100 of 8,400.  A comparison that includes ts keeps all 8,400 —
    # an eight-fold miss, not a near one (plan §8.1 row 4).
    plain = python_pane(db, hb_pick())
    assert plain["row_count"] == 8400  # the input really is the full collection
    assert 700 <= changed_result["row_count"] <= 1100


def test_ac40d_every_senders_first_beat_is_kept(changed_result):
    # IS DISTINCT FROM is what keeps these; <> would lose all fifty (B3
    # detail 2, mutant M5).  Exactly 50 kept rows are first beats, and
    # they are every sender's.
    kept_keys = {r["key"] for r in changed_result["rows"]}
    first_beats = {f"hb-{s:02d}-0000" for s in range(1, 51)}
    assert first_beats <= kept_keys
    assert sum(1 for k in kept_keys if k.endswith("-0000")) == 50


# ─────────────────────────────────────────────────────────────────────────
# AC-23(a) — a direct mutation in Postgres moves the Python pane
# ─────────────────────────────────────────────────────────────────────────

def test_ac23a_mutating_a_row_in_postgres_moves_the_python_pane():
    """The pane reads the database, so a row changed IN the database moves
    its answer — and by exactly the amount of the change, because the
    arithmetic is exact (§7.2).

    The write happens on this test's own connection inside a transaction
    that is ROLLED BACK (B10's shape: nothing committed, nothing to
    forget to clean up); the pane re-reads through that same connection,
    so it sees the uncommitted mutation and, after the rollback, the
    original rows again.  The API-level form of this test — both panes,
    committed UPDATE, restore in a finally — lands with W13/W16.
    """
    from demo.seed.load import demo_connection

    conn = demo_connection()
    try:
        sum_pick = hb_pick(aggregate={"fn": "sum", "field": "$.payload.load"})
        changed_pick = hb_pick(changed=True)

        before_sum = python_pane(conn, sum_pick)["agg"]
        before_kept = python_pane(conn, changed_pick)["row_count"]
        # loads are integers 0–100, so the exact-decimal sum of 8,400 of
        # them is a whole number — the checkable-on-the-spot property §7.2
        # exists for.  A float path would already have broken this.
        assert isinstance(before_sum, Decimal)
        assert before_sum == before_sum.to_integral_value()

        # The one sanctioned mutation (AC-23(a)): hb-01-0000's load, +1000.
        conn.execute(
            "UPDATE demo.records"
            "   SET data = jsonb_set(data, '{payload,load}',"
            "         to_jsonb(((data #>> '{payload,load}')::int + 1000)))"
            " WHERE collection = %(c)s AND key = 'hb-01-0000'",
            {"c": HEARTBEAT},
        )

        after_sum = python_pane(conn, sum_pick)["agg"]
        after_kept = python_pane(conn, changed_pick)["row_count"]
        # The sum moves by exactly the mutation.
        assert after_sum == before_sum + Decimal(1000)
        # And operation 9 moves too: hb-01's beats 0 and 1 are seeded
        # identical apart from ts (B27's stream for hb-01 draws (ok, 18,
        # lima) at beat 0 and carries it, per the same two-way derivation
        # as the hb-18 fixture above), so beat 1 was NOT kept before, and
        # after the mutation of beat 0 it differs from its predecessor and
        # IS kept: exactly one more row.
        assert after_kept == before_kept + 1
    finally:
        conn.rollback()

    try:
        # After the rollback the pane sees the seeded world again.
        assert python_pane(conn, sum_pick)["agg"] == before_sum
        assert python_pane(conn, changed_pick)["row_count"] == before_kept
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────
# AC-23(b) — the Python pane cannot follow a perturbed SQL side
# ─────────────────────────────────────────────────────────────────────────

_FORBIDDEN_IMPORTS = ("demo.builder", "builder", "demo.probes", "probes", "psycopg")


def _imported_names(path: Path) -> set:
    tree = pyast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, pyast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_ac23b_pyrunner_imports_nothing_from_the_sql_side():
    """Structural half: no module of demo/pyrunner/ imports the query
    builder, the probes, or the database driver (plan §4.5: only the
    connection factory imports the driver; W12's brief: the second
    calculator must not import from builder or probes).  This is the
    same enforcement shape B8 pins for expectations.py."""
    pkg = _REPO_ROOT / "demo" / "pyrunner"
    checked = 0
    for module in sorted(pkg.glob("*.py")):
        names = _imported_names(module)
        for name in names:
            for forbidden in _FORBIDDEN_IMPORTS:
                assert not (
                    name == forbidden or name.startswith(forbidden + ".")
                ), f"{module.name} imports {name!r}"
        checked += 1
    assert checked >= 6  # __init__, decimals, order, rows, evaluate, shape


def test_ac23b_the_answer_is_a_function_of_rows_and_pick_alone():
    """Functional half: the pane's answer has no other input.  Handing the
    pick a perturbed 'SQL answer' changes nothing, because no such channel
    exists — which is what 'the Python pane does not follow it' means from
    this side of the API.  The end-to-end version with the real test hook
    on the compiled expression is W13/W16's (plan §7, AC-23 row)."""
    rows = [
        hb_row("hb-95-0000", "hb-95", "2026-08-14T00:00:00Z", payload={"load": 3, "note": "a"}),
        hb_row("hb-95-0001", "hb-95", "2026-08-14T01:00:00Z", payload={"load": 4, "note": "a"}),
    ]
    pick = hb_pick(aggregate={"fn": "sum", "field": "$.payload.load"})
    baseline = answer(rows, pick)
    assert baseline["agg"] == Decimal("7.000000")  # 3 + 4, by hand

    perturbed = dict(pick)
    perturbed["sql_answer"] = {"agg": "999999.000000"}  # no such input exists
    perturbed["compiled_expression"] = "SELECT 999999"  # nor this
    assert answer(rows, perturbed) == baseline
    # and the same inputs give the same answer again — nothing ambient:
    assert answer(rows, pick) == baseline


# ─────────────────────────────────────────────────────────────────────────
# §7.4(2) — the order the ROWS answer carries when nothing is picked
# ─────────────────────────────────────────────────────────────────────────

def test_rows_order_collapses_to_key_asc_whatever_the_arrival_order():
    # rows.read_rows carries no ORDER BY on purpose; the pipeline's own
    # sort is what §7.4(2) holds responsible.  Feed the runner rows out of
    # order and the answer is in key order.
    rows = [
        hb_row("hb-96-0002", "hb-96", "2026-08-14T02:00:00Z"),
        hb_row("hb-96-0000", "hb-96", "2026-08-14T00:00:00Z"),
        hb_row("hb-96-0001", "hb-96", "2026-08-14T01:00:00Z"),
    ]
    result = answer(rows, hb_pick())
    assert [r["key"] for r in result["rows"]] == [
        "hb-96-0000", "hb-96-0001", "hb-96-0002",
    ]
