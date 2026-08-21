"""T-1 spike, MEASUREMENT seat (FRAMING.md section 4, finding #4) -- THROWAWAY harness.

Measures the representative dashboard widget (spikes/T-1/recon/baseline.md section 3.2)
on BOTH paths over the SAME corpus:

  Path A (today)     : acquire every candidate row into Python, truncate at MAX_SCAN,
                       then derive/filter/sort/limit with core.dashboard.expr --
                       api/dashboard/sources.py:330-357, called through the REAL module.
  Path B (pushdown)  : compile the same expressions with spikes/T-1/proto/compile.py and
                       run one statement in Postgres.

Nothing here is a library.  Per FRAMING.md section 3 the prototype is throwaway by contract.
"""
from __future__ import annotations
import os

import json, math, os, resource, statistics, sys, time
from typing import Any, Dict, List, Tuple

sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")

import psycopg2
from core.dashboard import expr as EXPR
from api.dashboard import sources as SRC          # the REAL in-memory pipeline
import compile as CC                              # the throwaway AST -> SQL compiler

# Connection string for the spike's scratch database.
# Set AUTOSQL_SPIKE_DSN to reproduce, e.g.
#   export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=<throwaway> dbname=autosql_spike"
# The password is deliberately NOT in this repo: the same role owns the live glp_strong
# database on that container. Scrubbed 2026-08-21 before first commit.
DSN = os.environ.get("AUTOSQL_SPIKE_DSN")
if not DSN:
    raise SystemExit(
        "AUTOSQL_SPIKE_DSN is not set, and there is no default. The only default that ever\n"
        "  existed pointed at port 55433 - the live glp-strong-db container, which holds real\n"
        "  data owned by the same role. Point it at a THROWAWAY Postgres instead.\n"
        "  See spikes/T-1/proto/REGENERATE-CORPUS.md."
    )
if "port=55433" in DSN:
    raise SystemExit(
        "Refusing to run against port 55433 - that is the live glp-strong-db container.\n"
        "  Use a throwaway one. See spikes/T-1/proto/REGENERATE-CORPUS.md."
    )
COLLECTION = "noun:Sample"

# ---- the representative widget (recon/baseline.md 3.2; every clause attested there) ----
WIDGET = {
    "type": "noun", "noun_type": "Sample",
    "filters": {"status": "open"},
    "derive": {"days_left": "days_between(today(), $.due_date)"},
    "where": "$.days_left != null and $.days_left < 7",
    "sort": {"field": "days_left", "dir": "asc"},
    "limit": 50,
}
CTX = {"now": "2026-08-19T12:00:00Z"}     # shape of routes.py:177 _server_now(), pinned

_EPS = 1e-9   # tests/fixtures/expr_vectors.json float_epsilon


# ---------------------------------------------------------------------------------------
# comparison rule -- mirrored from GIMS-Project/tests/test_dashboard_expr.py:20-25
# ---------------------------------------------------------------------------------------
def matches(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=0, abs_tol=_EPS)
    return actual == expected


def rows_match(a: List[dict], b: List[dict]) -> Tuple[bool, str]:
    if len(a) != len(b):
        return False, f"length {len(a)} vs {len(b)}"
    for i, (ra, rb) in enumerate(zip(a, b)):
        if set(ra.keys()) != set(rb.keys()):
            return False, f"row {i} key sets differ: {sorted(set(ra) ^ set(rb))[:5]}"
        for k in ra:
            if not matches(ra[k], rb[k]):
                return False, f"row {i} field {k!r}: {ra[k]!r} vs {rb[k]!r}"
    return True, "identical"


# ---------------------------------------------------------------------------------------
# AST substitution: inline a derive into an expression that reads it back as $.name.
# expr's _apply_derive writes row[name] then later clauses read $.name (sources.py:146),
# so replacing the read with the producing AST is semantics-preserving.
# ---------------------------------------------------------------------------------------
def subst(node, name, repl):
    if not isinstance(node, tuple) or not node:
        return node
    if node[0] == "field":
        return repl if node[1] == [("key", name)] else node
    out = [node[0]]
    for part in node[1:]:
        if isinstance(part, tuple):
            out.append(subst(part, name, repl))
        elif isinstance(part, list):
            out.append([subst(x, name, repl) for x in part])
        else:
            out.append(part)
    return tuple(out)


