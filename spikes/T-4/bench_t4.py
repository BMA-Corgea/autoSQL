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


def perturb_rows(rows: List[dict], arm: str = "") -> List[dict]:
    """Identity by default.  SEAM: injection 4 swaps this to perturb ONE arm by one row.

    Applied to the ARMS ONLY -- never to the reference.  It was applied to both sides, and
    a seam applied symmetrically CANNOT FIRE: the same perturbation on the truth and on the
    arm still compares equal, so injection 4 would have reported the void path working
    while proving nothing.  That is the precise failure section 6.1 exists to catch, found
    in the harness that section 6.1's control was going to be run against.

    `arm` is passed so an injection can perturb one named arm rather than all of them,
    which is what section 6.1's table actually specifies ("one arm's result perturbed").
    """
    return rows


# ---- what the seams are checked against ----------------------------------------------

def index_help_in_plan(plan: str) -> Optional[str]:
    """Q11 put indexes permanently off, so a generated query must be a sequential scan
    every time.  The corpus KEEPS the production GIN index (the real instances table has
    one) precisely so the run can DEMONSTRATE it is unused rather than assume it.

    Returns the offending line, or None if the plan is clean.  A primary-key lookup doing
    the `collection = ...` restriction is the one allowed index use.
    """
    for idx, raw in enumerate(plan.splitlines()):
        line = raw.strip()
        low = line.lower()
        if "index scan" not in low and "index only scan" not in low:
            continue
        # "->  Index Scan using measure_instances_1000_pkey on ..." is the allowed one --
        # but ONLY when it is doing the `collection = ...` restriction section 6 item 4
        # actually permits.  A bare `"_pkey" in line` test would wave through a pkey index
        # used for anything at all, and the guard is the whole evidence for Q11's world.
        if "_pkey" in low:
            cond = " ".join(plan.splitlines()[idx + 1:idx + 3]).lower()
            if "index cond" in cond and "collection" in cond:
                continue
            return f"{line}   [pkey index NOT doing the collection lookup]"
        return line
    return None


def buffers_from_plan(plan: str) -> Dict[str, int]:
    """shared hit/read, per FRAMING.md section 5.4 item 13 -- cache state is MEASURED,
    never claimed (section 6 item 8).

    POSTGRES REPORTS BUFFER COUNTS CUMULATIVELY: a parent node's `Buffers:` line already
    contains every child's.  Summing the lines therefore multiplies the true figure by the
    plan depth.  Measured in this run's own committed evidence before the fix: the date
    control's 1M B2 plan carries `shared hit=2465 read=55215` FOUR times and the cell
    reported shared_read=220860 -- 1.7 GB of reads against a 700 MB table, which is not a
    possible number.  Single-node plans (arm C has no ORDER BY, so no Limit/Sort above the
    scan) were correct by accident, which is exactly how it survived review-by-reading.

    The ROOT node is printed first in EXPLAIN text output, so its line -- the first one --
    is the whole-plan total.  `temp read=`/`written=` share the line and are kept separate:
    a sort spilling to disk is not a shared-buffer read.
    """
    out = {"shared_hit": 0, "shared_read": 0, "temp_read": 0, "temp_written": 0}
    for raw in plan.splitlines():
        if "buffers:" not in raw.lower():
            continue
        section = None
        toks = raw.lower().replace("=", " ").replace(",", " ").split()
        for i, t in enumerate(toks):
            if t in ("shared", "local", "temp"):
                section = t
            elif t in ("hit", "read", "written", "dirtied") and i + 1 < len(toks):
                nxt = toks[i + 1]
                if not nxt.isdigit():
                    continue
                if section == "shared" and t in ("hit", "read"):
                    out[f"shared_{t}"] = int(nxt)
                elif section == "temp" and t in ("read", "written"):
                    out[f"temp_{t}"] = int(nxt)
        break          # ROOT node only -- the counts are already cumulative
    return out


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


def memory_state() -> Dict[str, Any]:
    """FRAMING.md section 5.4 item 2 -- 'nproc, total and available RAM, free disk'.  The
    RAM half was absent, and a load average means nothing without it."""
    out: Dict[str, Any] = {}
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    out[k] = int(v.split()[0]) * 1024
    except OSError as exc:
        out["error"] = str(exc)
    return out


