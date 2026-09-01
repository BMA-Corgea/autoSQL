"""The shipping runtime's standing tests.

T-6 proved variant C with one-off probes. A probe that ran once is not a guard,
so the load-bearing ones are promoted here and run every build:

  * the generated file is not stale for this interpreter          (AC-3)
  * the digit mapping is exactly what Python's float() accepts    (AC-4)
  * xpr.num agrees with the real evaluator, case by case          (AC-2)
  * translate() stays INSIDE the failure branch                   (AC-5)
  * the ASCII path still skips translate(), measured                (AC-5)
  * the spike runtimes are still byte-identical to their digests  (AC-8)

The database tests need a throwaway Postgres with runtime.sql installed:

    docker run -d --name autosql-t8-db -e POSTGRES_PASSWORD=throwaway \\
      -e POSTGRES_USER=glp_owner -e POSTGRES_DB=autosql_spike \\
      -p 55434:5432 pgvector/pgvector:pg16
    psql ... < runtime/runtime.sql
    AUTOSQL_RUNTIME_DSN='host=127.0.0.1 port=55434 ...' pytest runtime/tests

They SKIP without that DSN rather than failing, so the pure-Python guards still
run anywhere. Port 55433 is refused outright: it is the live database.
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")

import generate  # noqa: E402  the generator under test

DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is the live database")

needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")


@pytest.fixture(scope="module")
def conn():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as cx:
        yield cx


# ── AC-3 · the committed bytes are what this interpreter produces ──────────

def test_the_generated_runtime_is_not_stale():
    """A Python whose Unicode data moved would silently split the two engines.

    This is the guard, and its failure message is the whole point: it does not
    just say "regenerate", it says the digit sets may have drifted apart.
    """
    committed = io.open(RUNTIME / "runtime.sql", encoding="utf-8").read()
    assert committed == generate.render(), (
        "runtime/runtime.sql is stale for this interpreter (Unicode %s). "
        "Regenerate with: python3 runtime/generate.py — and if the digit set itself "
        "moved, the SQL and Python halves have drifted apart; read runtime/README.md "
        "before committing." % unicodedata.unidata_version)


def test_the_generator_is_the_only_writer():
    """runtime.sql must carry its DO-NOT-EDIT banner, or someone hand-edited it."""
    head = io.open(RUNTIME / "runtime.sql", encoding="utf-8").read(400)
    assert "GENERATED FILE — DO NOT EDIT" in head
    assert "runtime/generate.py" in head


# ── AC-4 · the mapping is exactly what float() accepts ────────────────────

def test_the_digit_table_is_exactly_what_float_accepts():
    """Enumerated against float() itself, not against the category name.

    `Nd` is the set the generator uses; that it coincides with what float()
    accepts is the assumption this test refuses to leave unchecked.
    """
    mapped = set(generate.nonascii_decimal_digits())
    accepted = set()
    for cp in range(0x110000):
        ch = chr(cp)
        if ch.isascii():
            continue
        try:
            float(ch)
        except (ValueError, TypeError):
            continue
        accepted.add(cp)
    assert mapped == accepted, (
        "false negatives (float accepts, mapping misses): %r ; "
        "false positives (mapping has, float rejects): %r"
        % (sorted(accepted - mapped)[:12], sorted(mapped - accepted)[:12]))


def test_every_digit_maps_to_its_own_numeric_value():
    """translate() must send ٣ to '3', not merely to some digit."""
    nd = generate.nonascii_decimal_digits()
    tbl = generate.tables()
    for cp, replacement in zip(nd, tbl["ND_MAP_TO"]):
        assert replacement == str(unicodedata.decimal(chr(cp))), hex(cp)


def test_the_whitespace_table_is_pythons_whole_strip_set():
    ws = set(generate.python_whitespace())
    assert ws == {cp for cp in range(0x110000) if chr(cp).isspace()}
    # The failure this encodes: SQL's own btrim covers six of them.
    assert len(ws - set(b" \t\n\r\f\v".decode())) > 0


# ── AC-5 · the nesting is load-bearing, so it is asserted structurally ────

def test_translate_is_inside_the_failure_branch_not_above_the_ascii_gate():
    """Hoisting it costs 5.3x on every ordinary numeric string (T-6, measured).

    Asserted on the TEMPLATE, where a human would do the hoisting.
    """
    src = io.open(RUNTIME / "runtime.sql.in", encoding="utf-8").read()
    gate = src.index("IF t !~ '^[+-]?([0-9]+")          # the ASCII gate
    trans = src.index("translate(")
    assert trans > gate, "translate() was hoisted above the ASCII gate — see T-6 FINDINGS §B"
    assert "Do not hoist it." in src, "the warning that keeps it there was removed"


# ── AC-8 · the spike runtimes are evidence and must not have moved ────────

@pytest.mark.parametrize("rel,sha", [
    ("spikes/T-1/proto/runtime.sql", "1c58d548a6045aa6"),
    ("spikes/T-6/runtime.sql", "871b1b4c2df95719"),
])
def test_the_spike_runtimes_are_frozen(rel, sha):
    """Their digests are cited in T-3's and T-6's findings and in 42 battery
    outputs. Editing one breaks the chain that lets anyone re-derive those
    results — the single worst thing this ticket could do."""
    got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]
    assert got == sha, "%s has been modified — it is evidence, not source" % rel


# ── AC-2 · the runtime agrees with the real Python evaluator ──────────────

CASES = (
    ["123", "-4.5", ".5", "5.", "1e3", "1E-3", "+7", "  7  "] +
    ["n/a", "", "abc", "1,234", "1_2", "0x10", "inf", "nan"] +
    ["１２３", "١٢٣", "۱۲۳",
     "๑๒๓", "१२३", "１.５",
     "٣.٥", "1２3", "-１２３", "+٣",
     "۱۲۳e2", "1e３", "\U0001D7CE\U0001D7CF"] +
    ["Item ３", "３abc", "．５", "٣,٥"] +
    [" 7 ", " 7 ", "　1　", "\x1c7\x1f",
     " １２３ ", "7 8"]
)


@needs_db
@pytest.mark.parametrize("s", CASES, ids=[repr(c) for c in CASES])
def test_xpr_num_agrees_with_the_python_evaluator(conn, s):
    """The whole correctness claim, one string at a time.

    Every case must AGREE — variant C matches rather than refusing, so a refusal
    of the coercion class here is a failure, not an allowed outcome.
    """
    import json
    from core.dashboard.expr import _to_num          # the REAL evaluator

    want = _to_num(s)
    with conn.cursor() as cur:
        cur.execute("select xpr.num(%s::jsonb)", (json.dumps(s),))
        got = cur.fetchone()[0]

    if want is None:
        assert got is None, "SQL answered %r where Python declined" % got
    else:
        assert got is not None, "SQL returned NULL where Python read %r" % want
        assert abs(got - want) <= 1e-9 * max(1.0, abs(want))


@needs_db
def test_the_magnitude_refusal_still_fires(conn):
    """Variant C removes the COERCION refusal. XPR01, the out-of-range guard,
    is a different thing and must survive."""
    import psycopg
    with conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as e:
            cur.execute("select xpr.num('\"1e400\"'::jsonb)")
        assert e.value.sqlstate == "XPR01"


@needs_db
def test_no_coercion_refusal_is_raised_by_any_case(conn):
    """The point of variant C: nothing in CASES may raise XPR02."""
    import json
    import psycopg
    for s in CASES:
        with conn.cursor() as cur:
            try:
                cur.execute("select xpr.num(%s::jsonb)", (json.dumps(s),))
                cur.fetchone()
            except psycopg.Error as exc:
                assert exc.sqlstate != "XPR02", "coercion refusal survives for %r" % s


@needs_db
def test_the_installed_schema_is_complete(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from pg_proc p join pg_namespace n "
                    "on n.oid = p.pronamespace where n.nspname = 'xpr'")
        assert cur.fetchone()[0] == 21


@needs_db
def test_the_ascii_path_skips_the_translate(conn):
    """The nesting, measured rather than only asserted structurally.

    A DIFFERENTIAL, not a benchmark: compare xpr.num on an ASCII-numeric string
    (passes the gate, must never reach translate) against one that misses the
    gate (must reach it). Nested, the second is several times dearer. HOISTED,
    both pay translate and the ratio collapses toward 1 — which is precisely the
    5.3x regression on ordinary numbers that T-6 measured and rejected.

    Self-calibrating, so it means the same thing on a fast laptop and a noisy CI
    box: no absolute millisecond figure appears in the assertion.
    """
    def timed(sql, n=3):
        best = None
        for _ in range(n):
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.fetchone()
            d = time.perf_counter() - t0
            best = d if best is None else min(best, d)
        return best

    ascii_path = timed("select count(xpr.num(to_jsonb(g::text))) "
                       "from generate_series(1,60000) g")
    fallback = timed("select count(xpr.num(to_jsonb('abc' || g::text))) "
                     "from generate_series(1,60000) g")
    assert fallback > ascii_path * 2.0, (
        "the ASCII path costs %.3fs and the fallback %.3fs (%.2fx). They should differ "
        "by several times, because only the fallback runs translate(). A ratio near 1 "
        "means translate() has been hoisted above the ASCII gate — see T-6 FINDINGS §B."
        % (ascii_path, fallback, fallback / ascii_path))