# ---------------------------------------------------------------------------------------
# sort compilation -- mirrors sources.py:99-116 _sort_key's 3-tuple exactly.
# rank 3 ("other": list/dict -> str(value)) is NOT compilable (Python repr); the harness
# asserts the corpus never produces it rather than pretending it is handled.
# ---------------------------------------------------------------------------------------
def sort_sql(v: str) -> str:
    ty = f"jsonb_typeof({v})"
    r1 = (f"(CASE WHEN {v} IS NULL OR {ty}='null' THEN 4 WHEN {ty}='boolean' THEN 0 "
          f"WHEN {ty}='number' THEN 1 WHEN {ty}='string' THEN 2 ELSE 3 END)")
    r2 = (f"(CASE WHEN {ty}='boolean' THEN (CASE WHEN {v}='true'::jsonb THEN 1.0 ELSE 0.0 END) "
          f"WHEN {ty}='number' THEN xpr.f8({v}) ELSE 0.0 END)")
    r3 = f"(CASE WHEN {ty}='string' THEN ({v} #>> '{{}}') ELSE '' END) COLLATE \"C\""
    return f"{r1}, {r2}, {r3}"


# ---------------------------------------------------------------------------------------
# PATH A -- the current in-memory path, phase by phase.
# Acquisition mirrors PgRecordStore.list_records (gims-ledger api/storage_aws.py:728-731):
#     SELECT data FROM <table> WHERE collection = %s
# split into wire-fetch and JSON-deserialize so the RAG profile's load/use split
# (core/storage/sql.py:246) can be drawn for this path too.
# ---------------------------------------------------------------------------------------
def path_a(conn, table: str, *, split: bool = True) -> Dict[str, Any]:
    t: Dict[str, float] = {}
    cur = conn.cursor()

    t0 = time.perf_counter()
    cur.execute(f"SELECT data::text FROM {table} WHERE collection = %s", (COLLECTION,))
    texts = [r[0] for r in cur.fetchall()]
    t["fetch_wire_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    raw = [json.loads(s) for s in texts]
    t["deserialize_ms"] = (time.perf_counter() - t0) * 1000
    del texts

    t["acquire_ms"] = t["fetch_wire_ms"] + t["deserialize_ms"]

    # sources.py:348-351
    t0 = time.perf_counter()
    truncated = len(raw) > SRC.MAX_SCAN
    rows = raw[:SRC.MAX_SCAN] if truncated else raw
    t["truncate_ms"] = (time.perf_counter() - t0) * 1000
    scanned_in, scanned_out = len(raw), len(rows)

    t0 = time.perf_counter()                                        # sources.py:353
    rows = SRC._apply_derive(rows, WIDGET["derive"], CTX)
    t["derive_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()                                        # sources.py:354
    rows = SRC._filter_rows(rows, WIDGET["filters"], WIDGET["where"], CTX)
    t["filter_ms"] = (time.perf_counter() - t0) * 1000
    kept = len(rows)

    t0 = time.perf_counter()                                        # sources.py:355
    rows = SRC._apply_sort(rows, WIDGET["sort"])
    t["sort_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()                                        # sources.py:356
    rows = SRC._apply_limit(rows, WIDGET["limit"])
    t["limit_ms"] = (time.perf_counter() - t0) * 1000

    t["process_ms"] = (t["truncate_ms"] + t["derive_ms"] + t["filter_ms"]
                       + t["sort_ms"] + t["limit_ms"])
    t["total_ms"] = t["acquire_ms"] + t["process_ms"]
    return {"t": t, "rows": rows, "truncated": truncated,
            "rows_acquired": scanned_in, "rows_scanned": scanned_out, "rows_kept": kept}


def path_a_driver(conn, table: str) -> float:
    """The acquisition exactly as PgRecordStore.list_records does it (driver deserializes
    jsonb itself) -- a control on the ::text split above."""
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(f"SELECT data FROM {table} WHERE collection = %s", (COLLECTION,))
    rows = [r[0] for r in cur.fetchall()]
    ms = (time.perf_counter() - t0) * 1000
    n = len(rows)
    del rows
    return ms, n


# ---------------------------------------------------------------------------------------
# PATH B -- compile the widget and run it as one statement.
# ---------------------------------------------------------------------------------------
DERIVE_NAME = "days_left"
# Deterministic tiebreak, used ONLY by the identity arm: Python's sorted() is stable and
# Postgres' sort is not, so without it a tie spanning the LIMIT boundary makes row-for-row
# comparison meaningless.  Timing runs use the widget's own ORDER BY, untouched.
TIE = ", data->>'id' COLLATE \"C\""
TIE_D = ", d.data->>'id' COLLATE \"C\""


def build_b(variant: str, table: str, tie: bool = False):
    """Returns (sql, params).  Variants:
       B1 faithful : materialise data||{days_left:...} first, exactly as sources.py:146
                     mutates the row, then filter/sort over the augmented document.
       B2 inlined  : substitute the derive AST into where/sort; build the augmented
                     document only for surviving rows.
       B3 inlined+containment : B2 with the `status` equality expressed as `data @> ...`
                     so migrations/pg/0002's GIN index is usable.
    """
    d_ast = EXPR.parse(WIDGET["derive"][DERIVE_NAME])
    w_ast = EXPR.parse(WIDGET["where"])
    params: Dict[str, Any] = {"coll": COLLECTION, "ctx": json.dumps(CTX)}

    def take(c: CC.Compiled, tag: str) -> str:
        sql = c.sql
        for k, v in c.params.items():
            params[f"{tag}_{k}"] = v
            sql = sql.replace(f"%({k})s", f"%({tag}_{k})s")
        return sql

    if variant == "B1":
        d_sql = take(CC.compile_ast(d_ast, column="data"), "d")
        aug = f"(data || jsonb_build_object('{DERIVE_NAME}', {d_sql}))"
        w_sql = take(CC.compile_ast(w_ast, column="d.data"), "w")
        v = f"nullif(d.data -> '{DERIVE_NAME}', 'null'::jsonb)"
        params["fstatus"] = json.dumps(WIDGET["filters"]["status"])
        sql = (f"SELECT d.data FROM (SELECT {aug} AS data FROM {table} "
               f"WHERE collection = %(coll)s) d "
               f"WHERE (d.data -> 'status') = %(fstatus)s::jsonb AND xpr.truthy({w_sql}) "
               f"ORDER BY {sort_sql(v)}{TIE_D if tie else ''} "
               f"LIMIT {int(WIDGET['limit'])}")
        return sql, params

    # B2 / B3: inline the derive
    w_in = subst(w_ast, DERIVE_NAME, d_ast)
    w_sql = take(CC.compile_ast(w_in, column="data"), "w")
    d_sql_sort = take(CC.compile_ast(d_ast, column="data"), "s")
    d_sql_out = take(CC.compile_ast(d_ast, column="data"), "o")
    aug = f"(data || jsonb_build_object('{DERIVE_NAME}', {d_sql_out}))"
    if variant == "B3":
        params["fcontain"] = json.dumps({"status": WIDGET["filters"]["status"]})
        filt = "data @> %(fcontain)s::jsonb"
    else:
        params["fstatus"] = json.dumps(WIDGET["filters"]["status"])
        filt = "(data -> 'status') = %(fstatus)s::jsonb"
    sql = (f"SELECT {aug} FROM {table} WHERE collection = %(coll)s AND {filt} "
           f"AND xpr.truthy({w_sql}) ORDER BY {sort_sql(d_sql_sort)}"
           f"{TIE if tie else ''} LIMIT {int(WIDGET['limit'])}")
    return sql, params


def path_b(conn, table: str, variant: str, tie: bool = False) -> Dict[str, Any]:
    sql, params = build_b(variant, table, tie)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    out = [r[0] for r in cur.fetchall()]
    ms = (time.perf_counter() - t0) * 1000
    return {"t": {"total_ms": ms}, "rows": out, "sql": sql, "params": params}


# ---------------------------------------------------------------------------------------
# Ground truth + the cost of MAX_SCAN, measured rather than argued.
# ---------------------------------------------------------------------------------------
def ground_truth(conn, table: str, limit: int | None) -> List[dict]:
    sql, params = build_b("B2", table, tie=True)
    if limit is None:
        sql = sql.rsplit(" LIMIT ", 1)[0]
    cur = conn.cursor()
    cur.execute(sql, params)
    return [r[0] for r in cur.fetchall()]


def qualifying_count(conn, table: str) -> int:
    sql, params = build_b("B2", table)
    body = sql.split(" ORDER BY ")[0]
    body = "SELECT count(*) FROM" + body.split(" FROM", 1)[1]
    cur = conn.cursor()
    cur.execute(body, params)
    return cur.fetchone()[0]


def scan_floor(conn, table: str) -> Dict[str, float]:
    """The SQL-side floor: touch every row of the collection and evaluate nothing
    (count(*)), then the same scan WITH the compiled predicate.  The difference is what
    the compiled expression itself costs in Postgres -- the analogue of the RAG profile's
    load-vs-cosine split (core/storage/sql.py:246)."""
    cur = conn.cursor()
    out = {}
    t0 = time.perf_counter()
    cur.execute(f"SELECT count(*) FROM {table} WHERE collection = %s", (COLLECTION,))
    cur.fetchall()
    out["count_only_ms"] = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    cur.execute(f"SELECT sum(octet_length(data::text)) FROM {table} WHERE collection = %s",
                (COLLECTION,))
    out["payload_bytes"] = int(cur.fetchone()[0])
    out["payload_scan_ms"] = (time.perf_counter() - t0) * 1000
    return out


def explain(conn, table: str, variant: str) -> str:
    sql, params = build_b(variant, table)
    cur = conn.cursor()
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING ON) " + sql, params)
    return "\n".join(r[0] for r in cur.fetchall())


def reps(fn, n: int) -> Dict[str, Any]:
    vals: List[Dict[str, float]] = []
    last = None
    for _ in range(n):
        last = fn()
        vals.append(last["t"])
    keys = vals[0].keys()
    agg = {}
    for k in keys:
        xs = [v[k] for v in vals]
        agg[k] = {"median": round(statistics.median(xs), 2), "min": round(min(xs), 2),
                  "max": round(max(xs), 2),
                  "stdev": round(statistics.stdev(xs), 2) if len(xs) > 1 else 0.0,
                  "n": len(xs)}
    return {"agg": agg, "last": last, "raw": vals}


# ---------------------------------------------------------------------------------------
# The cost of the fallback machinery (FRAMING.md section 5: a fallback must be REPORTED).
# ---------------------------------------------------------------------------------------
UNCOMPILABLE_WHERE = "$.days_left != null and $.days_left < 1e400"


def fallback_costs(n: int = 2000) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    def timeit(fn):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t0) / n * 1000

    d_src = WIDGET["derive"][DERIVE_NAME]
    w_src = WIDGET["where"]
    out["parse_derive_ms"] = timeit(lambda: EXPR.parse(d_src))
    out["parse_where_ms"] = timeit(lambda: EXPR.parse(w_src))
    d_ast, w_ast = EXPR.parse(d_src), EXPR.parse(w_src)
    out["compile_derive_ms"] = timeit(lambda: CC.compile_ast(d_ast))
    out["compile_where_ms"] = timeit(lambda: CC.compile_ast(w_ast))

    bad_ast = EXPR.parse(UNCOMPILABLE_WHERE)

    def attempt():
        try:
            CC.compile_ast(bad_ast)
        except CC.Uncompilable:
            return True
        raise AssertionError("expected Uncompilable")
    out["detect_uncompilable_ms"] = timeit(attempt)
    out["detected"] = attempt()
    try:
        CC.compile_ast(bad_ast)
    except CC.Uncompilable as e:
        out["reason"] = e.reason
    out["plan_ms"] = out["parse_derive_ms"] + out["parse_where_ms"] + \
        out["compile_derive_ms"] + out["compile_where_ms"]
    return out


# ---------------------------------------------------------------------------------------
# Silent-divergence probe the SIZE arms cannot reach: sources._field_value (sources.py:67-85)
# resolves `filters`/`sort` keys tolerantly (exact -> case/space/underscore -> dotted path).
# compile.py models expressions only, so a compiled `filters` clause is EXACT-key.
# ---------------------------------------------------------------------------------------
TOLERANT_TABLE = "measure_instances_tolerant"


def tolerant_key_probe(conn) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TOLERANT_TABLE}")
    cur.execute(f"CREATE TABLE {TOLERANT_TABLE} (collection TEXT NOT NULL, key TEXT NOT NULL,"
                f" data JSONB NOT NULL, PRIMARY KEY (collection, key))")
    recs = [
        {"id": "T-1", "status": "open", "due_date": "2026-08-20", "priority": 1},
        {"id": "T-2", "Status": "open", "due_date": "2026-08-21", "priority": 1},
        {"id": "T-3", "status ": "open", "due_date": "2026-08-22", "priority": 1},
    ]
    for r in recs:
        cur.execute(f"INSERT INTO {TOLERANT_TABLE} VALUES (%s, %s, %s::jsonb)",
                    (COLLECTION, r["id"], json.dumps(r)))
    conn.commit()
    a = path_a(conn, TOLERANT_TABLE)
    ids_a = sorted(r["id"] for r in a["rows"])
    b = path_b(conn, TOLERANT_TABLE, "B2", tie=True)
    ids_b = sorted(r["id"] for r in b["rows"])
    return {"records": recs, "path_a_ids": ids_a, "path_b_ids": ids_b,
            "agree": ids_a == ids_b,
            "rows_only_python_finds": sorted(set(ids_a) - set(ids_b)),
            "rows_only_sql_finds": sorted(set(ids_b) - set(ids_a))}