def disk_io() -> Dict[str, Any]:
    """FRAMING.md section 5.4 item 17 -- free space AND I/O ACTIVITY.  disk_state() recorded
    only free space; the corpus, its CSVs, glp_strong's data and the OS all sit on the one
    filesystem, and contention there is precisely what host loadavg is worst at showing.
    Cumulative counters: a reader diffs the start and end records for the window."""
    out: Dict[str, Any] = {}
    try:
        with open("/proc/diskstats") as fh:
            for line in fh:
                f = line.split()
                if len(f) < 14:
                    continue
                name = f[2]
                if name.startswith(("loop", "ram", "dm-")):
                    continue
                reads, writes = int(f[5]), int(f[9])       # sectors read / written
                if reads or writes:
                    out[name] = {"sectors_read": reads, "sectors_written": writes,
                                 "ms_io": int(f[12])}
    except OSError as exc:
        out["error"] = str(exc)
    return out


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
        "memory": memory_state(),
        "disk": disk_state(),
        "disk_io": disk_io(),
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


SELECTIVITY_BAND = (4.5, 6.0)        # FRAMING.md section 6 item 2


def corpus_state(conn, table: str, spec, n: int) -> Dict[str, Any]:
    """FRAMING.md section 5.4 item 12 and section 6 item 2 -- row count, MEASURED
    selectivity, and mean stored JSON bytes per row.  None of the three was recorded
    anywhere in the output, and section 5.4 opens 'every one of these, in the output JSON,
    per size, or the cell is not admissible'.  Selectivity and payload size silently move
    every number in the run, and adding the two generator fields moved both.
    """
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table}")
    rows = int(cur.fetchone()[0])
    sql, params = _t4_build_b2(table, spec, order=False, count_only=True)
    cur.execute(sql, params)
    qualifying = int(cur.fetchone()[0])
    cur.execute(f"SELECT avg(pg_column_size(data)), avg(octet_length(data::text)) FROM {table}")
    stored, as_text = cur.fetchone()
    sel = (100.0 * qualifying / rows) if rows else None
    lo, hi = SELECTIVITY_BAND
    return {
        "table": table, "rows": rows, "rows_expected": n,
        "qualifying_rows": qualifying,
        "selectivity_pct": round(sel, 3) if sel is not None else None,
        "selectivity_band": list(SELECTIVITY_BAND),
        "selectivity_in_band": (sel is not None and lo <= sel <= hi),
        "mean_stored_bytes": round(float(stored), 2) if stored is not None else None,
        "mean_json_text_bytes": round(float(as_text), 2) if as_text is not None else None,
        "stored_bytes_note": ("mean_stored_bytes is pg_column_size(data) -- the on-disk "
                              "datum, TOAST compression included; mean_json_text_bytes is "
                              "the uncompressed JSON text the generator reports"),
    }


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


def _sort_sql_dir(v: str, direction: str) -> str:
    """B.sort_sql with an explicit direction on each of its three rank terms.

    Mirrors bench.py:111-118 term for term.  The frozen one emits no direction at all, so
    it is ASC-only -- and the invented widget sorts DESC (FRAMING.md section 7.2).  The
    direction cannot be bolted on by splitting the frozen function's output on commas,
    because the expression substituted into it is compiled SQL that contains commas of its
    own (`xpr.pdate_ms(a, b)`).  Faithfulness is asserted rather than claimed:
    _assert_builder_faithful() checks this returns B.sort_sql(v) exactly when asc.
    """
    d = " DESC" if str(direction).lower() == "desc" else ""
    ty = f"jsonb_typeof({v})"
    r1 = (f"(CASE WHEN {v} IS NULL OR {ty}='null' THEN 4 WHEN {ty}='boolean' THEN 0 "
          f"WHEN {ty}='number' THEN 1 WHEN {ty}='string' THEN 2 ELSE 3 END)")
    r2 = (f"(CASE WHEN {ty}='boolean' THEN (CASE WHEN {v}='true'::jsonb THEN 1.0 ELSE 0.0 END) "
          f"WHEN {ty}='number' THEN xpr.f8({v}) ELSE 0.0 END)")
    r3 = f"(CASE WHEN {ty}='string' THEN ({v} #>> '{{}}') ELSE '' END) COLLATE \"C\""
    if not d:
        return f"{r1}, {r2}, {r3}"
    return f"{r1}{d}, {r2}{d}, {r3}{d}"


