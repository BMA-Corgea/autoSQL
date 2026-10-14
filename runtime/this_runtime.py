"""runtime/this_runtime.py — install THIS tree's runtime into a throwaway database (T-98).

A database's `xpr` functions are whatever was last installed there: the shared demo database
carries what its last `./run-demo up` installed, which need not be any seat's runtime.sql
(measured 2026-10-13: its xpr.truthy predates T-37 M1). A test that measures the SQL engine
against GIMS's evaluator must measure the runtime it is testing, so it installs this tree's
generated runtime/runtime.sql first, and confirms every function in it is installed as written.

Refuses ports 55433 (a live database) and 55440 (the shared demo database).
"""
from __future__ import annotations

import re
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


# ── does a database run a given runtime? ─────────────────────────────────────
#
# Postgres keeps each function's body exactly as written (pg_proc.prosrc), so whether a database's
# `xpr` is a runtime.sql is one query: every function the file declares, by name, with its body.
# Cheap, read-only, needs no install — the demo suite asks it at its start (T-98).

_DECL = re.compile(r"CREATE OR REPLACE FUNCTION xpr\.([A-Za-z_0-9]+)\(.*?\bAS (\$[A-Za-z_0-9]*\$)(.*?)\2;", re.S)
_INSTALLED = """SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'xpr'"""


def declared(sql: str) -> dict:
    """name → [bodies] of every xpr function a runtime.sql declares."""
    out: dict = {}
    for name, _tag, body in _DECL.findall(sql):
        out.setdefault(name, []).append(body)
    return {k: sorted(v) for k, v in out.items()}


def compare(conn, sql: str) -> dict:
    """``{"state": "same" | "differs", "functions", "differ", "missing", "extra"}`` for the
    database on ``conn`` against the runtime ``sql``; read-only."""
    want = declared(sql)
    have: dict = {}
    for name, body in conn.execute(_INSTALLED).fetchall():
        have.setdefault(name, []).append(body)
    have = {k: sorted(v) for k, v in have.items()}
    differ = sorted(f"xpr.{k}" for k in want.keys() & have.keys() if want[k] != have[k])
    missing = sorted(f"xpr.{k}" for k in want.keys() - have.keys())
    extra = sorted(f"xpr.{k}" for k in have.keys() - want.keys())
    return {"state": "differs" if differ or missing or extra else "same",
            "functions": sum(len(v) for v in want.values()),
            "differ": differ, "missing": missing, "extra": extra}


def words(result: dict, path: str) -> str:
    """One line for a person: what differs between a database's runtime and ``path``."""
    if result["state"] == "same":
        return f"the database runs {path} ({result['functions']} functions, as written)"
    parts = [f"{label}: {', '.join(result[key])}" for key, label in
             (("differ", "differs"), ("missing", "missing"), ("extra", "extra")) if result[key]]
    return f"the database does NOT run {path} — " + "; ".join(parts)
