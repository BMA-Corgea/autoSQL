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


# ═════════════════════════════════════════════════════════════════════════
# W17 — AC-41(b)(c)(e) and AC-44.  The end-to-end halves, on the seeded
#       database.  AC-41(a) is test_builder_sql.py's grep over the emitted
#       statements; AC-41(d) is walkthrough step 5 and lives in
#       test_walkthrough.py beside the rest of that step.
#
# WHAT EACH PART IS FOR, IN ONE LINE EACH
#   (b) ten runs of one pick return one sequence — catches an order that
#       is stable by luck of the plan rather than by ORDER BY.
#   (c) the Python pane's sequence equals the SQL pane's ELEMENT FOR
#       ELEMENT over the whole result, not merely as sets.
#   (e) the comparator matches on mixed types and on BOTH kinds of null,
#       plus the --locale=C grep that makes the two text comparisons one
#       comparison.
#   AC-44 the record keys, and the fact that text order IS record order.
# ═════════════════════════════════════════════════════════════════════════

import json  # noqa: E402
import re  # noqa: E402
from decimal import Decimal  # noqa: E402

_DEMO_DIR = _REPO_ROOT / "demo"
if str(_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(_DEMO_DIR))

import builder as _builder  # noqa: E402
import legality as _legality  # noqa: E402
from demo.server import app as _server_app  # noqa: E402
from demo.server import db as _db  # noqa: E402

HEARTBEAT = "noun:Heartbeat"
SAMPLE = "noun:Sample"
EDGECASE = "noun:EdgeCase"


def _pick(**kw) -> dict:
    p = _legality.default_pick()
    p.update(kw)
    return p


#: AC-41(b)'s five picks — walkthrough steps 2, 4, 5, 8 and 9.
REPEATED_PICKS = {
    "step 2 (no sort — the tiebreak alone)": _pick(),
    "step 4 (a filter)": _pick(filter='$.status != "ok"'),
    "step 5 ($.ts desc, cap 10)": _pick(sort={"field": "$.ts", "dir": "desc"}, cap=10),
    "step 8 (the rolling window)": _pick(window={"field": "$.payload.load"}),
    "step 9 (changed rows only)": _pick(changed=True),
}


@pytest.fixture(scope="module")
def oconn():
    c = _db.connect(application_name="autosql-demo-order")
    c.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    yield c
    c.close()


def _panes(conn, pick: dict):
    """``run_pick``'s own path to both panes, without the 50-row page."""
    pick = _server_app.normalised_pick(pick)
    verdict = _legality.evaluate(pick)
    assert not verdict["violations"], verdict["violations"]
    keys = _server_app.collection_keys(conn, verdict["source"])
    built = _builder.build(pick, keys)
    sql = _server_app.sql_pane(conn, built)
    kinds = dict(zip(sql["columns"], sql["kinds"]))
    return sql, _server_app.python_pane(conn, pick, kinds)


def _texts(pane) -> list:
    kinds = pane["kinds"]
    return [tuple(_server_app.display_text(row[j], kinds[j]) for j in range(len(row)))
            for row in pane["canon"]]


# ─────────────────────────────────────────────────────────────────────────
# AC-41(b) — ten runs, one sequence.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", list(REPEATED_PICKS))
def test_ac41b_ten_runs_of_one_pick_return_one_sequence(oconn, label):
    """Executed TEN times; the row sequence is identical every time.

    This is the part that catches an order which is stable by luck of the
    plan rather than by ORDER BY — a synchronised sequential scan joining
    the table mid-way returns the same rows starting at a different place,
    and nothing else in the suite would notice (§7.4's "why half (2)
    exists").  Both panes are run each time, so a Python pane that leaned
    on arrival order fails here too.
    """
    pick = REPEATED_PICKS[label]
    sql_seqs, py_seqs = set(), set()
    for _ in range(10):
        sql, python = _panes(oconn, pick)
        ki = sql["columns"].index("key")
        sql_seqs.add(tuple(r[ki] for r in _texts(sql)))
        py_seqs.add(tuple(r[python["columns"].index("key")] for r in _texts(python)))
    assert len(sql_seqs) == 1, f"{label}: the SQL pane returned {len(sql_seqs)} orders in 10 runs"
    assert len(py_seqs) == 1, f"{label}: the Python pane returned {len(py_seqs)} orders in 10 runs"
    (seq,) = sql_seqs
    assert len(set(seq)) == len(seq), f"{label}: a key repeated — the order is not total"


