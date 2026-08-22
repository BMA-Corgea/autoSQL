"""§7.4's comparator — unit tests over a HAND-WRITTEN fixture (W9).

WHAT LIVES HERE, AND WHOSE IT IS
  * W9 (this file's first landing): the comparator alone, no database —
    demo/pyrunner/order.py reproduces a hand-written expected sequence over
    a mixed-type fixture.  The expected sequences below were derived BY HAND
    from spec §7.4(1b)'s table, row by row, and are stated as literals so a
    reviewer can check the ordering against the spec without trusting the
    code under test (or any code at all).
  * W17 adds AC-41(b)(c)(d)(e) and AC-44 — the end-to-end halves that need
    the seeded database and the running stack.  Not here yet.

WHAT THE FIXTURE DELIBERATELY CONTAINS
  - BOTH kinds of null (§7.4(1b)): present JSON null (None) and absent key
    (MISSING) — they band differently and may never merge;
  - strings whose C-collation byte order differs from dictionary order
    ("Zed" before "a-b" before "ab" — uppercase first, hyphen first);
  - numbers as int and Decimal mixed, including a value tie with different
    representations (2.5 vs 2.50);
  - arrays where length dominates content and elements compare numerically
    (so [1,2] < [1,10] — a text sort would flip it);
  - objects pinning pair-count dominance, storage order (shorter keys
    first), interleaved key-1,value-1,key-2,value-2 comparison, and the
    Postgres docs' own example {"aa":1,"c":1} > {"b":1,"d":1};
  - keys chosen so that key order does NOT equal value order inside any
    band, and an input order that matches neither expected sequence — a
    comparator that falls back on the key, or a sort that leaks input order
    through stability, fails loudly.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.pyrunner.order import MISSING, compare_jsonb, sort_key  # noqa: E402

# ---------------------------------------------------------------------------
# THE FIXTURE.  (key, sort-field value) pairs, listed in a scrambled order
# that matches neither expected sequence.

FIXTURE = [
    ("o5", {"a": 1, "c": 9}),
    ("d3", 2),                    # int on purpose, amid Decimals
    ("z2", MISSING),              # absent key — SQL NULL, the NULLS LAST band
    ("s4", "apple"),
    ("a1", [1, 2]),
    ("n2", None),                 # present JSON null — a VALUE, not SQL NULL
    ("b1", True),
    ("o1", {"a": 1}),
    ("d2", Decimal("2.5")),
    ("s1", "Zed"),
    ("a5", []),
    ("o8", {"b": 1, "d": 1}),
    ("d5", 10),
    ("a3", [1, 10]),
    ("o3", {"b": 0}),
    ("s5", ""),
    ("b2", False),
    ("d1", Decimal("-3")),
    ("a6", [1]),
    ("o2", {"a": 1, "b": 2}),
    ("z1", MISSING),
    ("s2", "a-b"),
    ("o7", {"aa": 1, "c": 1}),
    ("d4", Decimal("2.50")),      # == 2.5 in value: a genuine numeric tie
    ("a4", ["x"]),
    ("n1", None),
    ("o6", {"a": 2, "b": 0}),
    ("a2", [0, 0, 0]),
    ("o4", {"a": []}),
]

# ---------------------------------------------------------------------------
# THE EXPECTED ASCENDING SEQUENCE — derived by hand from §7.4(1b):
#
# Band 1 · JSON nulls first (Null is the smallest jsonb type; tie -> key ASC):
#   n1, n2
# Band 2 · strings, C-collation byte order:
#   ""(s5) < "Zed"(s1: Z=0x5A) < "a-b"(s2: -=0x2D) < "ab"... none < "apple":
#   s5, s1, s2, s4        ("a-b" < "apple" because 0x2D < 0x70)
# Band 3 · numbers, numeric order; the 2.5/2.50 tie breaks by key ASC:
#   -3(d1) < 2(d3) < 2.5(d2 == d4: keys d2 < d4) < 10(d5)
#   d1, d3, d2, d4, d5
# Band 4 · booleans, false < true:
#   b2, b1
# Band 5 · arrays: length first, then element by element (numeric, not text):
#   [](a5) < ["x"](a4) < [1](a6: string<number) < [1,2](a1) < [1,10](a3: 2<10)
#   < [0,0,0](a2: longer beats content)
#   a5, a4, a6, a1, a3, a2
# Band 6 · objects: pair count first; equal counts compare pairs in storage
#   order (shorter key first, bytewise within a length), key-1, value-1,
#   key-2, value-2:
#   one pair:  {"a":1}(o1) < {"a":[]}(o4: same key, number<array)
#              < {"b":0}(o3: key "a"<"b" decides first)
#   two pairs: {"a":1,"b":2}(o2) < {"a":1,"c":9}(o5: k1,v1 tie; "b"<"c")
#              < {"a":2,"b":0}(o6: v1 1<2 decides BEFORE the second key —
#                the interleaving pin; all-keys-first would say o6 < o5)
#              < {"b":1,"d":1}(o8: k1 "a"<"b")
#              < {"aa":1,"c":1}(o7: storage puts "c" first, k1 "b"<"c" —
#                the Postgres docs' own example, {"aa":1,"c":1} > {"b":1,"d":1})
#   o1, o4, o3, o2, o5, o6, o8, o7
# Band 7 · absent keys LAST — NULLS LAST (tie -> key ASC):
#   z1, z2

EXPECTED_ASC = [
    "n1", "n2",
    "s5", "s1", "s2", "s4",
    "d1", "d3", "d2", "d4", "d5",
    "b2", "b1",
    "a5", "a4", "a6", "a1", "a3", "a2",
    "o1", "o4", "o3", "o2", "o5", "o6", "o8", "o7",
    "z1", "z2",
]

# THE EXPECTED DESCENDING SEQUENCE — the VALUE order inverts; three things
# do not (§7.4(1a), (1)):
#   * the absent band stays LAST (NULLS LAST is unconditional),
#   * every tie still breaks key ASC (d2 before d4; n1 before n2; z1 before z2),
#   * within the present values, JSON nulls are now at the END of the values
#     (smallest value, descending), but still BEFORE the absent band.
EXPECTED_DESC = [
    "o7", "o8", "o6", "o5", "o2", "o3", "o4", "o1",
    "a2", "a3", "a1", "a6", "a4", "a5",
    "b1", "b2",
    "d5", "d2", "d4", "d3", "d1",
    "s4", "s2", "s1", "s5",
    "n1", "n2",
    "z1", "z2",
]


def _sorted_keys(direction):
    return [k for k, v in sorted(FIXTURE, key=lambda r: sort_key(r[1], r[0], direction))]


def test_fixture_ascending_matches_the_hand_written_sequence():
    assert _sorted_keys("asc") == EXPECTED_ASC


def test_fixture_descending_matches_the_hand_written_sequence():
    assert _sorted_keys("desc") == EXPECTED_DESC


def test_the_fixture_is_honest():
    """The scrambled input order matches neither expected sequence (so a
    stability leak cannot pass), the keys are unique (so both sequences are
    total), and the key-alphabetical order differs from both expected
    sequences (so a comparator that quietly sorts by key cannot pass)."""
    input_keys = [k for k, _ in FIXTURE]
    assert len(set(input_keys)) == len(input_keys)
    assert sorted(input_keys) != EXPECTED_ASC
    assert sorted(input_keys) != EXPECTED_DESC
    assert input_keys != EXPECTED_ASC
    assert input_keys != EXPECTED_DESC
    assert sorted(EXPECTED_ASC) == sorted(input_keys)
    assert sorted(EXPECTED_DESC) == sorted(input_keys)


# ---------------------------------------------------------------------------
# The three bands, small and explicit — edge-08's shape (plan B24): a present
# JSON null beside keys that are simply absent from every other row.

THREE_BANDS = [
    ("e3", Decimal("5")),
    ("e1", None),        # present, holds JSON null
    ("e4", "x"),
    ("e2", MISSING),     # the key is absent from this record
]


def test_ascending_has_three_bands_in_spec_order():
    """§7.4(1b): 'an ascending sort on such a field has THREE bands, in this
    order: JSON nulls, then everything else by the table, then the
    absent-key rows.'  ("x" is a string, 5 a number: string < number.)"""
    assert [k for k, v in sorted(THREE_BANDS, key=lambda r: sort_key(r[1], r[0], "asc"))] == [
        "e1", "e4", "e3", "e2"
    ]


