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


# ═════════════════════════════════════════════════════════════════════════
# W17 — AC-45.  The alias namespace is READ FROM THE DATA, per collection.
#
# Everything above needs no database: it hands the validator a pinned list
# of the heartbeat's four field names.  AC-45 is the criterion that the
# pinned list is not what the demo actually uses — that the names come out
# of the rows, per collection, as a union over the whole collection.
#
# Three parts, each aimed at a different way a build could fake it:
#   (a) `status` refused on noun:Heartbeat and ACCEPTED on noun:EdgeCase.
#       A constant typed into the validator passes half of this and fails
#       the other half.  Driven through POST /api/pick, so it is the
#       screen's own path.
#   (b) a key NO seeded row carries, inserted into a scratch collection
#       inside a rolled-back transaction, is refused on that collection.
#       A hard-coded list CANNOT pass this; only reading the data can.
#       B9 puts it at server level (the screen's source control is a
#       closed set of three, so no scratch collection is choosable there);
#       B10 puts it inside a transaction that is rolled back.
#   (c) on noun:Sample, whose rows carry DIFFERENT subsets of field_0 …
#       field_14, EVERY one of those names is refused — which is the part
#       that fails if the list is the keys of whichever row came back
#       first rather than the union over the collection.
# ═════════════════════════════════════════════════════════════════════════

import json as _json  # noqa: E402

_REPO_ROOT = DEMO_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import legality as _legality  # noqa: E402
from demo.server import app as _server_app  # noqa: E402
from demo.server import db as _db  # noqa: E402

HEARTBEAT = "noun:Heartbeat"
SAMPLE = "noun:Sample"
EDGECASE = "noun:EdgeCase"

#: B9's scratch collection, and a field name no seeded row carries.
SCRATCH = "noun:__scratch__"
SCRATCH_FIELD = "w17_scratch_only_field"

#: The refusal §4.10 requires for a collision — it must name the collision
#: rather than saying "invalid".
COLLISION_PHRASE = "already a top-level field name of the chosen collection"


@pytest.fixture(scope="module")
def aconn():
    c = _db.connect(application_name="autosql-demo-alias")
    yield c
    c.close()


@pytest.fixture(scope="module")
def aclient():
    from fastapi.testclient import TestClient

    return TestClient(_server_app.app)


def _alias_pick(source: str, name: str, expression: str) -> dict:
    p = _legality.default_pick()
    p["source"] = source
    p["computed"] = [{"name": name, "expr": expression}]
    return p


def _try_alias(client, source: str, name: str, expression: str):
    r = client.post("/api/pick", json=_alias_pick(source, name, expression))
    return r.status_code, r.json()


# ── AC-45(a) — per collection, not a constant ────────────────────────────

def test_ac45a_status_is_refused_on_the_heartbeat_naming_the_collision(aclient):
    status, body = _try_alias(aclient, HEARTBEAT, "status", "$.ts")
    assert status == 422 and body["accepted"] is False
    refusal = body["refusal"]
    assert refusal["layer"] == 1 and refusal["kind"] == "alias"
    assert refusal["construct"] == "status"
    assert COLLISION_PHRASE in refusal["why"], (
        f"the refusal must name the collision; it said: {refusal['why']!r}"
    )
    assert "status" in refusal["why"]
    assert refusal["sql_existed"] is False


def test_ac45a_the_same_name_is_accepted_on_edgecase(aclient):
    """The half a hard-coded list fails.

    B24 keeps every ``noun:EdgeCase`` row free of a ``status`` key
    precisely so this pair can be shown; if a reseed adds one, this fails
    rather than quietly making AC-45(a) untestable.
    """
    status, body = _try_alias(aclient, EDGECASE, "status", "$.label")
    assert status == 200, (
        "`status` must be ACCEPTED on noun:EdgeCase — that pair is what "
        f"proves the list is per-collection. Got: {body.get('refusal')}"
    )
    assert body["accepted"] is True
    assert "status" in body["panes"]["sql"]["columns"]
    assert "status" in body["panes"]["python"]["columns"]
    assert 'AS "status"' in body["sql"]["parameterised"]


def test_ac45a_the_pair_really_is_about_the_data_and_not_the_collection_name(aconn):
    """Why the pair proves anything: one collection HAS the key, one has not."""
    hb = _server_app.collection_keys(aconn, HEARTBEAT)
    edge = _server_app.collection_keys(aconn, EDGECASE)
    assert "status" in hb, "the heartbeat's rows really do carry `status`"
    assert "status" not in edge, (
        "B24 requires no EdgeCase row to carry a `status` key; the seed now "
        f"gives {edge}"
    )


# ── AC-45(b) — the seed-independent half, at server level (B9), inside a
#               transaction that is rolled back (B10) ─────────────────────

