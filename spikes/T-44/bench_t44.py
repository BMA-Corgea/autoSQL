"""T-44 timing harness: seven arms, interleaved rounds, on a LOADED host.

FRAMING section 10 (the loaded-host amendment, written before the first timed rep) is the
specification. In brief:

  * Every cell (size x encoding) runs its seven arms in INTERLEAVED ROUNDS. Each round runs
    every arm once, starting one arm later than the round before, so the same-session Python
    arm samples the same load as every candidate. n = 25 rounds.
  * Load is RECORDED per repetition, as the 1-minute load average read immediately before it.
    It NEVER voids a cell. These numbers are treated as pristine, on the owner's standing
    words.
  * Every other admissibility gate from T-4 stays. Corpus row count (void the cell). Index
    help (void the arm). Identity against the uncapped Python oracle: for a CANDIDATE, a
    disagreement is a wrong number, recorded as K5 FAIL; for a reported arm it voids that
    arm, as in T-4.
  * Nothing here connects to 55433. T-4's host_state() reads two counters from the live
    database; this harness does not call it. Tonight's charter forbids any connection there.

Reused from T-4 by import, never copied: the arms A and B4, the arm-C statement builder (with
the compiler swapped in for its run), the tiebroken oracle, the plan and buffer readers, the
statistics, and the connection setup. The C statements for the shipping and lever-(a) runtimes
are T-4's builder output with every `xpr.<fn>(` moved to that runtime's schema.

SEAMS for control_t44.py: read_loadavg, read_row_count, capture_plan, perturb_rows, and
call_arm (to make one repetition raise).

Usage: AUTOSQL_SPIKE_DSN=<autosql_spike> bench_t44.py <sizes> <encodings> <out.json> [rounds]
       e.g.  bench_t44.py 20000,100000 num,text spikes/T-44/out/timing.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import statistics
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if "port=55433" in os.environ.get("AUTOSQL_SPIKE_DSN", ""):
    raise SystemExit("REFUSING: 55433 is the live database")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T4 = _load("bench_t4", os.path.join(ROOT, "spikes", "T-4", "bench_t4.py"))
B, SRC = T4.B, T4.SRC
SPIKE = B.CC                                                     # the frozen spike compiler
SHIP = _load("t44_ship_compile", os.path.join(ROOT, "compiler", "compile.py"))
INLINE = _load("t44_inline_compile", os.path.join(HERE, "compile_inline.py"))
# T-52's head (dc088f7), frozen in t52_head/: the SHIPPING candidate after main was merged in.
# Timed as a REPORTED arm beside C_both, which the pre-registered verdict reads on.
T52HEAD = _load("t44_t52_head_compile", os.path.join(HERE, "t52_head", "compile.py"))

SPEC = T4.WIDGET_INVENTED
ENCODINGS = {"num": "measure_instances_{n}", "text": "t44_text_{n}"}
ROUNDS = 25
CANDIDATES = ("C_par", "C_inline", "C_both")
REPORTED = ("C_spike", "C_ship", "B4", "C_t52")
ARM_ORDER = ("A", "B4", "C_spike", "C_ship", "C_par", "C_inline", "C_both", "C_t52")

_CALL = re.compile(r"\bxpr\.(\w+)\(")


def in_schema(sql: str, schema: str) -> str:
    if schema == "xpr":
        return sql
    out = _CALL.sub(schema + r".\1(", sql)
    assert not _CALL.search(out)
    return out


# ---- statement builders --------------------------------------------------------------

def build_classic(table: str, spec, compiler, schema: str) -> Tuple[str, Dict[str, Any]]:
    """T-4's arm-C statement, byte for byte, with `compiler` swapped in for the duration."""
    old = B.CC
    B.CC = compiler
    try:
        sql, params = T4._arm_c_sql(table, spec)
    finally:
        B.CC = old
    return in_schema(sql, schema), params


