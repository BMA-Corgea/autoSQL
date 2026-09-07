"""T-4 -- the timing run's harness.  How long does a person actually wait?

This is Run 2.  It answers, in ABSOLUTE MILLISECONDS, how long a person waits for
a dashboard widget answered by the generated SQL versus GIMS's current in-memory
Python path.  The owner's own correction is what set the bar in milliseconds
rather than a ratio (FRAMING.md section 2), and everything here follows from it:
a millisecond figure taken at an unknown host load cannot be compared to
anything, so this harness refuses to emit one.

WHY THIS FILE EXISTS RATHER THAN AN EDIT TO ../T-1/proto/bench.py
-----------------------------------------------------------------
Everything under spikes/ is FROZEN EVIDENCE (kb/CURRENT-WORK.md): bench.py is the
artifact the existing sweep's numbers were produced by.  This file therefore
IMPORTS the frozen harness and drives it, rather than modifying it.  Arms A, B2
and B4 run through the frozen code paths unchanged, which is what makes the date
widget usable as a control: it re-measures the original sweep's own code under a
recorded host load for the first time.

WHAT IS NEW HERE (EXPERIMENTS.md section 2.4's build list, items 1-10)
----------------------------------------------------------------------
  1  host load recorded before and after every size            -> host_state()
  3  arm C, the shippable path -- SQL derive+where, Python sort+limit   -> arm_c()
  4  arm A-uncapped -- Python with MAX_SCAN lifted             -> arm_a_uncapped()
  5  the widget is selectable; the invented one and the date control both run
  6  the B1 and B3 arms are dropped
  7  the query plan is captured AND asserted on for every compiled arm
  8  dispersion reported: n, min, median, p95 (only where n >= 20), max, stdev
  9  synchronize_seqscans pinned and recorded, from THIS container
 10  the peak-memory column is DROPPED (see MEMORY, below)

THE VOID PATH IS THE POINT (FRAMING.md section 6.1)
---------------------------------------------------
A harness that has only ever printed "measured" has not been shown capable of
printing anything else.  This project already shipped that exact mistake once:
three of four failure branches in proto/conformance.py had never executed, and
every conformance headline in the record had come from a rig whose failure
surface was dead.  So each admissibility gate here runs through ONE seam that
the negative control can swap (control_t4.py), and a cell that voids is excluded
from every statistic rather than merely labelled.

MEMORY: the column is dropped, not fixed.  bench.py reads RUSAGE_SELF.ru_maxrss,
a whole-process high-water mark, so at 1M it carries every smaller arm's residue.
EXPERIMENTS.md section 2.4 item 10 allows one process per size, per-call
measurement, or dropping it.  A wrong number is worse than a missing one.
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# Keep __pycache__ out of the owner's GIMS checkouts -- FRAMING.md section 6 item 11
# makes writing into either checkout inadmissible, and bench.py puts GIMS-Project on
# sys.path.  Set before the import below, not after.
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROTO = os.path.join(_HERE, "..", "T-1", "proto")
sys.path.insert(0, _PROTO)

import bench as B                      # noqa: E402  the FROZEN harness, driven not edited
from api.dashboard import sources as SRC   # noqa: E402  the REAL in-memory pipeline


# =======================================================================================
# The widgets.  Two per run: the invented one the bar applies to, and the date widget
# as a control.
# =======================================================================================

# INVENTED.  EXPERIMENTS.md section 2.3 / FRAMING.md section 7.2.  The owner's Q8 asked him
# to name a real widget; item 7 of the second form took the default instead.  It is
# therefore NOT one of his widgets, and FRAMING.md section 6 item 3 makes an unlabelled
# invented widget an INADMISSIBLE result -- a latency figure silently attributed to real
# usage is a fabrication however carefully it was measured.  The `invented` flag below is
# carried into every cell of the output and every table of the readout.
WIDGET_INVENTED = {
    "name": "load_score",
    "invented": True,
    "derive_name": "load_score",
    "widget": {
        "type": "noun", "noun_type": "Sample",
        "filters": {},
        "derive": {"load_score": "coalesce($.queue_depth, 0) + coalesce($.retest_count, 0) * 25"},
        "where": "$.load_score > 195",
        "sort": {"field": "load_score", "dir": "desc"},
        "limit": 50,
    },
    # native-operator equivalent for the B4 ceiling arm.  ::numeric RAISES on a malformed
    # value where the language must return null -- which is exactly why it is not a
    # candidate implementation, only a physics ceiling.
    "b4_expr": ("(coalesce((data->>'queue_depth')::numeric, 0) "
                "+ coalesce((data->>'retest_count')::numeric, 0) * 25)"),
    "b4_desc": "desc",
}

# The CONTROL.  The original sweep's widget, re-measured in this session on this run's
# rows under a recorded host load.  FRAMING.md section 7.2: this is NOT a licence to quote
# an old absolute number -- adding the two generator fields shifted the random stream, so
# 999 of every 1,000 rows differ from the corpus those numbers came from.
WIDGET_DATE = {
    "name": "days_left",
    "invented": False,
    "derive_name": "days_left",
    "widget": dict(B.WIDGET),
    "b4_expr": None,          # build_b4 in the frozen harness already is this arm
    "b4_desc": "asc",
}

WIDGETS = {"invented": WIDGET_INVENTED, "date_control": WIDGET_DATE}


# =======================================================================================
# Admissibility seams.
#
# Each of these is the ONE place the harness learns a fact that can void a cell.  The
# negative control swaps the seam and asserts on the emitted outcome, which is how the
# void path gets driven through the real harness rather than a copy of it.
# =======================================================================================

LOAD_CEILING_START = 2.0     # FRAMING.md section 5.1
LOAD_CEILING_END = 4.0


def read_loadavg() -> Tuple[float, float, float]:
    """1-, 5- and 15-minute load averages.  SEAM: injection 1 swaps this."""
    with open("/proc/loadavg") as fh:
        parts = fh.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def read_row_count(conn, table: str) -> int:
    """Rows actually in the table.  SEAM: injection 2 swaps this."""
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table}")
    return int(cur.fetchone()[0])


def capture_plan(conn, sql: str, params) -> str:
    """EXPLAIN (ANALYZE, BUFFERS) for a compiled arm.  SEAM: injection 3 swaps this."""
    cur = conn.cursor()
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING ON) " + sql, params)
    return "\n".join(r[0] for r in cur.fetchall())


def perturb_rows(rows: List[dict]) -> List[dict]:
    """Identity by default.  SEAM: injection 4 swaps this to perturb one row."""
    return rows


# ---- what the seams are checked against ----------------------------------------------

def index_help_in_plan(plan: str) -> Optional[str]:
    """Q11 put indexes permanently off, so a generated query must be a sequential scan
    every time.  The corpus KEEPS the production GIN index (the real instances table has
    one) precisely so the run can DEMONSTRATE it is unused rather than assume it.

    Returns the offending line, or None if the plan is clean.  A primary-key lookup doing
    the `collection = ...` restriction is the one allowed index use.
    """
    for raw in plan.splitlines():
        line = raw.strip()
        low = line.lower()
        if "index scan" not in low and "index only scan" not in low:
            continue
        # "->  Index Scan using measure_instances_1000_pkey on ..."  is the allowed one.
        if "_pkey" in low:
            continue
        return line
    return None


def buffers_from_plan(plan: str) -> Dict[str, int]:
    """shared hit/read, per FRAMING.md section 5.4 item 13 -- cache state is MEASURED,
    never claimed (section 6 item 8)."""
    hit = read = 0
    for raw in plan.splitlines():
        low = raw.lower()
        if "shared" not in low:
            continue
        toks = low.replace("=", " ").split()
        for i, t in enumerate(toks):
            if t == "hit" and i + 1 < len(toks) and toks[i + 1].isdigit():
                hit += int(toks[i + 1])
            if t == "read" and i + 1 < len(toks) and toks[i + 1].isdigit():
                read += int(toks[i + 1])
    return {"shared_hit": hit, "shared_read": read}


# =======================================================================================
# Cell outcomes.  THREE, not two -- FRAMING.md section 4.5 and section 11 require a size
# that was never attempted to be distinguishable from one that ran and from one that
# voided.
# =======================================================================================

MEASURED = "measured"
VOID = "void"
NOT_ATTEMPTED = "not-attempted"


def cell_measured(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = {"outcome": MEASURED}
    out.update(payload)
    return out


def cell_void(reason: str, detail: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {"outcome": VOID, "void_reason": reason, "void_detail": detail}
    if payload:
        out.update(payload)
    return out


def cell_not_attempted(detail: str) -> Dict[str, Any]:
    return {"outcome": NOT_ATTEMPTED, "detail": detail}


def is_measured(cell: Dict[str, Any]) -> bool:
    return cell.get("outcome") == MEASURED


# =======================================================================================
# Statistics.  FRAMING.md section 5.2: the headline is the MEDIAN, never the mean, and a
# p95 is printed ONLY where n >= 20 -- below that it is the maximum wearing a misleading
# name, and this project has already been burned once by a number that was really a
# measurement of its own instrument.
# =======================================================================================

P95_MIN_N = 20


def stats(xs: List[float]) -> Dict[str, Any]:
    xs = sorted(xs)
    n = len(xs)
    out: Dict[str, Any] = {
        "n": n,
        "min": round(xs[0], 2),
        "median": round(statistics.median(xs), 2),
        "max": round(xs[-1], 2),
        "stdev": round(statistics.stdev(xs), 2) if n > 1 else 0.0,
    }
    if n >= P95_MIN_N:
        # real order statistic, inclusive method
        out["p95"] = round(statistics.quantiles(xs, n=100, method="inclusive")[94], 2)
    else:
        out["worst_of_n"] = out["max"]
        out["p95_note"] = f"not reported: n={n} < {P95_MIN_N}, a p95 here would just be the max"
    return out


def aggregate(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Statistics over MEASURED cells only.

    FRAMING.md section 6.1: a cell that prints `void` and still contributes to the median
    is WORSE than one that never voided, because it looks handled.  The excluded count is
    reported so the exclusion is visible rather than silent.
    """
    good = [c for c in cells if is_measured(c)]
    excluded = len(cells) - len(good)
    if not good:
        return {"outcome": VOID, "void_reason": "no_admissible_reps",
                "void_detail": f"all {len(cells)} repetitions voided", "excluded": excluded}
    agg = stats([c["ms"] for c in good])
    agg["excluded_void_reps"] = excluded
    agg["outcome"] = MEASURED
    return agg


