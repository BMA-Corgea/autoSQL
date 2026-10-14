"""runtime/this_runtime.py — install THIS tree's runtime into a throwaway database (T-98).

A database's `xpr` functions are whatever was last installed there: the shared demo database
carries what its last `./run-demo up` installed, which need not be any seat's runtime.sql
(measured 2026-10-13: its xpr.truthy predates T-37 M1). A test that measures the SQL engine
against GIMS's evaluator must measure the runtime it is testing, so it installs this tree's
generated runtime/runtime.sql first, and confirms every function in it is installed as written.

Refuses ports 55433 (a live database) and 55440 (the shared demo database).
"""
from __future__ import annotations

from pathlib import Path

RUNTIME_SQL = Path(__file__).resolve().parent / "runtime.sql"
_REFUSED = {55433: "a live database", 55440: "the shared demo database, which other seats read"}

_DEFS = """SELECT p.oid::regprocedure::text, pg_get_functiondef(p.oid) FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'xpr' ORDER BY 1"""


def install(conn) -> int:
    """Drop `xpr` and install runtime/runtime.sql on an autocommit connection; returns how many
    xpr functions are now installed."""
    port = int(conn.info.port)
    if port in _REFUSED:
        raise SystemExit(f"refusing to install into port {port}: {_REFUSED[port]}")
    sql = RUNTIME_SQL.read_text()
    conn.execute("DROP SCHEMA IF EXISTS xpr CASCADE")
    conn.execute(sql)
    names = [r[0] for r in conn.execute(_DEFS).fetchall()]
    want = sql.count("CREATE OR REPLACE FUNCTION xpr.")
    if len(names) != want:
        raise RuntimeError(f"runtime.sql creates {want} xpr functions; {len(names)} are installed")
    return len(names)