def build_inline(table: str, spec, schema: str, compiler=None) -> Tuple[str, Dict[str, Any]]:
    """The same statement shape as T-4's _t4_build_b2(order=False). Two things differ: the
    derive is compiled by lever (b), and the predicate is compile_predicate() in place of
    xpr.truthy(<jsonb>)."""
    w = spec["widget"]
    name = spec["derive_name"]
    if w.get("filters"):
        raise ValueError("build_inline expresses no filters; the invented widget has none")
    d_ast = B.EXPR.parse(w["derive"][name])
    w_ast = B.EXPR.parse(w["where"])
    params: Dict[str, Any] = {"coll": B.COLLECTION, "ctx": json.dumps(B.CTX)}

    def take(c, tag: str) -> str:
        sql = c.sql
        for k, v in c.params.items():
            params[f"{tag}_{k}"] = v
            sql = sql.replace(f"%({k})s", f"%({tag}_{k})s")
        return sql

    comp = compiler or INLINE
    w_sql = take(comp.compile_predicate(B.subst(w_ast, name, d_ast), column="data"), "w")
    d_out = take(comp.compile_ast(d_ast, column="data"), "o")
    sql = (f"SELECT (data || jsonb_build_object('{name}', {d_out})) FROM {table} "
           f"WHERE collection = %(coll)s AND {w_sql}")
    return in_schema(sql, schema), params


BUILDERS: Dict[str, Callable[[str, Any], Tuple[str, Dict[str, Any]]]] = {
    "C_spike": lambda t, s: build_classic(t, s, SPIKE, "xpr"),
    "C_ship": lambda t, s: build_classic(t, s, SHIP, "xpr_ship"),
    "C_par": lambda t, s: build_classic(t, s, SHIP, "xpr_par"),
    "C_inline": lambda t, s: build_inline(t, s, "xpr_ship"),
    "C_both": lambda t, s: build_inline(t, s, "xpr_par"),
    "C_t52": lambda t, s: build_inline(t, s, "xpr_t52", T52HEAD),
}


def run_c(conn, table: str, spec, arm: str) -> Dict[str, Any]:
    """T-4's arm_c, with the statement swapped: SQL for the derive and predicate, then
    Python for the sort and the limit. Both halves are what a person waits for."""
    sql, params = BUILDERS[arm](table, spec)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    rows = [r[0] for r in cur.fetchall()]
    t_sql = (time.perf_counter() - t0) * 1000
    n_sql = len(rows)
    t1 = time.perf_counter()
    rows = SRC._apply_sort(rows, spec["widget"]["sort"])
    rows = SRC._apply_limit(rows, spec["widget"]["limit"])
    t_py = (time.perf_counter() - t1) * 1000
    return {"ms": t_sql + t_py, "rows": rows,
            "split": {"sql_ms": round(t_sql, 2), "python_tail_ms": round(t_py, 2)},
            "shape": {"rows_from_sql": n_sql, "rows_after_limit": len(rows)}}


ARMS: Dict[str, Callable] = {"A": T4.arm_a, "B4": T4.arm_b4}
for _arm in BUILDERS:
    ARMS[_arm] = (lambda a: (lambda conn, table, spec: run_c(conn, table, spec, a)))(_arm)


# ---- SEAMS (control_t44.py swaps these) ---------------------------------------------

def read_loadavg() -> Tuple[float, float, float]:
    return T4.read_loadavg()


def read_row_count(conn, table: str) -> int:
    return T4.read_row_count(conn, table)


def capture_plan(conn, sql: str, params) -> str:
    return T4.capture_plan(conn, sql, params)


def perturb_rows(rows: List[dict], arm: str = "") -> List[dict]:
    return rows


def call_arm(arm: str, conn, table: str, spec) -> Dict[str, Any]:
    return ARMS[arm](conn, table, spec)


# ---- per-arm plan facts ---------------------------------------------------------------

def plan_facts(conn, table: str, spec, arm: str) -> Dict[str, Any]:
    if arm == "B4":
        sql, params = T4._build_b4_generic(table, spec)
    else:
        sql, params = BUILDERS[arm](table, spec)
    plan = capture_plan(conn, sql, params)
    wp = re.findall(r"Workers Planned: (\d+)", plan)
    wl = re.findall(r"Workers Launched: (\d+)", plan)
    jit = [ln.strip() for ln in plan.splitlines() if ln.strip().startswith(("JIT", "Functions:", "Options:", "Timing:"))]
    return {"plan": plan, "index_help": T4.index_help_in_plan(plan),
            "buffers": T4.buffers_from_plan(plan),
            "workers_planned": int(wp[0]) if wp else 0,
            "workers_launched": int(wl[0]) if wl else 0,
            "jit": jit, "statement_chars": len(sql)}