# =======================================================================================
# Host + server state.  FRAMING.md section 5.4 items 1-18.
# =======================================================================================

def _sh(cmd: List[str], timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception as exc:                      # never let telemetry kill a run
        return f"<unavailable: {exc}>"


def top_processes(k: int = 3) -> List[str]:
    out = _sh(["ps", "-eo", "pcpu,pid,comm", "--sort=-pcpu"])
    return [ln.strip() for ln in out.splitlines()[1:k + 1]]


def glp_strong_activity() -> Dict[str, Any]:
    """FRAMING.md section 5.4 item 16 -- the ONE narrow exception to 'no procedure points at
    the live container'.  Two read-only counters, nothing else, so that 'GIMS was idle
    during the window' becomes a measurement instead of an assumption.  No write, no
    CREATE, no load.  Stated in full so nobody widens it.
    """
    out = _sh(["docker", "exec", "glp-strong-db", "psql", "-U", "glp_owner",
               "-d", "glp_strong", "-tAc",
               "SELECT numbackends, xact_commit FROM pg_stat_database WHERE datname='glp_strong'"])
    if "|" in out:
        a, b = out.split("|")[:2]
        try:
            return {"numbackends": int(a), "xact_commit": int(b)}
        except ValueError:
            pass
    return {"raw": out}


def disk_state() -> Dict[str, Any]:
    out = _sh(["df", "-B1", "--output=size,avail,pcent", "/"])
    lines = out.splitlines()
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 3:
            return {"total_bytes": int(parts[0]), "avail_bytes": int(parts[1]), "used_pct": parts[2]}
    return {"raw": out}


def docker_state() -> Dict[str, Any]:
    return {
        "ps": _sh(["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"]).splitlines(),
        "stats": _sh(["docker", "stats", "--no-stream", "--format",
                      "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"], timeout=45).splitlines(),
    }


def host_state(conn, label: str) -> Dict[str, Any]:
    l1, l5, l15 = read_loadavg()
    return {
        "label": label,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "loadavg": {"1min": l1, "5min": l5, "15min": l15},
        "nproc": os.cpu_count(),
        "top_processes": top_processes(3),
        "disk": disk_state(),
        "docker": docker_state(),
        "glp_strong": glp_strong_activity(),
    }


def server_state(conn) -> Dict[str, Any]:
    """FRAMING.md section 5.4 items 4-9, read from THIS container.  The framing's own table
    carries values from glp-strong-db, which is NOT the server this run uses -- inheriting
    a setting from a server you are not measuring on is the same class of error as
    inheriting a load average.
    """
    cur = conn.cursor()
    out: Dict[str, Any] = {}
    for s in ("server_version", "synchronize_seqscans", "shared_buffers", "work_mem",
              "max_parallel_workers_per_gather", "max_parallel_maintenance_workers",
              "extra_float_digits"):
        cur.execute(f"SHOW {s}")
        out[s] = cur.fetchone()[0]
    out["dev_shm"] = _sh(["docker", "exec", "autosql-corpus", "df", "-h", "/dev/shm"]).splitlines()[-1:]
    out["container"] = _sh(["docker", "inspect", "autosql-corpus", "--format",
                            "{{.Name}}|{{.Config.Image}}|{{.Image}}|{{.HostConfig.ShmSize}}"])
    return out


def script_fingerprints() -> Dict[str, str]:
    import hashlib
    out = {}
    for rel in ("../T-1/proto/compile.py", "../T-1/proto/runtime.sql", "../T-1/proto/bench.py",
                "../T-1/proto/gen_data.py", "../T-1/proto/load_data.py",
                "gen_data_t4.py", "bench_t4.py"):
        p = os.path.normpath(os.path.join(_HERE, rel))
        try:
            with open(p, "rb") as fh:
                out[os.path.relpath(p, os.path.join(_HERE, "..", ".."))] = \
                    hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            pass
    return out


# =======================================================================================
# THE FIVE ARMS.
#
# A and B2 and B4 run through the FROZEN harness.  The frozen module reads its widget from
# a module global at call time, so `with widget(w):` rebinds it for the duration and puts
# it back -- the code being timed is byte-identical to the code the original sweep timed.
# =======================================================================================

class widget:
    """Rebind the frozen harness's widget globals for the duration of a block."""

    def __init__(self, spec: Dict[str, Any]):
        self.spec = spec

    def __enter__(self):
        self._old_widget = B.WIDGET
        self._old_derive = B.DERIVE_NAME
        B.WIDGET = self.spec["widget"]
        B.DERIVE_NAME = self.spec["derive_name"]
        return self.spec

    def __exit__(self, *exc):
        B.WIDGET = self._old_widget
        B.DERIVE_NAME = self._old_derive
        return False


def arm_a(conn, table: str, spec) -> Dict[str, Any]:
    """A -- today.  Everything in Python, with the 20,000-row cap in place."""
    r = B.path_a(conn, table)
    return {"ms": r["t"]["total_ms"], "rows": r["rows"], "shape": {
        "truncated": r["truncated"], "rows_acquired": r["rows_acquired"],
        "rows_scanned": r["rows_scanned"], "rows_kept": r["rows_kept"]}}


def arm_a_uncapped(conn, table: str, spec) -> Dict[str, Any]:
    """A-uncapped -- the correctness-matched baseline, cap lifted.

    FINDINGS.md section 5.5 quotes about 16.7 s at 1M as ARITHMETIC, never measured; the
    owner approved the cap lift in Q16.  This turns his approved number into a measurement.
    """
    old = SRC.MAX_SCAN
    SRC.MAX_SCAN = 1 << 62
    try:
        r = B.path_a(conn, table)
    finally:
        SRC.MAX_SCAN = old
    return {"ms": r["t"]["total_ms"], "rows": r["rows"], "shape": {
        "truncated": r["truncated"], "rows_acquired": r["rows_acquired"],
        "rows_scanned": r["rows_scanned"], "rows_kept": r["rows_kept"]}}


def _arm_c_sql(table: str, spec) -> Tuple[str, Dict[str, Any]]:
    """Arm C's statement: the compiled derive and where, with NO order by and NO limit.

    FINDINGS.md section 5.7 condition 3 keeps sort and limit OUT of the compiled path until
    ten separate ordering obligations are compiled and tested -- Postgres and Python sort
    mixed-type JSON differently at 9 of 9 tested positions.  So the honest shippable shape
    is SQL for the derive and the predicate, Python for the sort and the limit.
    """
    sql, params = B.build_b("B2", table)
    body = sql.split(" ORDER BY ")[0]          # drop ORDER BY ... LIMIT n
    return body, params


def arm_c(conn, table: str, spec) -> Dict[str, Any]:
    """C -- the shippable compiled path.  THE ARM THE BAR APPLIES TO.

    Its Python tail is a real part of what a person waits: at 1M with ~5% selectivity about
    52,000 rows come back and are decoded in Python.  A ratio hides that tail; an absolute
    bar cannot.  That is one of the concrete reasons the owner's correction improves the
    experiment, so the tail is timed here rather than argued about.
    """
    sql, params = _arm_c_sql(table, spec)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    rows = [r[0] for r in cur.fetchall()]
    t_sql = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    rows = SRC._apply_sort(rows, spec["widget"]["sort"])
    rows = SRC._apply_limit(rows, spec["widget"]["limit"])
    t_py = (time.perf_counter() - t1) * 1000

    return {"ms": t_sql + t_py, "rows": rows,
            "split": {"sql_ms": round(t_sql, 2), "python_tail_ms": round(t_py, 2)},
            "shape": {"rows_from_sql": len(rows)}}


def arm_b2(conn, table: str, spec) -> Dict[str, Any]:
    """B2 -- fully compiled.  Postgres does everything including sort and limit.
    Reported, not gated: the ceiling if the ordering obligations are ever discharged."""
    r = B.path_b(conn, table, "B2")
    return {"ms": r["t"]["total_ms"], "rows": r["rows"]}


def _build_b4_generic(table: str, spec) -> Tuple[str, Dict[str, Any]]:
    expr = spec["b4_expr"]
    name = spec["derive_name"]
    params = {"coll": B.COLLECTION}
    where = spec["widget"]["where"]
    # the invented widget's predicate is `$.load_score > 195`
    thresh = where.rsplit(">", 1)[1].strip()
    sql = (f"SELECT data || jsonb_build_object('{name}', to_jsonb({expr})) "
           f"FROM {table} WHERE collection = %(coll)s AND {expr} > {thresh} "
           f"ORDER BY {expr} {spec['b4_desc'].upper()} LIMIT {int(spec['widget']['limit'])}")
    return sql, params


def arm_b4(conn, table: str, spec) -> Dict[str, Any]:
    """B4 -- native operators.  The physics ceiling, NOT a candidate: it raises on a
    malformed value where the language must return null, which is the whole reason the
    safe xpr runtime exists."""
    if spec["b4_expr"] is None:
        r = B.path_b4(conn, table)
        return {"ms": r["t"]["total_ms"], "rows": r["rows"]}
    sql, params = _build_b4_generic(table, spec)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    rows = [r[0] for r in cur.fetchall()]
    return {"ms": (time.perf_counter() - t0) * 1000, "rows": rows}


ARMS: Dict[str, Callable] = {
    "A": arm_a,
    "A_uncapped": arm_a_uncapped,
    "C": arm_c,
    "B2": arm_b2,
    "B4": arm_b4,
}

COMPILED_ARMS = ("C", "B2", "B4")     # the ones a query plan must be asserted on
GATED_ARM = "C"                       # the arm the bar applies to


# =======================================================================================
# Running one cell.
# =======================================================================================

NREPS = {20000: 25, 100000: 25, 1000000: 9}     # FRAMING.md section 5.2, RULED


def plan_for_arm(conn, table: str, spec, arm: str) -> Optional[Tuple[str, str]]:
    """Returns (plan_text, offending_line_or_None) for a compiled arm."""
    if arm == "C":
        sql, params = _arm_c_sql(table, spec)
    elif arm == "B2":
        sql, params = B.build_b("B2", table)
    elif arm == "B4":
        sql, params = (B.build_b4(table) if spec["b4_expr"] is None
                       else _build_b4_generic(table, spec))
    else:
        return None
    plan = capture_plan(conn, sql, params)
    return plan, index_help_in_plan(plan)


def run_cell(conn, table: str, n: int, spec, arm: str, reps: int) -> Dict[str, Any]:
    """One (size, widget, arm) cell.  Every admissibility gate is checked HERE, and a
    failure produces a void cell rather than a number."""
    fn = ARMS[arm]

    # -- gate: corpus completeness (section 6 item 2) -----------------------------------
    actual = read_row_count(conn, table)
    if actual != n:
        return cell_void("corpus_incomplete",
                         f"{table} holds {actual} rows, expected {n}")

    # -- gate: host load at start (section 6 item 1) ------------------------------------
    l1_start, _, _ = read_loadavg()
    if l1_start > LOAD_CEILING_START:
        return cell_void("host_load",
                         f"1-min load {l1_start} > {LOAD_CEILING_START} at start")

    # -- gate: no index help (section 6 item 4) -----------------------------------------
    plan_info = plan_for_arm(conn, table, spec, arm)
    plan_text = None
    buffers = None
    if plan_info is not None:
        plan_text, offending = plan_info
        buffers = buffers_from_plan(plan_text)
        if offending:
            return cell_void("index_help", f"plan uses an index other than the pkey: {offending}",
                             {"plan": plan_text})

    # -- warm once, discarded (section 5.3: cache state measured, never claimed) ---------
    fn(conn, table, spec)

    # -- the repetitions ----------------------------------------------------------------
    per_rep: List[Dict[str, Any]] = []
    last = None
    for _ in range(reps):
        r = fn(conn, table, spec)
        last = r
        per_rep.append(cell_measured({"ms": r["ms"]}))

    # -- gate: host load at end ---------------------------------------------------------
    l1_end, _, _ = read_loadavg()
    if l1_end > LOAD_CEILING_END:
        return cell_void("host_load",
                         f"1-min load {l1_end} > {LOAD_CEILING_END} at end",
                         {"load_start": l1_start})

    agg = aggregate(per_rep)
    out = cell_measured({
        "arm": arm,
        "size": n,
        "reps": reps,
        "stats": agg,
        "load_start": l1_start,
        "load_end": l1_end,
        "rows_returned": len(last["rows"]) if last else None,
    })
    if "split" in (last or {}):
        out["split"] = last["split"]
    if "shape" in (last or {}):
        out["shape"] = last["shape"]
    if plan_text is not None:
        out["plan"] = plan_text
        out["buffers"] = buffers
    return out


def identity_across_arms(results: Dict[str, Any], truth_arm: str = "B2") -> Dict[str, Any]:
    """Section 6 item 6: if the arms disagree, the timing comparison is between two
    different questions.  Compared as SETS keyed by id, because arm C sorts in Python and
    B2 sorts in Postgres, and the two disagree on ties by design -- that is the very
    reason sort is not in the compiled path."""
    ref = results.get(truth_arm, {}).get("_rows")
    if ref is None:
        return {"checked": False, "detail": f"{truth_arm} produced no rows to compare against"}
    out = {"checked": True, "reference": truth_arm, "arms": {}}
    ref_ids = sorted(r.get("id") for r in perturb_rows(ref))
    for arm, res in results.items():
        rows = res.get("_rows")
        if rows is None or arm == truth_arm:
            continue
        ids = sorted(r.get("id") for r in perturb_rows(rows))
        agree = ids == ref_ids
        out["arms"][arm] = {"agree": agree, "n": len(ids),
                            "detail": "identical id set" if agree
                            else f"{len(set(ids) ^ set(ref_ids))} ids differ"}
    out["all_agree"] = all(v["agree"] for v in out["arms"].values()) if out["arms"] else None
    return out


# =======================================================================================
# main
# =======================================================================================

def connect():
    import psycopg2
    conn = psycopg2.connect(B.DSN)
    cur = conn.cursor()
    cur.execute("SET extra_float_digits = 1")        # T-9 enforces this; pinned and recorded
    cur.execute("SET synchronize_seqscans = on")     # section 6 item 9: pinned AND recorded
    return conn


def main(argv: List[str]) -> int:
    sizes = [int(x) for x in (argv[1].split(",") if len(argv) > 1 else "20000,100000,1000000".split(","))]
    which = argv[2].split(",") if len(argv) > 2 else list(WIDGETS)

    conn = connect()
    report: Dict[str, Any] = {
        "run": "T-4 timing run",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bar_is": "ABSOLUTE MILLISECONDS, not a ratio (the owner's own correction, GA-3)",
        "gated_arm": GATED_ARM,
        "server": server_state(conn),
        "fingerprints": script_fingerprints(),
        "python": sys.version.split()[0],
        "max_scan": SRC.MAX_SCAN,
        "widgets": {k: {"invented": WIDGETS[k]["invented"], "spec": WIDGETS[k]["widget"]}
                    for k in which},
        "cells": {},
        "host": [],
    }

    for wkey in which:
        spec = WIDGETS[wkey]
        report["cells"][wkey] = {}
        with widget(spec):
            for n in sizes:
                table = f"measure_instances_{n}"
                reps = NREPS.get(n, 9)
                report["host"].append(host_state(conn, f"{wkey}/{n}/start"))
                print(f"--- {wkey} / {table} (reps={reps}) ---", flush=True)
                per_arm: Dict[str, Any] = {}
                for arm in ARMS:
                    cell = run_cell(conn, table, n, spec, arm, reps)
                    if is_measured(cell):
                        last = ARMS[arm](conn, table, spec)
                        cell["_rows"] = last["rows"]
                        med = cell["stats"]["median"]
                        print(f"   {arm:12s} median {med:10.2f} ms   (n={cell['stats']['n']})", flush=True)
                    else:
                        print(f"   {arm:12s} VOID  {cell['void_reason']}: {cell['void_detail']}", flush=True)
                    per_arm[arm] = cell
                ident = identity_across_arms(per_arm)
                for cell in per_arm.values():
                    cell.pop("_rows", None)
                if ident.get("all_agree") is False:
                    for arm, cell in per_arm.items():
                        if is_measured(cell) and not ident["arms"].get(arm, {}).get("agree", True):
                            per_arm[arm] = cell_void("arms_disagree",
                                                     ident["arms"][arm]["detail"])
                report["cells"][wkey][str(n)] = {"arms": per_arm, "identity": ident}
                report["host"].append(host_state(conn, f"{wkey}/{n}/end"))

    # sizes never attempted are a THIRD outcome, distinguishable from both others
    for wkey in which:
        for n in (20000, 100000, 1000000):
            if str(n) not in report["cells"][wkey]:
                report["cells"][wkey][str(n)] = {
                    "arms": {a: cell_not_attempted("size not in this run's size list")
                             for a in ARMS}}

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = os.path.join(_HERE, "measurements.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"\nwrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