def _t4_build_b2(table: str, spec, tie: bool = False, order: bool = True,
                 count_only: bool = False):
    """B2 for an ARBITRARY widget spec, built from the frozen module's own primitives.

    Why this exists rather than a call to B.build_b: bench.py:242 reads
    WIDGET["filters"]["status"] unconditionally, so the frozen builder raises
    KeyError('status') on the invented widget -- whose spec (FRAMING.md section 7.2) carries
    no filters at all.  Measured, before this was written: arms C and B2 both raised, which
    means THE ARM THE BAR APPLIES TO could not run on the widget the bar is about.  bench.py
    is FROZEN EVIDENCE and cannot be edited, so this drives its parts instead -- the same
    EXPR.parse, the same CC.compile_ast, the same subst, the same params tagging.

    Faithfulness is asserted, not asserted-in-a-comment: for the date control this returns
    SQL and params byte-identical to B.build_b("B2", table, tie).  See
    _assert_builder_faithful(), which runs before any cell is timed.
    """
    w = spec["widget"]
    name = spec["derive_name"]
    d_ast = B.EXPR.parse(w["derive"][name])
    w_ast = B.EXPR.parse(w["where"])
    params: Dict[str, Any] = {"coll": B.COLLECTION, "ctx": json.dumps(B.CTX)}

    def take(c, tag: str) -> str:
        sql = c.sql
        for k, v in c.params.items():
            params[f"{tag}_{k}"] = v
            sql = sql.replace(f"%({k})s", f"%({tag}_{k})s")
        return sql

    w_in = B.subst(w_ast, name, d_ast)
    w_sql = take(B.CC.compile_ast(w_in, column="data"), "w")
    d_sql_sort = take(B.CC.compile_ast(d_ast, column="data"), "s")
    d_sql_out = take(B.CC.compile_ast(d_ast, column="data"), "o")
    aug = f"(data || jsonb_build_object('{name}', {d_sql_out}))"

    filters = w.get("filters") or {}
    unknown = set(filters) - {"status"}
    if unknown:
        raise ValueError(f"_t4_build_b2 cannot express filters {sorted(unknown)}")
    if "status" in filters:
        params["fstatus"] = json.dumps(filters["status"])
        filt = " AND (data -> 'status') = %(fstatus)s::jsonb"
    else:
        filt = ""

    projection = "count(*)" if count_only else aug
    sql = (f"SELECT {projection} FROM {table} WHERE collection = %(coll)s{filt} "
           f"AND xpr.truthy({w_sql})")
    if order:
        sql += (f" ORDER BY {_sort_sql_dir(d_sql_sort, w['sort'].get('dir', 'asc'))}"
                f"{B.TIE if tie else ''} LIMIT {int(w['limit'])}")
    return sql, params


def _assert_builder_faithful() -> Dict[str, Any]:
    """The extension above must reproduce the frozen builder exactly where the frozen
    builder can run, or the date control stops being a control.  Checked for both tie
    settings on the date widget, against B.build_b itself."""
    out = {}
    with widget(WIDGET_DATE):
        for tie in (False, True):
            want_sql, want_params = B.build_b("B2", "T", tie)
            got_sql, got_params = _t4_build_b2("T", WIDGET_DATE, tie)
            if got_sql != want_sql or got_params != want_params:
                raise AssertionError(
                    "t4 B2 builder diverges from the frozen one for the date control "
                    f"(tie={tie}).\n  frozen: {want_sql}\n  t4    : {got_sql}")
            out[f"b2_tie_{tie}"] = "byte-identical to frozen build_b"
        v = "xpr.f8(data -> 'x')"
        if _sort_sql_dir(v, "asc") != B.sort_sql(v):
            raise AssertionError("t4 sort_sql(asc) diverges from the frozen sort_sql")
        out["sort_sql_asc"] = "byte-identical to frozen sort_sql"

        # The two branches ABOVE are the only ones the date control exercises.  The invented
        # widget takes two the frozen builder cannot build at all -- DESC ordering and an
        # ABSENT filter -- so there is nothing to compare them against, and a defect in
        # either would surface only as an arms-disagreement.  They are therefore checked
        # DIFFERENTIALLY against the frozen output: same statement, one property changed.
        desc = _sort_sql_dir(v, "desc")
        if desc.count(" DESC") != 3:
            raise AssertionError(
                f"DESC must reach all THREE rank terms of the frozen sort, got "
                f"{desc.count(' DESC')} -- a direction on only the last term silently "
                f"orders by type-rank ascending")
        if desc.replace(" DESC", "") != B.sort_sql(v):
            raise AssertionError("t4 sort_sql(desc) is not the frozen sort plus directions")
        out["sort_sql_desc"] = "frozen sort_sql + DESC on each of its 3 rank terms"

        nofilter = {**WIDGET_DATE, "widget": {**WIDGET_DATE["widget"], "filters": {}}}
        got, got_p = _t4_build_b2("T", nofilter)
        want, want_p = B.build_b("B2", "T")
        expect = want.replace(" AND (data -> 'status') = %(fstatus)s::jsonb", "")
        if got != expect:
            raise AssertionError(
                f"the no-filter branch is not the frozen statement minus its filter "
                f"conjunct.\n  expected: {expect}\n  got     : {got}")
        if "fstatus" in got_p or set(want_p) - set(got_p) != {"fstatus"}:
            raise AssertionError(f"no-filter params wrong: {sorted(got_p)}")
        out["no_filter_branch"] = "frozen statement minus exactly its status conjunct"
    return out