def test_descending_keeps_the_absent_band_last():
    """NULLS LAST is unconditional; only the present values invert."""
    assert [k for k, v in sorted(THREE_BANDS, key=lambda r: sort_key(r[1], r[0], "desc"))] == [
        "e3", "e4", "e1", "e2"
    ]


# ---------------------------------------------------------------------------
# The reverse=True trap (§7.4(1a)): walkthrough step 5's shape — a
# descending sort where EVERY row ties.  The tiebreak must come back key
# ASCENDING; the banned idiom (reverse=True over a tuple containing key)
# returns key descending and fails this test.

def test_descending_tie_breaks_key_ascending():
    rows = [("hb-03", Decimal("7")), ("hb-01", Decimal("7")), ("hb-02", Decimal("7"))]
    got = [k for k, v in sorted(rows, key=lambda r: sort_key(r[1], r[0], "desc"))]
    assert got == ["hb-01", "hb-02", "hb-03"], (
        "the tiebreak flipped with the sort direction — the reverse=True bug (§7.4(1a))"
    )


def test_no_sort_field_collapses_to_key_asc():
    """§7.4(2): a pick with no sort field still carries a total order —
    MISSING for every row leaves exactly `ORDER BY key ASC`."""
    rows = [("hb-02-0004", MISSING), ("hb-01-0155", MISSING), ("hb-01-0007", MISSING)]
    got = [k for k, v in sorted(rows, key=lambda r: sort_key(r[1], r[0], "asc"))]
    assert got == ["hb-01-0007", "hb-01-0155", "hb-02-0004"]