# ---- identity (K5) ----------------------------------------------------------------------

def rows_tiebroken(conn, table: str, spec, arm: str) -> List[dict]:
    limit = int(spec["widget"]["limit"])
    if arm in ("A", "A_uncapped", "B4"):
        return T4._arm_rows_tiebroken(conn, table, spec, arm)
    sql, params = BUILDERS[arm](table, spec)
    cur = conn.cursor()
    cur.execute(sql, params)
    return T4._t4_sorted_tiebroken([r[0] for r in cur.fetchall()], spec)[:limit]


def identity(conn, table: str, spec, arms) -> Dict[str, Any]:
    truth = rows_tiebroken(conn, table, spec, "A_uncapped")
    truth_ids = [r.get("id") for r in truth]
    out = {"reference": "A_uncapped", "tiebroken": True, "arms": {}}
    for arm in arms:
        if arm == "A":
            continue
        rows = perturb_rows(rows_tiebroken(conn, table, spec, arm), arm)
        ids = [r.get("id") for r in rows]
        same, why = B.rows_match(rows, truth)
        agree = same and ids == truth_ids
        out["arms"][arm] = {"agree": agree, "n": len(rows),
                            "detail": "identical rows, tiebroken (every field, frozen rows_match)"
                            if agree else why}
    a_ids = [r.get("id") for r in rows_tiebroken(conn, table, spec, "A")]
    out["arm_a_recall_pct"] = round(100.0 * len(set(a_ids) & set(truth_ids)) / len(truth_ids), 1) if truth_ids else None
    return out


# ---- one cell: interleaved rounds ----------------------------------------------------------

def host_snapshot(label: str) -> Dict[str, Any]:
    l1, l5, l15 = read_loadavg()
    return {"label": label, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "loadavg": {"1min": l1, "5min": l5, "15min": l15}, "nproc": os.cpu_count(),
            "top_processes": T4.top_processes(5), "memory": T4.memory_state(),
            "docker": T4.docker_state()}