# ---------------------------------------------------------------------------------------
# Answer quality at and beyond MAX_SCAN.  Path A stops being CORRECT at 20,000 rows
# (sources.py:348-351), not merely slow -- so quality is measured, not asserted.
# ---------------------------------------------------------------------------------------
def path_a_tiebreak(conn, table: str) -> Dict[str, Any]:
    """Path A, run exactly as sources.resolve does EXCEPT that the sort carries a
    deterministic tiebreak on $.id.  Used only for identity/quality comparison: Python's
    sorted() is stable and Postgres' sort is not, so ties spanning the LIMIT boundary would
    otherwise make a row-for-row comparison meaningless.  Never used for timing."""
    assert str(WIDGET["sort"].get("dir", "asc")).lower() == "asc"
    cur = conn.cursor()
    cur.execute(f"SELECT data FROM {table} WHERE collection = %s", (COLLECTION,))
    raw = [r[0] for r in cur.fetchall()]
    truncated = len(raw) > SRC.MAX_SCAN
    rows = raw[:SRC.MAX_SCAN] if truncated else raw
    rows = SRC._apply_derive(rows, WIDGET["derive"], CTX)
    rows = SRC._filter_rows(rows, WIDGET["filters"], WIDGET["where"], CTX)
    field = str(WIDGET["sort"]["field"])
    rows = sorted(rows, key=lambda r: (SRC._sort_key(SRC._field_value(r, field)),
                                       str(SRC._field_value(r, "id"))))
    kept = len(rows)
    rows = SRC._apply_limit(rows, WIDGET["limit"])
    return {"rows": rows, "truncated": truncated, "rows_acquired": len(raw),
            "rows_scanned": (SRC.MAX_SCAN if truncated else len(raw)), "rows_kept": kept}