# ---------------------------------------------------------------------------
# compare_jsonb directly — one assertion per sentence of §7.4(1b)'s table.

def test_the_type_ladder():
    """Object > Array > Boolean > Number > String > Null, each adjacent pair."""
    ladder = [None, "", 0, False, [], {}]
    for lo, hi in zip(ladder, ladder[1:]):
        assert compare_jsonb(lo, hi) == -1, f"{lo!r} should sort below {hi!r}"
        assert compare_jsonb(hi, lo) == 1


def test_booleans_are_not_numbers_here():
    """Python says 0 == False and 1 == True; jsonb_typeof does not.  A
    comparator built on Python equality passes everything else and fails
    this (§7.2 item 5's trap, in its ordering form)."""
    assert compare_jsonb(0, False) == -1   # number < boolean
    assert compare_jsonb(True, 1) == 1     # boolean > number
    assert compare_jsonb(False, True) == -1


def test_strings_compare_as_C_collation_bytes():
    assert compare_jsonb("Zed", "a-b") == -1   # 0x5A < 0x61: uppercase first
    assert compare_jsonb("a-b", "ab") == -1    # 0x2D < 0x62: hyphen first
    assert compare_jsonb("ab", "apple") == -1  # 0x62 < 0x70
    assert compare_jsonb("", "Zed") == -1      # empty string smallest
    assert compare_jsonb("apple", "apple") == 0


def test_numbers_compare_numerically_across_representations():
    assert compare_jsonb(Decimal("2.5"), Decimal("2.50")) == 0
    assert compare_jsonb(2, Decimal("2.5")) == -1
    assert compare_jsonb(Decimal("-3"), 2) == -1
    assert compare_jsonb(10, Decimal("2.50")) == 1
    assert compare_jsonb(2, 10) == -1          # 2 < 10 numerically; "10" < "2" as text


def test_arrays_length_dominates_then_elements():
    assert compare_jsonb([], ["x"]) == -1
    assert compare_jsonb([{"a": 1}], [0, 0]) == -1   # len 1 < 2, despite the object
    assert compare_jsonb([1, 2], [1, 10]) == -1      # elements numeric
    assert compare_jsonb(["x"], [1]) == -1           # string < number, same length
    assert compare_jsonb([1, 2], [1, 2]) == 0


def test_objects_pair_count_dominates():
    assert compare_jsonb({"a": 1}, {"a": 1, "b": 2}) == -1
    assert compare_jsonb({"z": {"deep": [1, 2, 3]}}, {"a": 0, "b": 0}) == -1


def test_objects_equal_counts_compare_interleaved_in_storage_order():
    # k1 ties, v1 decides — BEFORE the second key is ever looked at.
    # (All-keys-first would compare "c" vs "b" and give the opposite answer.)
    assert compare_jsonb({"a": 1, "c": 9}, {"a": 2, "b": 0}) == -1
    # The Postgres docs' own example of storage-order comparison:
    # {"aa":1,"c":1} storage order is [("c",1),("aa",1)] (shorter key first),
    # so k1 is "c" vs "b" — and "c" > "b".
    assert compare_jsonb({"aa": 1, "c": 1}, {"b": 1, "d": 1}) == 1
    # Storage order itself decides which pair is pair 1: both objects store
    # ("b", …) first because "b" is shorter than "aa", so v1 compares 9 vs 0
    # and the first object is GREATER — alphabetical pair order ("aa" first)
    # would compare 0 vs 1 and say LESS.
    assert compare_jsonb({"aa": 0, "b": 9}, {"aa": 1, "b": 0}) == 1
    # Same storage order, same keys: the second pair's value decides.
    assert compare_jsonb({"b": 1, "aa": 2}, {"b": 1, "aa": 3}) == -1
    assert compare_jsonb({"a": 1, "b": 2}, {"b": 2, "a": 1}) == 0  # insertion order is meaningless


def test_json_null_is_a_value_and_missing_is_not():
    assert compare_jsonb(None, None) == 0
    assert compare_jsonb(None, "") == -1       # null below every other value
    assert compare_jsonb(None, False) == -1
    with pytest.raises(TypeError):
        compare_jsonb(MISSING, 1)              # absent keys are sort_key's business
    with pytest.raises(TypeError):
        compare_jsonb(1, MISSING)


def test_sort_key_rejects_what_the_closed_set_does_not_contain():
    with pytest.raises(ValueError):
        sort_key(1, "k", "ASC")        # the direction keywords are exact (§4.4 row 7)
    with pytest.raises(ValueError):
        sort_key(1, "k", "ascending")
    with pytest.raises(TypeError):
        sort_key(1, None)              # the tiebreak key must be text