def _arm_c_sql(table: str, spec) -> Tuple[str, Dict[str, Any]]:
    """Arm C's statement: the compiled derive and where, with NO order by and NO limit.

    FINDINGS.md section 5.7 condition 3 keeps sort and limit OUT of the compiled path until
    ten separate ordering obligations are compiled and tested -- Postgres and Python sort
    mixed-type JSON differently at 9 of 9 tested positions.  So the honest shippable shape
    is SQL for the derive and the predicate, Python for the sort and the limit.

    The clauses are omitted at BUILD time (order=False) rather than cut off the finished
    statement with `sql.split(" ORDER BY ")`, which is a text search over compiled SQL that
    happens to contain no such literal today and carries no guarantee it never will.
    """
    return _t4_build_b2(table, spec, order=False)


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
    n_from_sql = len(rows)          # BEFORE the limit -- see below

    t1 = time.perf_counter()
    rows = SRC._apply_sort(rows, spec["widget"]["sort"])
    rows = SRC._apply_limit(rows, spec["widget"]["limit"])
    t_py = (time.perf_counter() - t1) * 1000

    # rows_from_sql is captured before _apply_limit.  It was read after it, which made it
    # report 50 at every size -- the count of what SQL returned, wearing the value of what
    # survived the limit.  The ~52,000 rows this arm decodes in Python at 1M IS the tail
    # this arm exists to time, so the number that names it has to be the real one.
    return {"ms": t_sql + t_py, "rows": rows,
            "split": {"sql_ms": round(t_sql, 2), "python_tail_ms": round(t_py, 2)},
            "shape": {"rows_from_sql": n_from_sql, "rows_after_limit": len(rows)}}


def arm_b2(conn, table: str, spec) -> Dict[str, Any]:
    """B2 -- fully compiled.  Postgres does everything including sort and limit.
    Reported, not gated: the ceiling if the ordering obligations are ever discharged."""
    sql, params = _t4_build_b2(table, spec)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    rows = [r[0] for r in cur.fetchall()]
    return {"ms": (time.perf_counter() - t0) * 1000, "rows": rows}


