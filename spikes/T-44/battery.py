"""T-44 battery driver: the FROZEN T-1/T-3 batteries, driven against a NAMED compiler.

Why a driver and not an edit. `differ.py` and `H_ast_fuzz.py` are frozen evidence: T-3's and
T-6's outputs cite them. And `differ.py` imports the frozen SPIKE compiler by name
(`import compile`, with spikes/T-1/proto first on sys.path). That is why the SHIPPING compiler
has never been through these batteries. This driver puts the compiler it was asked for into
`sys.modules["compile"]` BEFORE `differ` is imported, so the frozen import resolves to it. It
then prints what actually ran, read back from the loaded module and from pg_proc. A battery
that names the compiler it hoped for is how T-6's 42 outputs came to carry the wrong
provenance (T-10).

It adds two things the frozen harness cannot do, both required by T-44 FRAMING section 4:

  * --parallel on: `SET debug_parallel_query = on` on the battery's own connection, read back,
    plus a positive control. EXPLAIN ANALYZE of a real compiled battery query must show a
    launched worker. Otherwise the run stops: a forced-parallel battery that never left the
    leader is a check that never ran.
  * the PREDICATE form of every case. The timed arms filter with a boolean predicate, not with
    the jsonb value the batteries compare. The predicate is `compile_predicate()` where the
    compiler has one, else `xpr.truthy(<compiled jsonb>)`, exactly as T-4's harness wraps it.
    It runs on the same row and is compared with Python's own `_truthy`.

Every case is recorded, one JSON line each, so that K2 (no new refusals, same SQLSTATE) and the
case-level differential can be computed across compilers by compare_cases.py.

Usage (AUTOSQL_SPIKE_DSN must name a THROWAWAY database; port 55433 is refused):
    battery.py --compiler {spike,ship,inline} --profile P [--n 4000] [--seed 2026]
               [--parallel off|on] --tag TAG
AUTOSQL_EFD and AUTOSQL_MATCH_MODE are read by differ.py itself, unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True        # never write __pycache__ into either GIMS checkout

ROOT = "/home/corgea/Desktop/Coding Projects/autoSQL"
FUZZ = os.path.join(ROOT, "spikes/T-1/analysis/fuzz")
COMPILERS = {
    "spike": os.path.join(ROOT, "spikes/T-1/proto/compile.py"),
    "ship": os.path.join(ROOT, "compiler/compile.py"),
    "inline": os.path.join(ROOT, "spikes/T-44/compile_inline.py"),
}
OUT = os.path.join(ROOT, "spikes/T-44/out")
CASES = os.path.join(ROOT, ".autodev/evidence/T-44/cases")   # git-ignored: large, regenerable


def sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_compiler(name: str):
    # "file:<path>" runs a compiler from anywhere -- e.g. a branch worktree's
    # compiler/compile.py -- with the same provenance read-back as the named ones.
    path = name[5:] if name.startswith("file:") else COMPILERS[name]
    spec = importlib.util.spec_from_file_location("compile", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["compile"] = mod          # the frozen `import compile` now resolves here
    spec.loader.exec_module(mod)
    return mod, path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True,
                    help="spike | ship | inline | file:<path to a compile.py>")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--parallel", choices=("off", "on"), default="off")
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()

    dsn = os.environ.get("AUTOSQL_SPIKE_DSN", "")
    if not dsn or "port=55433" in dsn:
        raise SystemExit("REFUSING: AUTOSQL_SPIKE_DSN unset or pointing at 55433 (the live database)")

    xc, xc_path = load_compiler(a.compiler)

    # H_ast_fuzz reads profile / N / seed from sys.argv AT IMPORT, and does
    # sys.path.insert(0, '.') + `import differ`, so the fuzz dir goes on the path first.
    sys.argv = ["H_ast_fuzz.py", a.profile, str(a.n), str(a.seed)]
    sys.path.insert(0, FUZZ)
    import differ                                          # noqa: E402  frozen
    if differ.xcompile is not xc:
        raise SystemExit("PROVENANCE FAILURE: differ imported a different compile module "
                         f"({getattr(differ.xcompile, '__file__', '?')}) than {xc_path}")
    spec = importlib.util.spec_from_file_location("H_ast_fuzz", os.path.join(FUZZ, "H_ast_fuzz.py"))
    H = importlib.util.module_from_spec(spec)
    sys.modules["H_ast_fuzz"] = H
    spec.loader.exec_module(H)

    # ---- forced parallel mode on the battery's own connection --------------------------
    par_state = {"requested": a.parallel, "readback": None, "positive_control": None}
    orig_conn = differ.conn

    def conn_wrapped():
        c = orig_conn()
        if par_state["readback"] is None:
            with c.cursor() as cur:
                if a.parallel == "on":
                    cur.execute("SET debug_parallel_query = on")
                cur.execute("SHOW debug_parallel_query")
                par_state["readback"] = cur.fetchone()[0]
            if a.parallel == "on" and par_state["readback"] != "on":
                raise SystemExit("positive-control failure: debug_parallel_query did not take")
        return c

    differ.conn = conn_wrapped

    # ---- per-case recording + the predicate form ---------------------------------------
    import psycopg2                                        # noqa: E402
    expr = differ.expr
    records = []
    pred_counts = {}
    orig_run_case = differ.run_case

    def predicate_sql(ast):
        if hasattr(xc, "compile_predicate"):
            c = xc.compile_predicate(ast)
            return c.sql, c.params
        c = xc.compile_ast(ast)
        return f"xpr.truthy({c.sql})", c.params

    def run_pred(src, record, ctx):
        """Python's truthiness of the value vs the SQL predicate on the same row."""
        try:
            ast = expr.parse(src)
        except Exception:
            return {"pred": "PARSE_ERROR"}
        try:
            py_t = expr._truthy(expr.evaluate(ast, record, ctx or {}))
            py_err = None
        except Exception as e:                             # expr claims totality; record it
            py_t, py_err = None, f"{type(e).__name__}: {e}"
        try:
            sql, params = predicate_sql(ast)
        except xc.Uncompilable as e:
            return {"pred": "UNCOMPILABLE", "why": e.reason}
        params = dict(params)
        params["ctx"] = json.dumps(ctx or {})
        params["rec"] = json.dumps(record)
        q = f"SELECT ({sql}) FROM (SELECT (%(rec)s)::jsonb AS data) t"
        try:
            with differ.conn().cursor() as cur:
                cur.execute(q, params)
                got = cur.fetchone()[0]
            sql_err, state = None, None
        except psycopg2.Error as e:
            got, sql_err, state = None, str(e).strip().splitlines()[0], e.pgcode
        if py_err and sql_err:
            v = "BOTH_RAISE"
        elif py_err:
            v = "PY_RAISE"
        elif sql_err:
            v = "SQL_RAISE"
        elif got is None:
            v = "NULL"                                     # a predicate must never be NULL
        else:
            v = "AGREE" if got is py_t else "DIVERGE"
        return {"pred": v, "pred_sqlstate": state, "pred_py": py_t, "pred_sql": got,
                "pred_err": sql_err or py_err}

    def run_case_rec(src, record=None, ctx=None, mode="py", raw=None, note=""):
        o = orig_run_case(src, record, ctx, mode=mode, raw=raw, note=note)
        r = {"i": len(records), "expr": src, "record": record, "ctx": ctx,
             "verdict": o.get("verdict"), "sqlstate": o.get("sqlstate"),
             "refusal_kind": o.get("refusal_kind"), "python": o.get("python"),
             "python_raised": o.get("python_raised"), "sql_value": o.get("sql_value"),
             "sql_typeof": o.get("sql_typeof"), "sql_raised": o.get("sql_raised")}
        if o.get("verdict") not in ("PARSE_ERROR", "UNCOMPILABLE"):
            p = run_pred(src, record, ctx)
            r.update(p)
            pred_counts[p["pred"]] = pred_counts.get(p["pred"], 0) + 1
        records.append(r)
        return o

    H.run_case = run_case_rec          # H bound the name at import (`from differ import run_case`)

    # ---- positive control for --parallel on: a real compiled query must launch a worker --
    if a.parallel == "on":
        probe_src = "coalesce($.a, 0) + 1 > 2"
        ast = expr.parse(probe_src)
        c = xc.compile_ast(ast)
        params = dict(c.params)
        params["ctx"] = "{}"
        params["rec"] = json.dumps({"a": 5})
        q = ("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT " + c.sql +
             " FROM (SELECT (%(rec)s)::jsonb AS data) t")
        with conn_wrapped().cursor() as cur:
            cur.execute(q, params)
            plan = "\n".join(r[0] for r in cur.fetchall())
        launched = [ln.strip() for ln in plan.splitlines() if "Workers Launched" in ln]
        par_state["positive_control"] = {"probe": probe_src, "plan": plan,
                                         "workers_launched": launched}
        # On the shipping runtime every xpr function is PARALLEL UNSAFE, so no Gather is
        # planned at all.  That is an honest outcome, not a failure: it is recorded and the
        # battery runs in the leader exactly as it would without the setting.
        par_state["gather_planned"] = "Gather" in plan
        if par_state["gather_planned"] and not any(ln.endswith(": 1") for ln in launched):
            raise SystemExit("positive-control failure: a Gather was planned but no worker "
                             f"launched -- the forced run would silently stay in the leader.\n{plan}")

    # ---- run the frozen battery, capturing its report ----------------------------------
    t0 = time.monotonic()
    buf = io.StringIO()
    rc = 0
    try:
        with redirect_stdout(buf):
            H.main()
    except SystemExit as e:                                # stop rule 3 exits 3; keep going
        rc = int(e.code or 0)
    wall = time.monotonic() - t0

    # ---- the true fingerprints ---------------------------------------------------------
    with differ.conn().cursor() as cur:
        cur.execute("select version(), current_database(), current_setting('debug_parallel_query'), "
                    "current_setting('extra_float_digits')")
        version, db, dpq, efd = cur.fetchone()
        cur.execute("""select proparallel, provolatile, count(*) from pg_proc p
                         join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = 'xpr' group by 1, 2 order by 1, 2""")
        labels = [list(r) for r in cur.fetchall()]
    fp = {
        "tag": a.tag, "compiler": a.compiler, "compiler_file": xc_path,
        "compiler_sha256": sha256(xc_path),
        "loaded_module_file": getattr(differ.xcompile, "__file__", None),
        "installed_runtime_sha256": differ.installed_runtime_sha(),
        "xpr_labels(proparallel,provolatile,count)": labels,
        "database": db, "server": version.split(" on ")[0],
        "debug_parallel_query": dpq, "parallel": par_state,
        "efd_requested": differ.EFD, "efd_readback": differ.EFD_READBACK,
        "match_mode": differ.MATCH_MODE, "profile": a.profile, "n": a.n, "seed": a.seed,
        "predicate_verdicts": pred_counts, "wall_s": round(wall, 1), "exit": rc,
    }

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(CASES, exist_ok=True)
    with open(os.path.join(OUT, a.tag + ".txt"), "w") as fh:
        fh.write(buf.getvalue())
        fh.write("\n=== T-44 driver: what ACTUALLY ran (read back, not assumed) ===\n")
        fh.write(json.dumps(fp, indent=1, default=str) + "\n")
    with open(os.path.join(CASES, a.tag + ".jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, default=repr, ensure_ascii=False) + "\n")

    counts = {}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"{a.tag}: exit={rc} wall={wall:.1f}s value-verdicts={counts} "
          f"predicate-verdicts={pred_counts} dpq={dpq} gather={par_state.get('gather_planned')}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