# ─────────────────────────────────────────────────────────────────────────
# AC-41(c) — element for element, over the WHOLE result.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", list(REPEATED_PICKS))
def test_ac41c_the_two_panes_sequences_are_equal_element_for_element(oconn, label):
    """Not "the same set of rows" — the same rows in the same positions."""
    sql, python = _panes(oconn, REPEATED_PICKS[label])
    assert sql["columns"] == python["columns"], f"{label}: the panes disagree on columns"
    a, b = _texts(sql), _texts(python)
    assert len(a) == len(b), f"{label}: {len(a)} rows vs {len(b)}"
    ki = sql["columns"].index("key")
    first_bad = next((i for i in range(len(a)) if a[i][ki] != b[i][ki]), None)
    assert first_bad is None, (
        f"{label}: the sequences first diverge at row {first_bad} — "
        f"SQL {a[first_bad][ki]!r}, Python {b[first_bad][ki]!r}"
    )
    # And as SETS they are equal too, so the failure above can only ever
    # mean "same rows, wrong order" and never "different rows".
    assert {r[ki] for r in a} == {r[ki] for r in b}
    assert a == b, f"{label}: the panes agree on the key order but not on every cell"


# ─────────────────────────────────────────────────────────────────────────
# AC-41(e) — mixed types and BOTH kinds of null, on noun:Sample.
# ─────────────────────────────────────────────────────────────────────────

#: §7.4(1b)'s ladder, ascending.  Written out here rather than imported, so
#: this test can fail if the comparator and the spec ever part company.
ASCENDING_TYPES = ["string", "number", "boolean", "array", "object"]


def _json_type(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float, Decimal)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def test_ac41e_three_bands_in_spec_order_on_a_field_some_rows_omit(oconn):
    """Ascending on ``$.field_14``: JSON nulls, then values, then absent.

    ``noun:Sample`` carries all three cases on this one key — 41 rows hold
    JSON null, 138 hold a value of five different types, and 1,821 omit the
    key entirely.  §7.4(1b): "an ascending sort on such a field has THREE
    bands, in this order: JSON nulls, then everything else by the table,
    then the absent-key rows.  The Python pane has to reproduce all three,
    and it cannot do it by mapping both kinds of null to ``None``."
    """
    pick = _pick(source=SAMPLE, sort={"field": "$.field_14", "dir": "asc"})
    sql, python = _panes(oconn, pick)
    a, b = _texts(sql), _texts(python)
    assert len(a) == len(b) == 2000

    di = sql["columns"].index("data")
    ki = sql["columns"].index("key")

    def band_of(rowtext):
        data = json.loads(rowtext[di])
        if "field_14" not in data:
            return "absent"
        return "json-null" if data["field_14"] is None else "value"

    for name, rows in (("SQL", a), ("Python", b)):
        bands = [band_of(r) for r in rows]
        runs = []
        for x in bands:
            if runs and runs[-1][0] == x:
                runs[-1][1] += 1
            else:
                runs.append([x, 1])
        assert [r[0] for r in runs] == ["json-null", "value", "absent"], (
            f"{name} pane's bands came back as {[r[0] for r in runs]} — "
            "three contiguous bands in §7.4(1b)'s order is the requirement"
        )
        assert [r[1] for r in runs] == [41, 138, 1821], f"{name} pane's band sizes"

        # Inside the value band, the type ladder, ascending.
        seen = []
        for r in rows[41:41 + 138]:
            t = _json_type(json.loads(r[di])["field_14"])
            if not seen or seen[-1] != t:
                assert t not in seen, f"{name} pane: type {t} appears in two blocks"
                seen.append(t)
        assert seen == [t for t in ASCENDING_TYPES if t in seen], (
            f"{name} pane's type ladder was {seen}, not §7.4(1b)'s order"
        )
        # The tiebreak, inside one band: equal values order by key ascending.
        absent_keys = [r[ki] for r in rows[41 + 138:]]
        assert absent_keys == sorted(absent_keys), (
            f"{name} pane: the absent-key band is not in key order"
        )

    assert a == b, "the two panes agree element for element, all 2,000 rows"


def test_ac41e_the_compose_file_pins_the_C_collation(oconn):
    """The grep — and the database that grep is about.

    "That one line is what makes the two panes' text comparisons the same
    comparison" (AC-41(e)).  The line is checked in the file AND the
    running database is asked what it was actually created with, because a
    compose file describes a container that may predate the line.
    """
    compose = (_DEMO_DIR / "compose.yaml").read_text()
    assert "--locale=C" in compose, "demo/compose.yaml does not pin --locale=C"
    assert re.search(r"POSTGRES_INITDB_ARGS:\s*\"[^\"]*--locale=C", compose), (
        "--locale=C is present but not inside POSTGRES_INITDB_ARGS"
    )
    collate, ctype = oconn.execute(
        "SELECT datcollate, datctype FROM pg_database WHERE datname = current_database()"
    ).fetchone()
    assert collate == "C" and ctype == "C", (
        f"the running database was created with collate={collate!r} "
        f"ctype={ctype!r} — a language collation orders text differently "
        "from Python and AC-41(e) is unsatisfiable on it"
    )


# ─────────────────────────────────────────────────────────────────────────
# AC-44 — the record keys, and the fact that TEXT order is RECORD order.
# ─────────────────────────────────────────────────────────────────────────

#: R19's three formats.  Fixed width, zero padded, ASCII.
KEY_FORMATS = {
    HEARTBEAT: (re.compile(r"^hb-\d{2}-\d{4}$"), 8400),
    SAMPLE: (re.compile(r"^smp-\d{4}$"), 2000),
    EDGECASE: (re.compile(r"^edge-\d{2}$"), 10),
}