def answer_quality(conn, table: str, truth: List[dict]) -> Dict[str, Any]:
    a = path_a_tiebreak(conn, table)
    ids_a = [r["id"] for r in a["rows"]]
    ids_t = [r["id"] for r in truth]
    overlap = len(set(ids_a) & set(ids_t))
    q_all = qualifying_count(conn, table)
    # how many rows qualify inside the capped window Path A actually sees
    cur = conn.cursor()
    q_seen = None
    if a["truncated"]:
        q_seen = a["rows_kept"]
    best_a = a["rows"][0]["days_left"] if a["rows"] else None
    best_t = truth[0]["days_left"] if truth else None
    return {
        "truncated": a["truncated"],
        "rows_acquired": a["rows_acquired"], "rows_scanned_by_python": a["rows_scanned"],
        "qualifying_rows_in_whole_table": q_all,
        "qualifying_rows_inside_cap": q_seen if q_seen is not None else a["rows_kept"],
        "qualifying_rows_never_examined": q_all - (q_seen if q_seen is not None else a["rows_kept"]),
        "answer_len_path_a": len(ids_a), "answer_len_truth": len(ids_t),
        "top50_overlap": overlap,
        "top50_recall": round(overlap / len(ids_t), 4) if ids_t else None,
        "identical_order": ids_a == ids_t,
        "rank1_correct": (ids_a[:1] == ids_t[:1]) if ids_t else None,
        "best_days_left_path_a": best_a, "best_days_left_truth": best_t,
        "path_a_ids_not_in_truth": [i for i in ids_a if i not in set(ids_t)][:10],
    }


