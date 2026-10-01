"""T-52: the runtime is genuinely parallel safe (T-44 lever a), and stays so.

A parallel label is a claim about code. A wrong one cannot be seen in any one-row test:
it fails only when the planner gives a query workers. T-44 measured exactly that. With
xpr.num's old EXCEPTION block, which opens a subtransaction that PostgreSQL 16 refuses in
parallel mode, merely LABELLING the bodies safe made 395 battery cases raise 25000. These
tests force a worker and check the code paths the label vouches for.

Database tests: AUTOSQL_RUNTIME_DSN, as in test_runtime.py.  They SKIP without it.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_RUNTIME_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is the live database")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_RUNTIME_DSN to a throwaway Postgres")
SQL = io.open(ROOT / "runtime" / "runtime.sql", encoding="utf-8").read()


def test_no_function_opens_an_exception_block():
    """An EXCEPTION handler opens a subtransaction: parallel UNSAFE, whatever the label says."""
    assert "EXCEPTION WHEN" not in SQL


def test_every_function_is_labelled_parallel_safe():
    headers = re.findall(r"^LANGUAGE (?:sql|plpgsql) (?:IMMUTABLE|STABLE)( PARALLEL SAFE)?", SQL, re.M)
    assert len(headers) == SQL.count("CREATE OR REPLACE FUNCTION") == 23
    assert all(headers), "a function lost its PARALLEL SAFE label"


@pytest.fixture(scope="module")
def conn():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as cx:
        yield cx


@needs_db
def test_every_installed_function_is_parallel_safe(conn):
    rows = conn.execute("select p.proname, p.proparallel from pg_proc p join pg_namespace n "
                        "on n.oid = p.pronamespace where n.nspname = 'xpr'").fetchall()
    assert len(rows) == 23 and {r[1] for r in rows} == {"s"}, rows


@needs_db
@pytest.mark.parametrize("raw,expect", [
    ('" 7 "', 7.0), ('"１２３"', 123.0), ('"1e3"', 1000.0), ('"12.5"', 12.5), ("true", 1.0),
    ('"abc"', None), ("5", 5.0),
])
def test_string_coercion_runs_inside_a_parallel_worker(conn, raw, expect):
    """The exact path that raised 25000 before the rewrite, forced into a worker."""
    conn.execute("SET debug_parallel_query = on")
    try:
        plan = "\n".join(r[0] for r in conn.execute(
            "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT xpr.num(%s::jsonb)",
            (raw,)).fetchall())
        assert "Workers Launched: 1" in plan, "no worker launched -- the test proves nothing:\n" + plan
        assert conn.execute("SELECT xpr.num(%s::jsonb)", (raw,)).fetchone()[0] == expect
    finally:
        conn.execute("RESET debug_parallel_query")


@needs_db
@pytest.mark.parametrize("raw,state", [
    ('"1e999"', "XPR01"), ('"1e200000"', "XPR01"), ('"-1e200000"', "XPR01"),
    ('"0.' + "0" * 16384 + '"', "XPR01"), ('"1e-20000"', "22003"), ('"1e-400"', "22003"),
    ("1e400", "XPR01"),
])
def test_the_refusals_keep_their_sqlstate(conn, raw, state):
    """GIMS's fallback reads the SQLSTATE. The rewrite must refuse exactly as before."""
    import psycopg
    with pytest.raises(psycopg.Error) as exc:
        conn.execute("SELECT xpr.num(%s::jsonb)", (raw,)).fetchone()
    assert exc.value.sqlstate == state


@needs_db
def test_ecma_num_ignores_the_session_setting(conn):
    """T-52 pinned it, as T-9 pinned xpr.j. At efd 0 the old body printed 0.3."""
    conn.execute("SET extra_float_digits = 0")
    try:
        got = conn.execute("SELECT xpr.ecma_num(0.30000000000000004::float8)").fetchone()[0]
    finally:
        conn.execute("RESET extra_float_digits")
    assert got == "0.30000000000000004"