def run_cell(conn, n: int, encoding: str, rounds: int = ROUNDS,
             arms=ARM_ORDER) -> Dict[str, Any]:
    table = ENCODINGS[encoding].format(n=n)
    spec = SPEC
    cell: Dict[str, Any] = {"size": n, "encoding": encoding, "table": table, "invented": True,
                            "rounds_planned": rounds, "host_start": host_snapshot(f"{n}/{encoding}/start")}
    actual = read_row_count(conn, table)
    if actual != n:
        cell.update(T4.cell_void("corpus_incomplete", f"{table} holds {actual} rows, expected {n}"))
        return cell
    with T4.widget(spec):
        live = list(arms)
        arm_out: Dict[str, Dict[str, Any]] = {a: {} for a in live}
        for arm in live:
            if arm == "A":
                continue
            f = plan_facts(conn, table, spec, arm)
            arm_out[arm]["plan_facts"] = {k: v for k, v in f.items() if k != "plan"}
            arm_out[arm]["plan"] = f["plan"]
            if f["index_help"]:
                arm_out[arm].update(T4.cell_void("index_help", f["index_help"]))
        ident = identity(conn, table, spec, [a for a in live if "outcome" not in arm_out[a]])
        cell["identity"] = ident
        for arm, res in ident["arms"].items():
            if not res["agree"]:
                if arm in CANDIDATES:
                    arm_out[arm]["K5"] = "FAIL"          # a wrong number: never a void
                else:
                    arm_out[arm].update(T4.cell_void("arms_disagree", res["detail"]))
            elif arm in CANDIDATES:
                arm_out[arm]["K5"] = "PASS"
        timed = [a for a in live if arm_out[a].get("outcome") != T4.VOID]
        for arm in timed:                                # warm once, recorded, excluded
            try:
                arm_out[arm]["warmup_ms"] = round(call_arm(arm, conn, table, spec)["ms"], 2)
            except Exception as exc:
                conn.rollback()
                arm_out[arm]["warmup_error"] = f"{type(exc).__name__}: {exc}"
        reps: Dict[str, List[Dict[str, Any]]] = {a: [] for a in timed}
        last: Dict[str, Dict[str, Any]] = {}
        for r in range(rounds):
            k = r % len(timed)
            order = timed[k:] + timed[:k]
            for pos, arm in enumerate(order):
                load1 = read_loadavg()[0]
                try:
                    res = call_arm(arm, conn, table, spec)
                except Exception as exc:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    reps[arm].append(T4.cell_void("rep_error", f"{type(exc).__name__}: {exc}",
                                                  {"round": r, "pos": pos, "load1": load1}))
                    continue
                last[arm] = res
                rep = T4.cell_measured({"ms": res["ms"], "round": r, "pos": pos, "load1": load1})
                if "split" in res:
                    rep["split"] = res["split"]
                reps[arm].append(rep)
        a_by_round = {x["round"]: x["ms"] for x in reps.get("A", []) if T4.is_measured(x)}
        for arm in timed:
            agg = T4.aggregate(reps[arm])
            loads = [x["load1"] for x in reps[arm]]
            arm_out[arm]["stats"] = agg
            arm_out[arm]["load1_per_rep"] = {"min": min(loads), "median": statistics.median(loads),
                                             "max": max(loads)} if loads else None
            arm_out[arm]["reps"] = reps[arm]
            if agg.get("outcome") == T4.VOID:
                arm_out[arm].update({"outcome": T4.VOID, "void_reason": agg["void_reason"]})
            else:
                arm_out[arm]["outcome"] = T4.MEASURED
            if arm != "A" and a_by_round:
                d = [x["ms"] - a_by_round[x["round"]] for x in reps[arm]
                     if T4.is_measured(x) and x["round"] in a_by_round]
                arm_out[arm]["paired_minus_A_ms"] = ({"n": len(d), "median": round(statistics.median(d), 2)}
                                                     if d else None)
            if arm in last:
                arm_out[arm]["shape"] = last[arm].get("shape")
                arm_out[arm]["split_last"] = last[arm].get("split")     # arms A and B4 have none
    cell["arms"] = arm_out
    cell["host_end"] = host_snapshot(f"{n}/{encoding}/end")
    cell["outcome"] = T4.MEASURED
    return cell


# ---- the bar (FRAMING section 4.2-4.3, read under section 10) -------------------------------

BAR_MEDIAN_100K, BAR_P95_100K = 300.0, 600.0
NEAR = 1.25


def judge(cells: Dict[str, Dict[str, Any]], sizes=(20000, 100000), encs=("num", "text")) -> Dict[str, Any]:
    """S1-S4 and K5 per candidate. K1-K4 come from the batteries and are applied in
    synthesis. A missing or void required cell gives INCOMPLETE, never a pass."""
    out: Dict[str, Any] = {}
    for c in CANDIDATES:
        checks, missing, near_ok = [], [], True
        for n in sizes:
            for e in encs:
                cell = cells.get(f"{n}/{e}")
                arm = (cell or {}).get("arms", {}).get(c)
                a = (cell or {}).get("arms", {}).get("A")
                if (not cell or cell.get("outcome") != T4.MEASURED or not arm or not a
                        or arm.get("outcome") != T4.MEASURED or a.get("outcome") != T4.MEASURED):
                    missing.append(f"{n}/{e}")
                    continue
                if arm.get("K5") != "PASS":
                    checks.append((f"K5 {n}/{e}", False, "identity failed: a wrong number"))
                    near_ok = False
                    continue
                med, p95 = arm["stats"]["median"], arm["stats"].get("p95")
                a_med = a["stats"]["median"]
                if n == 100000:
                    s1 = med <= BAR_MEDIAN_100K and p95 is not None and p95 <= BAR_P95_100K
                    checks.append((f"S1 {n}/{e}", s1, f"median {med} <= 300 and p95 {p95} <= 600"))
                    if not s1 and not (med <= BAR_MEDIAN_100K * NEAR and p95 is not None
                                       and p95 <= BAR_P95_100K * NEAR):
                        near_ok = False
                    s2 = med < a_med
                    checks.append((f"S2 {n}/{e}", s2, f"median {med} < Python {a_med}"))
                    near_ok = near_ok and s2
                else:
                    s3 = med <= a_med + 100.0
                    checks.append((f"S3 {n}/{e}", s3, f"median {med} <= Python {a_med} + 100"))
                    near_ok = near_ok and s3
        failed = [k for k, ok, _ in checks if not ok]
        if any(k.startswith("K5") for k in failed):
            v = "FAIL"                       # any wrong number fails the candidate outright
        elif not failed and not missing:
            v = "PASS"
        elif failed and not near_ok:
            v = "FAIL"                       # T-4 section 4.5: a decisive miss stays a FAIL,
        elif missing:                        # whatever went untested elsewhere
            v = "INCOMPLETE"
        else:
            v = "NEAR-MISS"
        out[c] = {"speed_verdict": v, "checks": checks, "missing": missing}
    rank = {"PASS": 3, "NEAR-MISS": 2, "INCOMPLETE": 1, "FAIL": 0}

    def med100k(c):          # tie-break among equal verdicts: the fastest at 100,000 rows
        ms = [cells[f"100000/{e}"]["arms"][c]["stats"]["median"] for e in encs
              if cells.get(f"100000/{e}", {}).get("arms", {}).get(c, {}).get("stats", {}).get("median") is not None]
        return -max(ms) if ms else float("-inf")
    best = max(CANDIDATES, key=lambda c: (rank[out[c]["speed_verdict"]], med100k(c)))
    return {"per_candidate": out, "best": best, "run_verdict_speed_and_K5": out[best]["speed_verdict"]}