def _build_b4_generic(table: str, spec, tie: bool = False) -> Tuple[str, Dict[str, Any]]:
    expr = spec["b4_expr"]
    name = spec["derive_name"]
    params = {"coll": B.COLLECTION}
    where = spec["widget"]["where"]
    # `where.rsplit(">", 1)` is correct for `$.load_score > 195` and silently wrong for
    # anything else: on `>=` it yields the threshold "= 195", and on a compound predicate it
    # measures a different question.  Because B4 is held to identity, a mis-built B4 would
    # surface as "arms disagree" rather than as the build error it is.  So the shape this
    # builder can express is CHECKED, and anything else refuses to build.
    import re as _re
    m = _re.fullmatch(r"\s*\$\.(\w+)\s*(>|<|>=|<=)\s*(-?[0-9.]+)\s*", where)
    if not m or m.group(1) != name:
        raise ValueError(
            f"_build_b4_generic can only express `$.{name} <op> <number>`; refusing to "
            f"guess at {where!r}")
    op, thresh = m.group(2), m.group(3)
    sql = (f"SELECT data || jsonb_build_object('{name}', to_jsonb({expr})) "
           f"FROM {table} WHERE collection = %(coll)s AND {expr} {op} {thresh} "
           f"ORDER BY {expr} {spec['b4_desc'].upper()}{B.TIE if tie else ''} "
           f"LIMIT {int(spec['widget']['limit'])}")
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
        sql, params = _t4_build_b2(table, spec)
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
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())   # section 5.4 item 10

    # -- guard: the arm must be timing the widget it was handed -------------------------
    # Arms A, B2 and B4 read the widget from the FROZEN module's global, not from `spec`,
    # so calling one outside `with widget(spec):` silently times a DIFFERENT widget while
    # reporting this one's name.  Section 6 item 3 makes a latency figure attributed to the
    # wrong widget the most serious failure available to this run, so it is asserted rather
    # than left to call-site discipline.  (Caught in smoke: every arm ran the date widget
    # while being handed the invented spec.)
    if B.WIDGET is not spec["widget"] or B.DERIVE_NAME != spec["derive_name"]:
        raise AssertionError(
            f"arm {arm} would time widget {B.DERIVE_NAME!r} while reporting "
            f"{spec['derive_name']!r} -- call inside `with widget(spec):`")

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

    # -- warm once, RECORDED (section 5.3 ruling item 2) ---------------------------------
    # The frozen harness throws the warm-up away.  It is the closest thing to a cold
    # reading available and it costs nothing to keep, so it is labelled warmup_ms and
    # excluded from the median rather than discarded.
    try:
        warm = fn(conn, table, spec)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return cell_void("rep_error", f"warm-up raised {type(exc).__name__}: {exc}",
                         {"arm": arm, "size": n, "reps": reps, "started_utc": started})
    warmup_ms = round(warm["ms"], 2)
    # For C, B2 and B4 an EXPLAIN (ANALYZE) of the identical statement ran just above, which
    # is a FULL execution -- so their warm-up is a second warm run, while A and A_uncapped
    # (no plan captured) get a genuinely first one.  The field is captioned "the closest
    # thing to a cold reading available" and would be read that way across all five.
    warmup_preceded_by_explain = plan_text is not None

    # -- the repetitions ----------------------------------------------------------------
    per_rep: List[Dict[str, Any]] = []
    last = None
    for _ in range(reps):
        try:
            r = fn(conn, table, spec)
        except Exception as exc:
            # One raise used to end the run and discard every millisecond already measured,
            # inside a 2-3 hour EXCLUSIVE window that cannot simply be re-booked (section 3).
            # B4 is the documented candidate: `::numeric` RAISES where the language must
            # return null.  psycopg2 also leaves the connection in a failed transaction, so
            # every later statement would error until a rollback that never came.
            #
            # This is ALSO what makes section 6.1's exclusion clause reachable: it is the one
            # mechanism by which a single REP can void, so `excluded_void_reps` and
            # `no_admissible_reps` stop being dead surface.  It adds no gate -- a rep voids
            # only when it actually failed.
            try:
                conn.rollback()
            except Exception:
                pass
            per_rep.append(cell_void("rep_error", f"{type(exc).__name__}: {exc}"))
            continue
        last = r
        per_rep.append(cell_measured({"ms": r["ms"]}))
    if last is None:
        return cell_void("rep_error", "every repetition raised",
                         {"arm": arm, "size": n, "reps": reps, "started_utc": started})

    # -- gate: host load at end ---------------------------------------------------------
    l1_end, _, _ = read_loadavg()
    if l1_end > LOAD_CEILING_END:
        return cell_void("host_load",
                         f"1-min load {l1_end} > {LOAD_CEILING_END} at end",
                         {"load_start": l1_start})

    agg = aggregate(per_rep)
    if agg.get("outcome") == VOID:
        # aggregate() can return a VOID verdict (no_admissible_reps).  Wrapping that in
        # cell_measured() produced a cell whose top-level outcome read `measured` while its
        # statistics said void -- is_measured() returned True and it would have counted.
        return cell_void(agg["void_reason"], agg["void_detail"],
                         {"arm": arm, "size": n, "reps": reps, "started_utc": started})
    out = cell_measured({
        "arm": arm,
        "size": n,
        "reps": reps,
        "started_utc": started,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "warmup_ms": warmup_ms,
        "warmup_preceded_by_explain": warmup_preceded_by_explain,
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


# The arms that are HELD TO IDENTITY.  Arm A is deliberately not among them -- see
# identity_check.  A_uncapped is the correctness-matched Python baseline and is.
UNCAPPED_ARMS = ("A_uncapped", "C", "B2", "B4")
# The oracle is the REAL in-memory GIMS pipeline with the cap lifted -- NOT B2.
# B2 and arm C are built by the same function (_t4_build_b2), so with B2 as the reference a
# builder defect would make arm C agree BY CONSTRUCTION while the two independent
# implementations -- A_uncapped (the actual Python the compiled path must reproduce) and B4
# (native operators) -- disagreed and were voided as the dissenters.  The gate was oriented
# to bless the arm under test.  Identity means "the compiled path reproduces Python", so
# Python is the reference.
TRUTH_ARM = "A_uncapped"


def _t4_sorted_tiebroken(rows: List[dict], spec) -> List[dict]:
    """The widget's sort, then $.id ascending, deterministically.

    bench.py:416 does exactly this for the asc case and says why (bench.py:192-196):
    Python's sorted() is stable and Postgres' sort is not, so a tie spanning the LIMIT
    boundary makes a row-for-row comparison meaningless.  The frozen helper asserts the
    sort is ascending (bench.py:407) and the invented widget sorts DESC, so the extension
    is here.  sorted() being stable is what makes it correct: sorting on id first and then
    on the sort key leaves id ascending inside every tie group, which is what SQL's
    `ORDER BY key <dir>, id ASC` produces.
    """
    field = str(spec["widget"]["sort"]["field"])
    desc = str(spec["widget"]["sort"].get("dir", "asc")).lower() == "desc"
    rows = sorted(rows, key=lambda r: str(SRC._field_value(r, "id")))
    return sorted(rows, key=lambda r: SRC._sort_key(SRC._field_value(r, field)), reverse=desc)


def _arm_rows_tiebroken(conn, table: str, spec, arm: str) -> List[dict]:
    """Each arm's answer in a deterministic order.  NEVER timed -- bench.py:194 keeps the
    tiebreak out of the timing statement, and so does this."""
    limit = int(spec["widget"]["limit"])
    w = spec["widget"]
    if arm in ("A", "A_uncapped"):
        old = SRC.MAX_SCAN
        if arm == "A_uncapped":
            SRC.MAX_SCAN = 1 << 62
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT data FROM {table} WHERE collection = %s", (B.COLLECTION,))
            raw = [r[0] for r in cur.fetchall()]
            rows = raw[:SRC.MAX_SCAN] if len(raw) > SRC.MAX_SCAN else raw
            rows = SRC._apply_derive(rows, w["derive"], B.CTX)
            rows = SRC._filter_rows(rows, w.get("filters"), w["where"], B.CTX)
        finally:
            SRC.MAX_SCAN = old
        return _t4_sorted_tiebroken(rows, spec)[:limit]
    if arm == "C":
        sql, params = _arm_c_sql(table, spec)
        cur = conn.cursor(); cur.execute(sql, params)
        return _t4_sorted_tiebroken([r[0] for r in cur.fetchall()], spec)[:limit]
    if arm == "B2":
        sql, params = _t4_build_b2(table, spec, tie=True)
    elif arm == "B4":
        sql, params = (B.build_b4(table, True) if spec["b4_expr"] is None
                       else _build_b4_generic(table, spec, tie=True))
    else:
        raise ValueError(arm)
    cur = conn.cursor(); cur.execute(sql, params)
    return [r[0] for r in cur.fetchall()]


def identity_check(conn, table: str, spec) -> Dict[str, Any]:
    """FRAMING.md section 6 item 6, run ONCE per size on the tiebroken arms.

    TWO corrections to what this replaced, both of which would have destroyed the run.

    1.  It compared the TIMING arms' rows.  Arm C sorts in Python and B2 sorts in Postgres,
        so ties spanning the LIMIT boundary put different-but-equally-correct rows in the
        last places -- which the old docstring acknowledged and then compared anyway.
        MEASURED before this was rewritten: arm C "disagreed" with B2 on 8 of 50 ids at
        20,000 rows, and the old code voided the disagreeing arm.  Arm C is THE ARM THE BAR
        APPLIES TO, so the run would have voided its own headline for tie order.  The frozen
        harness had already solved this -- build_b(tie=), path_a_tiebreak, ground_truth --
        and the fix is to use that mechanism rather than to invent another.

    2.  It held ARM A to identity.  Arm A is the capped path.  Above 20,000 rows it is
        SUPPOSED to disagree: recall 38% at 100k and 4% at 1M (FRAMING.md section 4.1) is
        the correctness failure this whole project exists to fix.  Voiding it for that would
        delete the same-session Python median that section 4.2's kill condition is DEFINED
        against ("strictly below the same-session Python median"), leaving the run unable to
        evaluate its own kill condition at the two sizes that decide it.  Section 6 item 6's
        actual words scope identity to "arms where Python is correct (<= 20,000 rows)" and
        to "ground truth computed by an uncapped query above the cap".  So arm A's agreement
        is REQUIRED at and below the cap, and MEASURED as recall above it.
    """
    truth = _arm_rows_tiebroken(conn, table, spec, TRUTH_ARM)
    truth_ids = [r.get("id") for r in truth]        # the reference is NOT perturbed
    capped = SRC.MAX_SCAN
    n_rows = read_row_count(conn, table)
    # Whether the cap ACTUALLY truncated arm A, from the same expression the frozen
    # path_a uses (`len(raw) > MAX_SCAN` over the COLLECTION, bench.py:146) -- not from the
    # table's total row count, which includes any row outside `collection = noun:Sample`.
    # This is the one place the arm-A exemption could leak: an over-count would set
    # cap_binds True and silently exempt arm A at a size where identity IS required.
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {table} WHERE collection = %s", (B.COLLECTION,))
    n_in_collection = int(cur.fetchone()[0])
    cap_binds = n_in_collection > capped
    out: Dict[str, Any] = {
        "checked": True, "reference": TRUTH_ARM, "tiebroken": True,
        "held_to_identity": list(UNCAPPED_ARMS),
        "arms": {}, "arm_a_recall": None,
    }
    for arm in UNCAPPED_ARMS:
        if arm == TRUTH_ARM:
            continue
        rows = perturb_rows(_arm_rows_tiebroken(conn, table, spec, arm), arm)
        ids = [r.get("id") for r in rows]
        # ROW-FOR-ROW, per section 6 item 6's actual words -- via the frozen comparator,
        # which compares every field with the fixture's float epsilon.  An id-list check
        # cannot see a wrong DERIVED VALUE: a compiled derive emitting 195.0 where Python
        # has 195, or null where Python has 0, keeps top-50 membership and order identical
        # while the two arms return different documents -- and the derived value is the
        # number the widget puts on the screen.
        same_rows, why = B.rows_match(rows, truth)
        agree = (ids == truth_ids) and same_rows
        if agree:
            detail = "identical rows, tiebroken (every field, frozen rows_match)"
        elif ids != truth_ids:
            only = len(set(ids) - set(truth_ids))
            detail = (f"{only} id(s) present here and not in the reference; "
                      f"{sum(1 for a, b in zip(ids, truth_ids) if a != b)} positions differ")
        else:
            detail = f"same ids, DIFFERENT VALUES: {why}"
        out["arms"][arm] = {"agree": agree, "n": len(ids), "detail": detail}
    out["all_agree"] = all(v["agree"] for v in out["arms"].values()) if out["arms"] else None

    # Arm A: measured, never gated.  This is the correctness number the run exists beside.
    a_ids = [r.get("id") for r in
             perturb_rows(_arm_rows_tiebroken(conn, table, spec, "A"), "A")]
    hit = len(set(a_ids) & set(truth_ids))
    out["arm_a_recall"] = {
        "capped_at": capped, "rows_in_table": n_rows,
        "rows_in_collection": n_in_collection,
        "cap_binds": cap_binds,
        "overlap_with_truth": hit, "of": len(truth_ids),
        "recall_pct": round(100.0 * hit / len(truth_ids), 1) if truth_ids else None,
        "note": ("arm A is the capped path; above the cap it is EXPECTED to disagree and is "
                 "not held to identity -- section 4.2 needs its median as the same-session "
                 "Python baseline"),
    }
    if not out["arm_a_recall"]["cap_binds"]:
        out["arms"]["A"] = {
            "agree": a_ids == truth_ids, "n": len(a_ids),
            "detail": "identical id list, tiebroken" if a_ids == truth_ids
            else f"{len(set(a_ids) ^ set(truth_ids))} ids differ AT OR BELOW THE CAP, "
                 f"where section 6 item 6 requires identity",
        }
        out["all_agree"] = all(v["agree"] for v in out["arms"].values())
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
        "builder_faithfulness": _assert_builder_faithful(),
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

                corpus = corpus_state(conn, table, spec, n)
                print(f"   corpus: {corpus['rows']} rows, selectivity "
                      f"{corpus['selectivity_pct']}% (band {corpus['selectivity_band']}), "
                      f"{corpus['mean_stored_bytes']} stored bytes/row", flush=True)

                per_arm: Dict[str, Any] = {}
                if not corpus["selectivity_in_band"]:
                    # section 6 item 2: an out-of-band corpus voids the SIZE, and the fix is
                    # to regenerate BEFORE timing -- never to tune until a timing looks good.
                    det = (f"measured selectivity {corpus['selectivity_pct']}% outside "
                           f"{corpus['selectivity_band']}")
                    per_arm = {a: cell_void("corpus_incomplete", det) for a in ARMS}
                    ident = {"checked": False, "detail": "size voided on corpus selectivity"}
                    for a in ARMS:
                        print(f"   {a:12s} VOID  corpus_incomplete: {det}", flush=True)
                else:
                    # T4_ARMS re-takes named cells after a void (section 6 item 1: "the cell
                    # is void and re-run").  It selects WHICH cells run; it changes no gate.
                    only = [a for a in os.environ.get("T4_ARMS", "").split(",") if a]
                    bad = [a for a in only if a not in ARMS]
                    if bad:
                        raise SystemExit(f"T4_ARMS names no such arm: {bad}; have {list(ARMS)}")
                    # Arms not selected are the THIRD outcome, not absent.  Omitting them
                    # produced a size block where four arms had no outcome key at all --
                    # indistinguishable from a harness that forgot them, and a fourth state
                    # section 4.5 does not define.
                    for arm in ARMS:
                        if only and arm not in only:
                            per_arm[arm] = cell_not_attempted(
                                "not selected by T4_ARMS on this re-take")
                    for arm in (only or list(ARMS)):
                        cell = run_cell(conn, table, n, spec, arm, reps)
                        if is_measured(cell):
                            s = cell["stats"]
                            tail = (f"p95 {s['p95']:9.2f}" if "p95" in s
                                    else f"worst of {s['n']} {s['worst_of_n']:9.2f}")
                            print(f"   {arm:12s} median {s['median']:10.2f} ms   {tail}   "
                                  f"(n={s['n']}, warmup {cell['warmup_ms']})", flush=True)
                        else:
                            print(f"   {arm:12s} VOID  {cell['void_reason']}: "
                                  f"{cell['void_detail']}", flush=True)
                        per_arm[arm] = cell

                    # Identity ONCE per size, on the tiebroken arms, never on the timed rows.
                    ident = identity_check(conn, table, spec)
                    ra = ident["arm_a_recall"]
                    print(f"   identity: all_agree={ident['all_agree']}  "
                          f"armA recall {ra['recall_pct']}% "
                          f"({'cap binds' if ra['cap_binds'] else 'cap does not bind'})",
                          flush=True)
                    for arm, cell in list(per_arm.items()):
                        v = ident["arms"].get(arm)
                        if v is not None and not v["agree"] and is_measured(cell):
                            per_arm[arm] = cell_void("arms_disagree", v["detail"])
                            print(f"   {arm:12s} VOID  arms_disagree: {v['detail']}", flush=True)

                end_state = host_state(conn, f"{wkey}/{n}/end")
                report["host"].append(end_state)
                # Section 5.1 / 5.4 item 1 gate the load "when a size ENDS", and nothing
                # compared it.  The per-arm check inside run_cell does not cover this: a
                # cell that voids early never reads an end load at all, and identity_check
                # re-executes every arm AFTER the last cell's reading -- the most expensive
                # ungated stretch in the size.
                l1_end = end_state["loadavg"]["1min"]
                size_void = l1_end > LOAD_CEILING_END
                if size_void:
                    det = (f"1-min load {l1_end} > {LOAD_CEILING_END} at the END of size {n}"
                           f" -- section 5.1's size-level ceiling")
                    print(f"   SIZE VOID  host_load: {det}", flush=True)
                    for arm, cell in list(per_arm.items()):
                        if is_measured(cell):
                            per_arm[arm] = cell_void("host_load", det, {"arm": arm})
                report["cells"][wkey][str(n)] = {"arms": per_arm, "identity": ident,
                                                 "corpus": corpus,
                                                 "size_load_end": l1_end,
                                                 "size_voided_on_end_load": size_void}

    # sizes never attempted are a THIRD outcome, distinguishable from both others
    for wkey in which:
        for n in (20000, 100000, 1000000):
            if str(n) not in report["cells"][wkey]:
                report["cells"][wkey][str(n)] = {
                    "arms": {a: cell_not_attempted("size not in this run's size list")
                             for a in ARMS}}

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # The negative control drives this same main() and must not leave its 1,000-row output
    # sitting at the real run's path, where a later reader would take it for the run.
    out = os.environ.get("T4_OUT") or os.path.join(_HERE, "measurements.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"\nwrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