def _keys(conn, collection: str) -> list:
    return [r[0] for r in conn.execute(
        "SELECT key FROM demo.records WHERE collection = %(c)s ORDER BY key",
        {"c": collection},
    ).fetchall()]


@pytest.mark.parametrize("collection", list(KEY_FORMATS))
def test_ac44a_every_key_matches_its_collections_format(oconn, collection):
    """(a) The regex per collection — what fails if a build reuses
    ``gen_data.py:58``'s unpadded ``S-{i}``, which orders
    ``S-0, S-1, S-10, S-100`` and makes every named row unpredictable."""
    pattern, expected = KEY_FORMATS[collection]
    keys = _keys(oconn, collection)
    assert len(keys) == expected
    bad = [k for k in keys if not pattern.match(k)]
    assert not bad, f"{collection}: {len(bad)} keys off R19's format, e.g. {bad[:5]}"
    assert len(set(keys)) == len(keys), f"{collection}: a key repeats"
    # Fixed width is the property the ordering rests on, so it is asserted
    # rather than inferred from the regex.
    assert len({len(k) for k in keys}) == 1, f"{collection}: keys are not one width"


def test_ac44b_key_order_is_record_order_on_the_heartbeat(oconn):
    """(b) ``ORDER BY key`` groups a sender and runs its beats forward.

    This is the property walkthrough step 8 relies on to display a sender's
    rolling averages in the order the frame computed them.
    """
    rows = oconn.execute(
        "SELECT key, data ->> 'sender_id', data ->> 'ts' FROM demo.records"
        " WHERE collection = %(c)s ORDER BY key", {"c": HEARTBEAT},
    ).fetchall()
    assert len(rows) == 8400

    # Every beat of one sender before any beat of the next, and no sender
    # ever reappears after another has started.
    order, started = [], set()
    for _key, sender, _ts in rows:
        if not order or order[-1] != sender:
            assert sender not in started, (
                f"sender {sender} reappears after {order[-1]} started — "
                "key order does not group senders"
            )
            started.add(sender)
            order.append(sender)
    assert order == [f"hb-{i:02d}" for i in range(1, 51)], (
        "the 50 senders do not appear in ascending sender order"
    )
    # And within one sender, ascending ts.
    for sender in order:
        stamps = [ts for _k, s, ts in rows if s == sender]
        assert len(stamps) == 168
        assert stamps == sorted(stamps), f"{sender}'s beats are not in ts order"
        assert len(set(stamps)) == 168, f"{sender} has a duplicate timestamp"
    # The key's own sender field and the record's agree — the key is not
    # merely well formed, it names the row it belongs to.
    for key, sender, _ts in rows:
        assert key.startswith(sender + "-"), f"{key} does not belong to {sender}"


@pytest.mark.parametrize("collection", list(KEY_FORMATS))
def test_ac44c_python_sorts_the_keys_exactly_as_postgres_does(oconn, collection):
    """(c) The assertion that fails if the database has a language collation.

    Postgres's ``ORDER BY key`` under the ``C`` locale is byte order;
    Python's ``sorted`` is code-point order; on the ASCII these keys are
    made of the two are the same order — and that sameness is what lets
    the Python pane reproduce the SQL pane's tiebreak at all.
    """
    from_pg = _keys(oconn, collection)
    from_python = sorted(from_pg)
    assert from_pg == from_python, (
        f"{collection}: Postgres and Python order these keys differently — "
        "the first divergence is at index "
        f"{next(i for i in range(len(from_pg)) if from_pg[i] != from_python[i])}"
    )
    # The same statement, run through the Python pane's own comparator, so
    # this is not merely a fact about `sorted` but about the code the pane
    # uses (§7.4's tiebreak is that comparator's last component).
    assert [k for _v, k in sorted((MISSING, k) for k in from_pg)] == from_python


def test_ac44_the_hyphen_case_that_a_language_collation_would_flip(oconn):
    """A named example of the failure (c) exists to catch.

    Under ``en_US.UTF-8`` a leading punctuation difference can be ignored
    on the first pass, so ``hb-01-0002`` and ``hb-010002`` could order
    either way. Under ``C`` the hyphen (0x2D) is below every digit, always.
    The demo's own keys are asserted to be ordered by that rule.
    """
    probe = ["hb-01-0002", "hb-010002", "hb-0", "hb-01", "HB-01-0000"]
    from_pg = [r[0] for r in oconn.execute(
        "SELECT k FROM unnest(%(ks)s::text[]) AS k ORDER BY k", {"ks": probe}
    ).fetchall()]
    assert from_pg == sorted(probe), (
        f"Postgres ordered {probe} as {from_pg}; Python's byte order is "
        f"{sorted(probe)} — the collation is not C"
    )
    assert from_pg[0] == "HB-01-0000", "uppercase sorts first under C, and did not"