def identity_check(conn, table: str) -> Dict[str, Any]:
    a = path_a_tiebreak(conn, table)
    b = path_b(conn, table, "B2", tie=True)
    if a["truncated"]:
        return {"verdict": "NOT COMPARABLE (Path A truncated at MAX_SCAN)",
                "ok": None, "detail": "the two arms are answering different questions"}
    ok, why = rows_match(a["rows"], b["rows"])
    return {"verdict": "IDENTICAL" if ok else "DIVERGED", "ok": ok, "detail": why,
            "n_rows": len(a["rows"])}



# ---------------------------------------------------------------------------------------
# B4 -- the CEILING arm.  Same widget, but days_left computed with native Postgres date
# arithmetic instead of the xpr runtime.  THIS IS NOT A CANDIDATE IMPLEMENTATION: `::date`
# RAISES on a malformed date, which is precisely the totality violation xpr.pdate_ms
# (plpgsql) exists to prevent (compile.py:28-31, expr.py:409-431).  It is measured only to
# bound how much of Path B's time is the xpr runtime versus the scan itself -- the
# lever-attribution the RAG profile draws at core/storage/sql.py:249-250.
# ---------------------------------------------------------------------------------------
def build_b4(table: str, tie: bool = False):
    today = CTX["now"][:10]
    dl = f"(((data->>'due_date')::date - DATE '{today}')::float8)"
    params = {"coll": COLLECTION, "fstatus": json.dumps(WIDGET["filters"]["status"])}
    sql = (f"SELECT data || jsonb_build_object('{DERIVE_NAME}', to_jsonb({dl})) "
           f"FROM {table} WHERE collection = %(coll)s "
           f"AND (data -> 'status') = %(fstatus)s::jsonb "
           f"AND (data ? 'due_date') AND {dl} < 7 "
           f"ORDER BY {dl}{TIE if tie else ''} LIMIT {int(WIDGET['limit'])}")
    return sql, params


