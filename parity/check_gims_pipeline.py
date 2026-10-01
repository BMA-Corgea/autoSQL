#!/usr/bin/env python3
"""Check autoSQL against GIMS's REAL dashboard pipeline, case by case (T-46).

    python parity/check_gims_pipeline.py --gims <GIMS source tree> [--dsn <libpq DSN>]

The cases live in ``parity/gims-pipeline-vectors.json`` (format ``gims-pipeline-vectors/1``,
described in ``parity/README.md``). Every case is checked twice:

  GIMS half   the hand-authored expectation is recomputed by GIMS's OWN Python functions,
              imported from the GIMS tree given by --gims (never a copy). Any disagreement
              fails the run: a vector that misreads GIMS must never reach GIMS's parity gate.
              No database is needed.

  SQL half    the case goes through autoSQL's SHIPPING compiler (compiler/compile.py) and
              runtime (runtime/runtime.sql, installed fresh into a scratch schema) on a real
              Postgres, and the measured outcome must equal the case's recorded
              ``autosql.status`` ("agrees" or "diverges"). A recorded "agrees" that now
              diverges fails, and so does the reverse, so the file cannot go stale quietly.
              Without a DSN the SQL half does not run, and the run SAYS SO, loudly: a run
              that compared nothing must never read like a run that found nothing.

Read only toward GIMS: modules are imported with bytecode writing off, so nothing lands in the
GIMS tree. The one GIMS dependency the pipeline functions never call, ``boto3`` (imported at
module load by ``api/i_o``), is replaced by an inert stand-in, and the run names it.
Port 55433 is refused: it is a live database.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "parity" / "gims-pipeline-vectors.json"
FORMAT = "gims-pipeline-vectors/1"
KINDS = {
    "expr": {"expr", "expect"},
    "record": {"stored", "expr", "expect"},
    "sort": {"rows", "sort", "expect_ids"},
    "filter": {"rows", "filter", "expect_ids"},
}
STATUSES = ("agrees", "diverges")
# Which side must change, seen from T-37's design (SQL runs the where; Python shapes the rows, then
# applies the filters map, the sort and the limit). Every divergence carries one.
FIX_SIDES = ("adapter-shaping", "where-clause", "filters-map", "sort-pushdown", "browser", "accepted")
SOURCE_KEYS = ("autosql", "compiler_sha256", "runtime_sha256", "gims")


# ---------------------------------------------------------------------------------------
# The format (AC1)
# ---------------------------------------------------------------------------------------
def validate(doc: Dict[str, Any]) -> List[str]:
    """Every structural problem in the vector file; [] means it is well formed."""
    errs: List[str] = []
    if doc.get("format") != FORMAT:
        errs.append(f"format must be {FORMAT!r}, got {doc.get('format')!r}")
    if not isinstance(doc.get("version"), int) or isinstance(doc.get("version"), bool) or doc["version"] < 1:
        errs.append("version must be a positive integer")
    src = doc.get("source")
    if not isinstance(src, dict) or not all(isinstance(src.get(k), str) and src[k] for k in SOURCE_KEYS):
        errs.append(f"source must carry {SOURCE_KEYS}: the autoSQL commit, the sha256 of the compiler and "
                    "runtime the statuses were measured with, and the GIMS commit that confirmed the expectations")
    if not isinstance(doc.get("float_epsilon"), (int, float)) or isinstance(doc.get("float_epsilon"), bool):
        errs.append("float_epsilon must be a number")
    if not isinstance(doc.get("note"), str) or not doc["note"].strip():
        errs.append("note must be a non-empty string")
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases:
        return errs + ["cases must be a non-empty list"]
    seen = set()
    for i, c in enumerate(cases):
        where = f"case {i} ({c.get('name', '?') if isinstance(c, dict) else '?'})"
        if not isinstance(c, dict):
            errs.append(f"{where}: not an object")
            continue
        for k in ("group", "name", "kind"):
            if not isinstance(c.get(k), str) or not c[k]:
                errs.append(f"{where}: missing {k}")
        if c.get("name") in seen:
            errs.append(f"{where}: duplicate name")
        seen.add(c.get("name"))
        kind = c.get("kind")
        if kind not in KINDS:
            errs.append(f"{where}: kind must be one of {sorted(KINDS)}")
            continue
        missing = KINDS[kind] - c.keys()
        if missing:
            errs.append(f"{where}: kind {kind!r} needs {sorted(missing)}")
        if kind in ("sort", "filter"):
            rows = c.get("rows")
            if not isinstance(rows, list) or not all(isinstance(r, dict) and "id" in r for r in rows):
                errs.append(f"{where}: rows must be objects that each carry an 'id'")
            elif len({r["id"] for r in rows}) != len(rows):
                errs.append(f"{where}: row ids must be unique")
        if kind == "sort" and (not isinstance(c.get("sort"), dict)
                               or c["sort"].get("dir") not in ("asc", "desc")
                               or not isinstance(c["sort"].get("field"), str)):
            errs.append(f"{where}: sort must be {{'field': str, 'dir': 'asc'|'desc'}}")
        a = c.get("autosql")
        if not isinstance(a, dict) or a.get("status") not in STATUSES:
            errs.append(f"{where}: autosql.status must be one of {STATUSES}")
        elif a["status"] == "diverges" and not (isinstance(a.get("why"), str) and a["why"].strip()):
            errs.append(f"{where}: a divergence must say why")
        elif a["status"] == "diverges" and a.get("fix_side") not in FIX_SIDES:
            errs.append(f"{where}: a divergence must name its fix_side, one of {FIX_SIDES}")
    return errs


# ---------------------------------------------------------------------------------------
# Value comparison: GIMS's own rule (tests/test_dashboard_expr.py), applied at every depth
# (T-6 FRAMING section 4), so [True] and [1] stay distinct inside containers too.
# ---------------------------------------------------------------------------------------
def matches(actual: Any, expected: Any, eps: float) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected or (actual == expected and type(actual) is type(expected))
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=eps)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(matches(a, e, eps) for a, e in zip(actual, expected))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(matches(actual[k], expected[k], eps) for k in expected)
    return actual == expected


# ---------------------------------------------------------------------------------------
# GIMS, imported from its own tree (the GIMS half)
# ---------------------------------------------------------------------------------------
class _Inert(types.ModuleType):
    """Stand-in for a module GIMS imports at load time but the pipeline functions never call.
    Any attribute is another inert stand-in; calling one returns an inert stand-in."""

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Inert(f"{self.__name__}.{name}")

    def __call__(self, *args, **kwargs):
        return _Inert(f"{self.__name__}()")


STUBBED = ("boto3",)


def load_gims(gims: Path) -> Dict[str, Any]:
    if not (gims / "core" / "dashboard" / "expr.py").is_file():
        raise SystemExit(f"--gims {gims}: not a GIMS source tree (no core/dashboard/expr.py)")
    for name in STUBBED:
        sys.modules.setdefault(name, _Inert(name))
    sys.path.insert(0, str(gims))
    mods = {
        "expr": importlib.import_module("core.dashboard.expr"),
        "sources": importlib.import_module("api.dashboard.sources"),
        "nouns": importlib.import_module("api.iostore.nouns"),
    }
    return mods


# ---------------------------------------------------------------------------------------
# autoSQL's shipping compiler and runtime, on a real Postgres (the SQL half)
# ---------------------------------------------------------------------------------------
def load_compiler():
    spec = importlib.util.spec_from_file_location("autosql_compile", ROOT / "compiler" / "compile.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autosql_compile"] = mod
    spec.loader.exec_module(mod)
    return mod


class Sql:
    """One connection with the CURRENT runtime/runtime.sql installed fresh, and the session
    pinned the way the runtime requires (extra_float_digits = 1)."""

    def __init__(self, dsn: str):
        if "port=55433" in dsn.replace(" ", "") or ":55433" in dsn:
            raise SystemExit("refusing port 55433: it is a live database")
        import psycopg
        self.psycopg = psycopg
        self.cx = psycopg.connect(dsn, autocommit=True)
        self.cx.execute("DROP SCHEMA IF EXISTS xpr CASCADE")
        self.cx.execute((ROOT / "runtime" / "runtime.sql").read_text())
        self.cx.execute("SET extra_float_digits = 1")
        self.functions = self.cx.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'xpr'").fetchone()[0]

    def value(self, sql: str, params: Dict[str, Any], record: Any, ctx: Dict[str, Any]) -> Tuple[str, Any]:
        """('value', v) | ('sql-null', None) | ('raised', 'SQLSTATE message')."""
        p = dict(params, rec=json.dumps(record), ctx=json.dumps(ctx or {}))
        q = ("SELECT (v IS NULL), jsonb_typeof(v), v::text FROM (SELECT " + sql +
             " AS v FROM (SELECT (%(rec)s)::jsonb AS data) t) q")
        try:
            is_null, jt, vt = self.cx.execute(q, p).fetchone()
        except self.psycopg.Error as e:
            return "raised", f"{e.sqlstate} {str(e).strip().splitlines()[0]}"
        if is_null:
            return "sql-null", None
        return "value", (None if jt == "null" else json.loads(vt))

    def ids(self, select_sql: str, params: Dict[str, Any], rows: List[Dict[str, Any]],
            ctx: Dict[str, Any]) -> Tuple[str, Any]:
        """Run a statement over the rows as a VALUES table r(id, data); ('ids', [...]) or ('raised', ...)."""
        p = dict(params, rows=json.dumps(rows), ctx=json.dumps(ctx or {}))
        q = ("WITH r AS (SELECT e->>'id' AS id, e AS data, o AS ord "
             "FROM jsonb_array_elements((%(rows)s)::jsonb) WITH ORDINALITY AS x(e, o)) " + select_sql)
        try:
            return "ids", [row[0] for row in self.cx.execute(q, p).fetchall()]
        except self.psycopg.Error as e:
            return "raised", f"{e.sqlstate} {str(e).strip().splitlines()[0]}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gims", default=os.environ.get("GIMS_SRC"), help="a GIMS source tree (or GIMS_SRC)")
    ap.add_argument("--dsn", default=os.environ.get("AUTOSQL_PARITY_DSN"),
                    help="a scratch Postgres 16 for the SQL half (or AUTOSQL_PARITY_DSN)")
    ap.add_argument("--vectors", default=str(VECTORS))
    ap.add_argument("--json-out", help="write every case's outcome here")
    args = ap.parse_args(argv)

    doc = json.loads(Path(args.vectors).read_text())
    errs = validate(doc)
    if errs:
        print("FORMAT: the vector file is malformed:")
        for e in errs:
            print("  -", e)
        return 2
    print(f"format {doc['format']} v{doc['version']}: {len(doc['cases'])} cases, source {doc['source']}")
    if not args.gims:
        print("NO GIMS TREE: pass --gims <path> (or GIMS_SRC); nothing was checked")
        return 2
    return run(doc, Path(args.gims).resolve(), args.dsn, args.json_out)


# ---------------------------------------------------------------------------------------
# The GIMS half: GIMS's real resolve(), end to end, over the case's stored rows
# ---------------------------------------------------------------------------------------
class GimsPipeline:
    """Drives GIMS's own ``api.dashboard.sources.resolve`` for a noun source.

    Only the record store is replaced: ``get_noun_items`` asks the unified instances store for
    the collection's rows, and here that store answers with the case's ``stored`` rows. So the
    rows still pass through GIMS's own ``_normalize_row`` (the key copies), the ``_noun_type``
    tag, derive, filters, where, sort and limit, exactly as on a dashboard. Rows are handed
    over in jsonb's key order (shorter keys first, then bytewise), because in Postgres mode
    that is the order GIMS receives them in, and ``_normalize_row``'s setdefault makes the
    first of two colliding keys win.
    """

    NOUN = "parity_case"

    def __init__(self, gims: Path):
        self.m = load_gims(gims)
        self.rows: List[Dict[str, Any]] = []
        import core.storage.factory as factory
        outer = self

        class _Store:
            def list_records(self, collection):
                return [dict(r) for r in outer.rows]

        factory.get_record_store = lambda project_path: _Store()
        factory.collection_for_noun = lambda noun: f"noun:{noun}"
        # get_noun_items asks this before reading the store, and the answer only steers the
        # fallbacks that a non-empty store never reaches. Pinned so the run reads no config.
        self.m["nouns"]._get_objects_db_target = lambda project_path: ("sqlite", "/nonexistent/objects.db")
        self.project = Path("/nonexistent/parity-project")

    @staticmethod
    def jsonb_order(row: Dict[str, Any]) -> Dict[str, Any]:
        return {k: row[k] for k in sorted(row, key=lambda k: (len(k.encode()), k.encode()))}

    def resolve(self, rows: List[Dict[str, Any]], spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        self.rows = [self.jsonb_order(r) for r in rows]
        source = {"type": "noun", "noun_type": self.NOUN, **spec}
        return self.m["sources"].resolve(source, self.project, ctx)


def gims_answer(g: GimsPipeline, c: Dict[str, Any]) -> Any:
    ctx = c.get("context", {})
    kind = c["kind"]
    if kind == "expr":
        return g.m["expr"].evaluate_str(c["expr"], c.get("record", {}), ctx)
    if kind == "record":
        out = g.resolve([c["stored"]], {"derive": {"__value": c["expr"]}}, ctx)["records"]
        return out[0]["__value"] if out else "NO ROW"
    if kind == "sort":
        return [r.get("id") for r in g.resolve(c["rows"], {"sort": c["sort"]}, ctx)["records"]]
    if kind == "filter":
        spec = {"where": c["filter"]} if isinstance(c["filter"], str) else {"filters": c["filter"]}
        return [r.get("id") for r in g.resolve(c["rows"], spec, ctx)["records"]]
    raise ValueError(kind)


# ---------------------------------------------------------------------------------------
# The SQL half: what autoSQL computes for the same case
# ---------------------------------------------------------------------------------------
def sort_rank_sql(v: str, direction: str) -> str:
    """GIMS's _sort_key as SQL: autoSQL's candidate translation, term for term as in
    spikes/T-1/proto/bench.py (sort_sql) and spikes/T-4/bench_t4.py (_sort_sql_dir): rank
    (bool 0 < number 1 < string 2 < other 3 < null 4), then the number, then the string."""
    d = " DESC" if direction == "desc" else ""
    ty = f"jsonb_typeof({v})"
    r1 = (f"(CASE WHEN {v} IS NULL OR {ty}='null' THEN 4 WHEN {ty}='boolean' THEN 0 "
          f"WHEN {ty}='number' THEN 1 WHEN {ty}='string' THEN 2 ELSE 3 END)")
    r2 = (f"(CASE WHEN {ty}='boolean' THEN (CASE WHEN {v}='true'::jsonb THEN 1.0 ELSE 0.0 END) "
          f"WHEN {ty}='number' THEN xpr.f8({v}) ELSE 0.0 END)")
    r3 = f"(CASE WHEN {ty}='string' THEN ({v} #>> '{{}}') ELSE '' END) COLLATE \"C\""
    return f"{r1}{d}, {r2}{d}, {r3}{d}"


def sql_answer(db: "Sql", comp, parse: Callable, c: Dict[str, Any]) -> Tuple[str, Any]:
    """('value'|'ids', answer) or ('raised'|'uncompilable'|'sql-null', detail)."""
    ctx = c.get("context", {})
    kind = c["kind"]
    try:
        if kind in ("expr", "record"):
            compiled = comp.compile_ast(parse(c["expr"]), column="data")
            return db.value(compiled.sql, compiled.params, c.get("record", {}) if kind == "expr" else c["stored"], ctx)
        if kind == "sort":
            # The field as the adapter would read it from instances.data: an exact key.
            field = c["sort"]["field"]
            q = (f"SELECT id FROM r ORDER BY {sort_rank_sql('(data -> %(sort_field)s)', c['sort']['dir'])}, ord")
            return db.ids(q, {"sort_field": field}, c["rows"], ctx)
        if kind == "filter":
            if not isinstance(c["filter"], str):
                return "uncompilable", "a filters object (exact-equality map) has no SQL translation in autoSQL"
            compiled = comp.compile_ast(parse(c["filter"]), column="data")
            return db.ids(f"SELECT id FROM r WHERE xpr.truthy({compiled.sql}) ORDER BY ord", compiled.params, c["rows"], ctx)
    except comp.Uncompilable as e:
        return "uncompilable", e.reason
    raise ValueError(kind)


def run(doc: Dict[str, Any], gims: Path, dsn: Optional[str], json_out: Optional[str]) -> int:
    eps = float(doc["float_epsilon"])
    g = GimsPipeline(gims)
    print(f"GIMS tree {gims} (stand-ins for modules the pipeline never calls: {', '.join(STUBBED)})")
    import hashlib
    for key, rel in (("compiler_sha256", "compiler/compile.py"), ("runtime_sha256", "runtime/runtime.sql")):
        now = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        if now != doc["source"][key]:
            print(f"NOTE: {rel} is not the one the statuses were recorded with "
                  f"({now[:16]} here, {doc['source'][key][:16]} in source). The SQL half re-measures every case.")
    db = comp = None
    if dsn:
        db, comp = Sql(dsn), load_compiler()
        print(f"SQL: runtime/runtime.sql installed fresh ({db.functions} xpr functions); compiler/compile.py")
    outcomes, gims_bad, stale = [], 0, 0
    for c in doc["cases"]:
        o: Dict[str, Any] = {"name": c["name"], "kind": c["kind"], "group": c["group"]}
        want = c["expect"] if "expect" in c else c["expect_ids"]
        try:
            got = gims_answer(g, c)
            o["gims"] = got
            o["gims_ok"] = matches(got, want, eps)
        except Exception as e:  # GIMS raising IS a finding: its pipeline claims to be total
            o["gims"], o["gims_ok"] = f"RAISED {type(e).__name__}: {e}", False
        if not o["gims_ok"]:
            gims_bad += 1
            print(f"GIMS DISAGREES  {c['group']}/{c['name']}: GIMS gives {o['gims']!r}, the vector expects {want!r}")
        if db is not None:
            how, ans = sql_answer(db, comp, g.m["expr"].parse, c)
            o["sql"] = [how, ans]
            # SQL NULL and jsonb null both reach the adapter's Python as None, and xpr.truthy
            # treats both as false, so for the pipeline they are the same blank. The outcome
            # file keeps which one it was ("sql-null"), for the representation record.
            agree = (how in ("value", "ids") and matches(ans, want, eps)) or (how == "sql-null" and want is None)
            measured = "agrees" if agree else "diverges"
            o["sql_status"] = measured
            if measured != c["autosql"]["status"]:
                stale += 1
                print(f"SQL STATUS STALE  {c['group']}/{c['name']}: recorded {c['autosql']['status']!r}, "
                      f"measured {measured!r} ({how}: {ans!r})")
        outcomes.append(o)
    n = len(doc["cases"])
    div = sum(1 for c in doc["cases"] if c["autosql"]["status"] == "diverges")
    print()
    print(f"GIMS half: {n - gims_bad}/{n} expectations confirmed by GIMS's own pipeline")
    if db is None:
        print("=" * 78)
        print("SQL half: DID NOT RUN. No DSN (--dsn or AUTOSQL_PARITY_DSN), so autoSQL was")
        print("  compared against NOTHING. The recorded autosql statuses are unverified by this")
        print("  run. Run it against a scratch Postgres 16 (never port 55433).")
        print("=" * 78)
    else:
        print(f"SQL half: {n - stale}/{n} recorded statuses confirmed "
              f"({n - div} agree, {div} diverge, as recorded)")
    if json_out:
        Path(json_out).write_text(json.dumps(outcomes, indent=1, default=str) + "\n")
    return 1 if (gims_bad or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
