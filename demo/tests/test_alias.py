"""AC-38(a) -- the computed-column alias is validated against §4.10's allowlist
before it is emitted, and hostile input is refused by name.

The 13-name hostile table (spec §12 AC-38(a)), one name from each of §4.10's
three name-list collision groups, plus the in-pick duplicate -- the fourth
group, a property of a pick rather than of a name.  Every refusal names the
alias and the rule; none ever reads "invalid input".

AC-38(b) (zero statements reach the database, walkthrough step 14) and (c)
(the emitted `AS "alive"`) are end-to-end criteria driven in
test_walkthrough.py once the server exists; this file is the validator's own
table, which needs no database: the heartbeat's top-level field names are
supplied to the validator here as the pinned list spec §4.10 states for
`noun:Heartbeat` -- that they really come from the data is AC-45's half.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[1]
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from gate import (  # noqa: E402
    ALIAS_RE,
    BUILDER_COLUMNS,
    TABLE_COLUMNS,
    Refused,
    emit_alias,
    validate_alias,
)

#: `noun:Heartbeat`'s top-level JSON field names (spec §4.10, §8.3) -- in the
#: running demo this list is read out of the data by the server at operation 1;
#: here it is the same four names, supplied directly.
HEARTBEAT_KEYS = ["payload", "sender_id", "status", "ts"]


def _refusal(name, keys=(), aliases=()):
    with pytest.raises(Refused) as exc:
        validate_alias(name, keys, aliases)
    message = str(exc.value)
    assert "invalid input" not in message.lower()
    return exc.value


# ---------------------------------------------------------------------------------
# Accepted -- AC-38(a)'s five, validated WITH the collision vocabularies loaded,
# so acceptance is shown to survive the full check rather than an empty one.
# ---------------------------------------------------------------------------------

ACCEPTED = ["alive", "_x", "days_left", "A1", "a" + "b" * 62]


def test_the_63_char_row_really_is_63_chars():
    assert len(ACCEPTED[4]) == 63


@pytest.mark.parametrize("name", ACCEPTED, ids=lambda n: n[:16])
def test_accepted(name):
    assert validate_alias(name, HEARTBEAT_KEYS, ["earlier_alias"]) == name


# ---------------------------------------------------------------------------------
# Refused -- the 13-name hostile table.  (name, the rule-phrase the message
# must carry, the collection-key list in force).
# ---------------------------------------------------------------------------------

HOSTILE = [
    # -- §4.10's pattern: shape, not collision ----------------------------------
    ("", "empty column name", ()),
    ("1abc", "not a usable column name", ()),
    ("my col", "not a usable column name", ()),
    ("my-col", "not a usable column name", ()),
    ("naïve", "not a usable column name", ()),          # non-ASCII
    ("pct%", "not a usable column name", ()),           # % breaks %(name)s binding
    ('a"b', "not a usable column name", ()),            # closes the quoted identifier
    ("alive'--", "not a usable column name", ()),
    ('alive"; DROP TABLE demo.records; --', "not a usable column name", ()),
    ("a" * 64, "not a usable column name", ()),         # 64 chars: Postgres would truncate
    # -- one name from each of §4.10's three collision groups -------------------
    ("data", "column of the demo's own table", ()),                    # group 1
    ("bucket", "query builder emits", ()),                             # group 2
    ("status", "field name of the chosen collection", HEARTBEAT_KEYS), # group 3
]


def test_the_hostile_table_is_exactly_13_names():
    assert len(HOSTILE) == 13
    assert len({name for name, _, _ in HOSTILE}) == 13
    # one representative from each collision group, drawn from the pinned lists
    assert "data" in {"collection", "key", "data"}
    assert "bucket" in {"agg", "bucket", "rolling_avg", "changed"}
    assert "status" in HEARTBEAT_KEYS


@pytest.mark.parametrize(
    "name,rule_phrase,keys", HOSTILE, ids=[repr(h[0])[:34] for h in HOSTILE]
)
def test_hostile_name_refused_naming_alias_and_rule(name, rule_phrase, keys):
    refusal = _refusal(name, keys=keys)
    assert refusal.construct == name
    if name:
        assert name in str(refusal)          # the refusal names the alias ...
    assert rule_phrase in str(refusal)       # ... and the rule it broke


def test_the_injection_name_is_refused_at_the_pattern():
    """The M13 mutant: re.match instead of re.fullmatch accepts this name,
    because match anchors only the start."""
    import re

    hostile = 'alive"; DROP TABLE demo.records; --'
    assert re.match(ALIAS_RE, hostile) is not None      # match WOULD pass it
    assert re.fullmatch(ALIAS_RE, hostile) is None      # fullmatch refuses it
    _refusal(hostile)


# ---------------------------------------------------------------------------------
# The fourth group -- an alias already defined in this pick.
# ---------------------------------------------------------------------------------

def test_in_pick_duplicate_refused():
    assert validate_alias("alive", HEARTBEAT_KEYS, []) == "alive"
    refusal = _refusal("alive", keys=HEARTBEAT_KEYS, aliases=["alive"])
    assert refusal.construct == "alive"
    assert "already defined as a computed column in this pick" in str(refusal)


# ---------------------------------------------------------------------------------
# Each collision group in full -- the pinned lists are finite, so test all of them.
# ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(TABLE_COLUMNS))
def test_every_table_column_refused(name):
    assert name in {"collection", "key", "data"}  # the pinned list, literally
    refusal = _refusal(name)
    assert refusal.construct == name
    assert "column of the demo's own table" in str(refusal)


@pytest.mark.parametrize("name", sorted(BUILDER_COLUMNS))
def test_every_builder_emitted_name_refused(name):
    assert name in {"agg", "bucket", "rolling_avg", "changed"}  # pinned, literally
    refusal = _refusal(name)
    assert refusal.construct == name
    assert "query builder emits" in str(refusal)


@pytest.mark.parametrize("name", HEARTBEAT_KEYS)
def test_every_heartbeat_top_level_key_refused(name):
    refusal = _refusal(name, keys=HEARTBEAT_KEYS)
    assert refusal.construct == name
    assert "field name of the chosen collection" in str(refusal)


def test_collection_keys_only_bind_when_supplied():
    """`status` is a fine alias on a collection that has no `status` field --
    the vocabulary is per-collection, handed over by the caller."""
    assert validate_alias("status", ["id", "priority"], []) == "status"


def test_pattern_runs_before_the_lists():
    """§4.10: a key that could never be an alias is refused by the pattern
    before any list is consulted -- even if that very string is in the list."""
    refusal = _refusal('a"b', keys=['a"b'])
    assert "not a usable column name" in str(refusal)


# ---------------------------------------------------------------------------------
# fullmatch hardening beyond the 13 -- shapes that historically slip anchors.
# ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "alive\n",        # re.match + $ would accept the trailing newline
        "alive\nDROP",
        " alive",
        "alive ",
        "\talive",
        "аlive",          # Cyrillic а (U+0430) -- a homoglyph, not ASCII 'a'
        "a٣",             # Arabic-Indic digit (U+0663) -- \w would take it
        "alive\x00",
    ],
    ids=["trailing-nl", "embedded-nl", "lead-space", "trail-space",
         "lead-tab", "cyrillic-a", "arabic-digit", "nul"],
)
def test_anchor_and_unicode_hostiles_refused(name):
    refusal = _refusal(name)
    assert refusal.construct == name


@pytest.mark.parametrize("junk", [None, 42, b"alive", ["alive"]],
                         ids=["none", "int", "bytes", "list"])
def test_non_string_names_are_refused_not_crashed(junk):
    with pytest.raises(Refused):
        validate_alias(junk, HEARTBEAT_KEYS, [])


# ---------------------------------------------------------------------------------
# The collision lists are exact strings: the emitted alias is double-quoted, so
# `"Data"` is a different SQL identifier from the column `data`, and the Python
# pane keys its dict case-sensitively.  The list is "a finite list rather than
# a description" (§4.10) -- it does not fold case.
# ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Data", "BUCKET", "Status", "Key"])
def test_case_variants_are_not_collisions(name):
    assert validate_alias(name, HEARTBEAT_KEYS, []) == name


# ---------------------------------------------------------------------------------
# Emission: double-quoted, after the check, never instead of it.
# ---------------------------------------------------------------------------------

def test_emit_alias_quotes_after_the_check():
    assert emit_alias("alive", HEARTBEAT_KEYS, []) == '"alive"'


def test_emit_alias_refuses_before_quoting():
    with pytest.raises(Refused):
        emit_alias('alive"; DROP TABLE demo.records; --', HEARTBEAT_KEYS, [])
    with pytest.raises(Refused):
        emit_alias("data", HEARTBEAT_KEYS, [])


def test_the_pattern_is_the_pinned_one():
    """R10 pins the pattern as a literal, so assert the literal -- here, not
    read back from the module under test."""
    assert ALIAS_RE == r"[A-Za-z_][A-Za-z0-9_]{0,62}"