def test_ac45b_a_key_no_seeded_row_carries_is_refused_on_a_scratch_collection(aconn):
    """A hard-coded list cannot pass this; only reading the data can.

    The row is INSERTed and the two assertions run **on the same
    connection, inside the same transaction**, so the field-name reader
    sees it — and the transaction is rolled back, so nothing is ever
    committed and no ordering between tests matters (B10).  The digest
    guard in conftest.py is the independent proof that this left nothing
    behind.
    """
    for collection in (HEARTBEAT, SAMPLE, EDGECASE):
        assert SCRATCH_FIELD not in _server_app.collection_keys(aconn, collection), (
            f"{SCRATCH_FIELD} is supposed to be a name NO seeded row carries"
        )
    before = aconn.execute("SELECT count(*) FROM demo.records").fetchone()[0]
    try:
        aconn.execute(
            "INSERT INTO demo.records (collection, key, data)"
            " VALUES (%(c)s, %(k)s, %(d)s::jsonb)",
            {"c": SCRATCH, "k": "scratch-00",
             "d": _json.dumps({SCRATCH_FIELD: 1})},
        )
        keys = _server_app.collection_keys(aconn, SCRATCH)
        assert keys == [SCRATCH_FIELD], (
            "the field-name reader did not learn the scratch row's key — "
            f"it returned {keys}"
        )
        with pytest.raises(Refused) as excinfo:
            validate_alias(SCRATCH_FIELD, keys, [])
        assert SCRATCH_FIELD in str(excinfo.value)
        assert COLLISION_PHRASE in str(excinfo.value)
        # And the control: a name the scratch row does NOT carry is fine,
        # so the refusal above is about this key and not about everything.
        validate_alias("some_other_name", keys, [])
        # The seeded collections are unaffected by the scratch row.
        assert SCRATCH_FIELD not in _server_app.collection_keys(aconn, HEARTBEAT)
    finally:
        aconn.rollback()
    after = aconn.execute("SELECT count(*) FROM demo.records").fetchone()[0]
    assert after == before, "the scratch row was not rolled back"
    assert _server_app.collection_keys(aconn, SCRATCH) == [], (
        "the scratch collection still exists after the rollback"
    )


# ── AC-45(c) — the UNION over the collection, not one row's keys ─────────

def test_ac45c_the_sample_rows_really_do_carry_different_subsets(aconn):
    """The premise of (c), measured rather than assumed.

    (c) only proves the list is the UNION if a single row's keys would be
    a WRONG answer.  Measured on this seed: ``noun:Sample`` rows carry
    between 5 and 15 of the fifteen ``field_n`` keys, in 11 distinct
    subsets, and the first row in key order carries 13 of them — so an
    implementation that read one row's keys would let at least one
    ``field_n`` through as an alias.  Those are the facts (c) rests on, so
    they are asserted here; if a reseed ever made every row carry all
    fifteen, (c) would pass by accident and this test says so first.
    """
    per_row = dict(aconn.execute(
        "SELECT key, count(*) FROM demo.records,"
        " LATERAL jsonb_object_keys(data) AS k"
        " WHERE collection = %(c)s AND k LIKE 'field\\_%%'"
        " GROUP BY key", {"c": SAMPLE},
    ).fetchall())
    assert len(per_row) == 2000
    assert min(per_row.values()) < 15, (
        "every noun:Sample row carries all fifteen field_n keys, so reading "
        "one row would be indistinguishable from reading the union and "
        "AC-45(c) proves nothing on this seed"
    )
    subsets = {r[0] for r in aconn.execute(
        "SELECT string_agg(k, ',' ORDER BY k) FROM demo.records,"
        " LATERAL jsonb_object_keys(data) AS k"
        " WHERE collection = %(c)s AND k LIKE 'field\\_%%'"
        " GROUP BY key", {"c": SAMPLE},
    ).fetchall()}
    assert len(subsets) > 1, "the rows all carry the same subset"

    # The row a naive "read one row" build would read first, and exactly
    # which names it would then wrongly accept.
    first_key, first_keys = aconn.execute(
        "SELECT key, (SELECT array_agg(k ORDER BY k) FROM"
        " jsonb_object_keys(data) AS k WHERE k LIKE 'field\\_%%')"
        " FROM demo.records WHERE collection = %(c)s"
        " ORDER BY key LIMIT 1", {"c": SAMPLE},
    ).fetchone()
    missed = sorted(set(f"field_{i}" for i in range(15)) - set(first_keys))
    assert missed, (
        f"the first noun:Sample row ({first_key}) carries every field_n, so "
        "one row's keys would be the right answer here by luck"
    )

    union = [k for k in _server_app.collection_keys(aconn, SAMPLE)
             if k.startswith("field_")]
    assert sorted(union) == sorted(f"field_{i}" for i in range(15)), (
        "the reader's union is not the fifteen field_n names"
    )
    assert set(missed) <= set(union), (
        f"{missed} are in the union but not on {first_key} — those are the "
        "names a one-row build would wrongly accept, and the parametrised "
        "test below refuses every one of them"
    )


@pytest.mark.parametrize("index", range(15))
def test_ac45c_every_field_n_is_refused_on_noun_sample(aclient, index):
    """All fifteen, one test each, through the screen's own route."""
    name = f"field_{index}"
    status, body = _try_alias(aclient, SAMPLE, name, "$.id")
    assert status == 422, f"{name} was ACCEPTED on noun:Sample"
    assert body["refusal"]["construct"] == name
    assert COLLISION_PHRASE in body["refusal"]["why"]


def test_ac45c_a_name_no_sample_row_carries_is_still_accepted(aclient):
    """The negative control: (c) is not "noun:Sample refuses everything"."""
    status, body = _try_alias(aclient, SAMPLE, "field_15", "$.id")
    assert status == 200, (
        "`field_15` is on no noun:Sample row, so it must be accepted — "
        f"otherwise the refusal is a blanket one. Got: {body.get('refusal')}"
    )
    assert 'AS "field_15"' in body["sql"]["parameterised"]