def path_b4(conn, table: str, tie: bool = False) -> Dict[str, Any]:
    sql, params = build_b4(table, tie)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    out = [r[0] for r in cur.fetchall()]
    return {"t": {"total_ms": (time.perf_counter() - t0) * 1000}, "rows": out, "sql": sql}


def runtime_microcost(conn, table: str) -> Dict[str, Any]:
    """Isolate the per-row cost of ONE xpr plpgsql call against the same scan."""
    cur = conn.cursor()
    out = {}
    for name, q in (
        ("count_only", f"SELECT count(*) FROM {table} WHERE collection = %s"),
        ("plus_field_read", f"SELECT count(data -> 'due_date') FROM {table} WHERE collection = %s"),
        ("plus_xpr_pdate_ms",
         f"SELECT count(xpr.pdate_ms(data -> 'due_date')) FROM {table} WHERE collection = %s"),
        ("plus_native_date",
         f"SELECT count((data->>'due_date')::date) FROM {table} WHERE collection = %s"),
    ):
        cur.execute(q, (COLLECTION,)); cur.fetchall()          # warm
        ts = []
        for _ in range(5):
            t0 = time.perf_counter(); cur.execute(q, (COLLECTION,)); cur.fetchall()
            ts.append((time.perf_counter() - t0) * 1000)
        out[name] = round(statistics.median(ts), 2)
    return out