def statement_record() -> Dict[str, Any]:
    """Every statement this run times, for the record (display-rendered; never executed)."""
    out = {}
    with T4.widget(SPEC):
        for arm, build in BUILDERS.items():
            sql, params = build("measure_instances_100000", SPEC)
            out[arm] = {"chars": len(sql), "sql": sql}
    return out


def main(argv: List[str]) -> int:
    sizes = [int(x) for x in argv[1].split(",")]
    encs = argv[2].split(",")
    out_path = argv[3]
    rounds = int(argv[4]) if len(argv) > 4 else ROUNDS
    conn = T4.connect()
    report: Dict[str, Any] = {
        "run": "T-44 timing run (loaded host; FRAMING section 10)",
        "builder_faithfulness": T4._assert_builder_faithful(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bar_is": "ABSOLUTE MILLISECONDS, read literally on a loaded host (FRAMING section 10)",
        "candidates": CANDIDATES, "reported": REPORTED, "rounds": rounds,
        "widget": {"name": SPEC["name"], "invented": True, "spec": SPEC["widget"]},
        "server": T4.server_state(conn), "python": sys.version.split()[0], "max_scan": SRC.MAX_SCAN,
        "statements": statement_record(), "cells": {},
    }
    with conn.cursor() as cur:
        cur.execute("""select name, setting from pg_settings where name in ('jit','jit_above_cost',
                       'jit_inline_above_cost','jit_optimize_above_cost','max_parallel_workers_per_gather',
                       'max_parallel_workers','max_worker_processes','min_parallel_table_scan_size',
                       'parallel_setup_cost','parallel_tuple_cost','debug_parallel_query',
                       'extra_float_digits','synchronize_seqscans','work_mem','shared_buffers')""")
        report["server"]["settings_read_back"] = dict(cur.fetchall())
    for n in sizes:
        for e in encs:
            t0 = time.time()
            print(f"--- cell {n}/{e} ---", flush=True)
            cell = run_cell(conn, n, e, rounds)
            report["cells"][f"{n}/{e}"] = cell
            for arm, a in cell.get("arms", {}).items():
                s = a.get("stats", {})
                print(f"   {arm:9s} {a.get('outcome', '?'):9s} median={s.get('median')} p95={s.get('p95')} "
                      f"K5={a.get('K5', '-')} workers={a.get('plan_facts', {}).get('workers_launched')} "
                      f"load~{(a.get('load1_per_rep') or {}).get('median')}", flush=True)
            print(f"   ({time.time() - t0:.0f}s)", flush=True)
            json.dump(report, open(out_path, "w"), indent=1, default=str)   # survive an interruption
    report["verdict_speed_and_K5"] = judge(report["cells"], tuple(sizes), tuple(encs))
    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(report, open(out_path, "w"), indent=1, default=str)
    print(json.dumps(report["verdict_speed_and_K5"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