def main():
    sizes = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1
                              else "1000,10000,20000,25000,100000,1000000".split(","))]
    nreps = {1000: 9, 10000: 9, 20000: 9, 25000: 9, 100000: 7, 1000000: 3}

    t0 = time.perf_counter()
    conn = psycopg2.connect(DSN)
    connect_ms = (time.perf_counter() - t0) * 1000
    cur = conn.cursor()
    cur.execute("SET extra_float_digits = 1")            # pinned, as the conformance run did
    cur.execute("SELECT version(), current_setting('max_parallel_workers_per_gather'),"
                " current_setting('work_mem'), current_setting('shared_buffers')")
    ver, par, wm, sb = cur.fetchone()

    report: Dict[str, Any] = {
        "widget": WIDGET, "ctx": CTX, "collection": COLLECTION,
        "pg": {"version": ver, "max_parallel_workers_per_gather": par,
               "work_mem": wm, "shared_buffers": sb},
        "python": sys.version.split()[0],
        "connect_ms": round(connect_ms, 2),
        "max_scan": SRC.MAX_SCAN,
        "sizes": {},
    }

    report["fallback"] = fallback_costs()
    report["tolerant_key_probe"] = tolerant_key_probe(conn)
    for v in ("B1", "B2", "B3"):
        _s, _p = build_b(v, "measure_instances_1000")
        report.setdefault("generated_sql", {})[v] = _s
    report["generated_sql"]["B4"] = build_b4("measure_instances_1000")[0]

    for n in sizes:
        table = f"measure_instances_{n}"
        R = nreps.get(n, 5)
        print(f"--- {table} (reps={R}) ---", flush=True)
        entry: Dict[str, Any] = {"table": table, "reps": R}

        entry["floor"] = scan_floor(conn, table)

        # warm both paths once (results discarded) so the reps measure a warm cache
        path_a(conn, table); path_b(conn, table, "B2")

        m0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        a = reps(lambda: path_a(conn, table), R)
        m1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        entry["path_a"] = a["agg"]
        entry["path_a_shape"] = {k: a["last"][k] for k in
                                 ("truncated", "rows_acquired", "rows_scanned", "rows_kept")}
        entry["path_a_peak_rss_mb"] = round(m1 / 1024.0, 1)
        entry["path_a_rss_growth_mb"] = round((m1 - m0) / 1024.0, 1)
        print("   A", entry["path_a"]["total_ms"], entry["path_a_shape"], flush=True)

        for v in ("B1", "B2", "B3"):
            b = reps(lambda: path_b(conn, table, v), R)
            entry[f"path_{v}"] = b["agg"]
            entry[f"path_{v}_rows"] = len(b["last"]["rows"])
            print(f"   {v}", entry[f"path_{v}"]["total_ms"], flush=True)

        b4 = reps(lambda: path_b4(conn, table), R)
        entry["path_B4_ceiling"] = b4["agg"]
        entry["path_B4_rows"] = len(b4["last"]["rows"])
        print("   B4", entry["path_B4_ceiling"]["total_ms"], flush=True)
        entry["runtime_microcost_ms"] = runtime_microcost(conn, table)
        print("   micro", entry["runtime_microcost_ms"], flush=True)

        drv_ms, drv_n = path_a_driver(conn, table)
        entry["path_a_driver_acquire_ms"] = round(drv_ms, 2)

        # ---- answer quality at and beyond MAX_SCAN -------------------------------------
        truth = ground_truth(conn, table, WIDGET["limit"])
        entry["qualifying_rows_total"] = qualifying_count(conn, table)
        entry["answer"] = answer_quality(conn, table, truth)
        # row-for-row identity of the two arms, both with the deterministic tiebreak
        entry["identity"] = identity_check(conn, table)
        b4t = path_b4(conn, table, tie=True)["rows"]
        ok4, why4 = rows_match(b4t, truth)
        entry["b4_ceiling_matches_compiled_answer"] = {"ok": ok4, "detail": why4}
        entry["explain_B2"] = explain(conn, table, "B2")
        entry["explain_B3"] = explain(conn, table, "B3")
        report["sizes"][str(n)] = entry
        print("   quality", entry["answer"], flush=True)
        print("   identity", entry["identity"]["verdict"], flush=True)

    out = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/measurements.json"
    if os.path.exists(out):                 # merge, so the sweep can be run in chunks
        try:
            prev = json.load(open(out))
            merged = dict(prev.get("sizes", {}))
            merged.update(report["sizes"])
            report["sizes"] = merged
        except Exception as e:
            print("merge skipped:", e)
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print("WROTE", out)


if __name__ == "__main__":
    main()
