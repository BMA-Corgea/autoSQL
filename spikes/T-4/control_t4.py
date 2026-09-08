"""T-4 · THE NEGATIVE CONTROL — required, and required FIRST (FRAMING.md §6.1).

WHY THIS EXISTS
---------------
A negative control is a deliberately broken input, used to prove the rig can report a
failure at all.  It is not a test of the thing being measured; it is a test of the
INSTRUMENT, run before the instrument is believed.

This project has already shipped exactly this mistake and it stood for four passes.
`proto/conformance.py` assigns outcomes at four sites, and a full run under a line tracer
showed `DID_NOT_COMPILE` hits=0, `SQL_ERROR` hits=0, `COMPILED_DIVERGES` hits=0 — three of
the four failure branches had NEVER EXECUTED, and every conformance headline in the
record had come from a rig whose failure surface was dead.

T-4 is open to the same failure in a worse place: everything it reports is a number of
milliseconds, and the only thing between a dirty-host reading and a quoted headline is the
void path.  If that path never fires, the run emits a complete, plausible, internally
consistent table of timings with no indication whatsoever that anything was wrong — which
is a description of the original sweep.

BINDING ORDERING RULE (§6.1): no real millisecond may be quoted, in any document, until
this passes.  A control run afterwards is a control that already knows which answer it
needs.

HOW IT WORKS
------------
`bench_t4.py` is NOT modified.  It is imported and its SEAMS — the single places it learns
a fact that can void a cell — are swapped for fakes, exactly as
`proto/conformance_injection_test.py` swaps the compiler handle.  Everything downstream
(run_cell, the gates, aggregate(), identity_check(), main()'s void loop, the report writer)
is the real, unmodified harness.  Each injection declares in advance the outcome it MUST
provoke, asserts it FIRED, and asserts the emitted outcome string.

THE INJECTIONS
--------------
  I1a  /proc/loadavg above §5.1's START ceiling, injected — the machine is NOT loaded
                                                       expect void · host_load
  I1b  load fine at start, above the END ceiling when the cell finishes
                                                       expect void · host_load
       (I1b is separate because it is a SEPARATE BRANCH.  A start-ceiling injection
       leaves the end-ceiling branch exactly as dead as the three conformance branches
       were, and this file exists because of those.)
  I2   a table whose row count is short of N           expect void · corpus_incomplete
  I3a  a plan carrying a non-pkey index-scan node      expect void · index_help
  I3b  a plan carrying the ALLOWED pkey lookup         expect MEASURED — the guard must
       discriminate, not merely refuse.  T-17's guard exercise found two genuine holes of
       exactly this shape (a check that matched almost any text), so the negative case is
       asserted alongside the positive one.
  I4   ONE arm's rows perturbed by a single row        expect void · arms_disagree
  I5   a size never attempted at all                   expect not-attempted — the THIRD
       outcome, distinguishable from both of the others (§4.5, §11)
  X    §6.1's exclusion clause: a median computed over a set containing a voided cell is
       computed from the OTHERS, and a fully-voided set reports no_admissible_reps.

If any injection comes back scored as admissible, THE RUN REPORTS NOTHING — not a caveat
in the write-up, not a footnote under the table.  No output, and the control failure is
what gets handed up instead (§6.1).

USAGE
  AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=... dbname=autosql_spike" \
      python control_t4.py [--json OUT.json]
"""
from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import bench_t4 as T          # noqa: E402  the REAL harness, seams swapped, never edited

TABLE = "measure_instances_1000"      # §6.1: five injections on the 1,000-row table
N = 1000
SPEC = T.WIDGET_INVENTED              # the widget the bar applies to

results = []
failures = []


def record(name, expect, got, fired, detail=""):
    ok = (got == expect) and fired
    results.append({"injection": name, "expected": expect, "emitted": got,
                    "fired": bool(fired), "pass": ok, "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name:5s} expected {expect:<28s} emitted {got}"
          + (f"   [{detail}]" if detail else ""))
    if not ok:
        failures.append(name)


def outcome_of(cell):
    o = cell.get("outcome")
    return o if o != T.VOID else f"void:{cell.get('void_reason')}"


class swap:
    """Replace one seam on the real module for the duration of a block."""

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def __enter__(self):
        self.old = getattr(T, self.name)
        setattr(T, self.name, self.fn)
        return self

    def __exit__(self, *exc):
        setattr(T, self.name, self.old)
        return False


def main() -> int:
    conn = T.connect()
    print(f"\nT-4 NEGATIVE CONTROL — {TABLE}, widget "
          f"{SPEC['derive_name']!r} (invented={SPEC['invented']})")
    print(f"started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")

    # A single real cell first: the control must show the harness CAN say "measured",
    # or every void below proves only that the harness always voids.
    with T.widget(SPEC):
        base = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I0", T.MEASURED, outcome_of(base), True,
           "uninjected baseline: the rig can emit `measured`")

    # ---- I1a: host load over the START ceiling ---------------------------------------
    calls = []
    def hot(_c=calls):
        _c.append(1)
        return (99.0, 99.0, 99.0)
    with T.widget(SPEC), swap("read_loadavg", hot):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I1a", "void:host_load", outcome_of(cell), bool(calls),
           f"injected 1-min load 99.0 > {T.LOAD_CEILING_START}; machine NOT loaded")

    # ---- I1b: fine at start, over the END ceiling ------------------------------------
    seq = {"n": 0}
    def rising():
        seq["n"] += 1
        return ((0.10, 0.10, 0.10) if seq["n"] == 1 else (9.90, 9.90, 9.90))
    with T.widget(SPEC), swap("read_loadavg", rising):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I1b", "void:host_load", outcome_of(cell), seq["n"] >= 2,
           f"0.10 at start, 9.90 > {T.LOAD_CEILING_END} at end — the SEPARATE end branch")

    # ---- I2: corpus short of N -------------------------------------------------------
    hits = []
    def short(conn_, table_, _h=hits):
        _h.append(table_)
        return N - 1
    with T.widget(SPEC), swap("read_row_count", short):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I2", "void:corpus_incomplete", outcome_of(cell), bool(hits),
           f"row count reported as {N - 1}, expected {N}")

    # ---- I3a: a non-pkey index scan in the plan --------------------------------------
    BAD = ("Limit (actual rows=50 loops=1)\n"
           "  ->  Bitmap Heap Scan on measure_instances_1000 (actual rows=53 loops=1)\n"
           "        ->  Bitmap Index Scan on idx_measure_instances_1000_data_gin"
           " (actual rows=53 loops=1)\n"
           "              Buffers: shared hit=12 read=3\n")
    seen = []
    def bad_plan(conn_, sql, params, _s=seen):
        _s.append(sql)
        return BAD
    with T.widget(SPEC), swap("capture_plan", bad_plan):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I3a", "void:index_help", outcome_of(cell), bool(seen),
           "plan carries a GIN Bitmap Index Scan — Q11 put index help permanently off")

    # ---- I3b: the ALLOWED pkey lookup must NOT void ----------------------------------
    # The shape Postgres actually prints for the ALLOWED use: the primary key doing the
    # `collection = ...` restriction, Index Cond and all.  An earlier version of this fixture
    # omitted the Index Cond line, and when the guard was tightened to require it this check
    # went red -- the control catching a regression in the guard, which is its whole job.
    OK_PLAN = ("Limit (actual rows=50 loops=1)\n"
               "  ->  Index Scan using measure_instances_1000_pkey on"
               " measure_instances_1000 (actual rows=53 loops=1)\n"
               "        Index Cond: (collection = 'noun:Sample'::text)\n"
               "        Buffers: shared hit=40 read=2\n")
    seen2 = []
    def ok_plan(conn_, sql, params, _s=seen2):
        _s.append(sql)
        return OK_PLAN
    with T.widget(SPEC), swap("capture_plan", ok_plan):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I3b", T.MEASURED, outcome_of(cell), bool(seen2),
           "pkey collection lookup is the one allowed index use — the guard must "
           "discriminate, not merely refuse")

    # ---- I3c: the pkey exemption must be the COLLECTION lookup, not the word "_pkey" ---
    # §6 item 4 permits the primary key doing the `collection = ...` restriction, and
    # nothing else.  A guard that skips any line containing "_pkey" would wave through the
    # primary key being used to ANSWER THE WIDGET, which is precisely the index help Q11
    # ruled permanently off.
    SNEAKY = ("Limit (actual rows=50 loops=1)\n"
              "  ->  Index Scan using measure_instances_1000_pkey on"
              " measure_instances_1000 (actual rows=53 loops=1)\n"
              "        Index Cond: (((data ->> 'queue_depth'))::numeric > 195::numeric)\n"
              "        Buffers: shared hit=40 read=2\n")
    seen3 = []
    def sneaky_plan(conn_, sql, params, _s=seen3):
        _s.append(sql)
        return SNEAKY
    with T.widget(SPEC), swap("capture_plan", sneaky_plan):
        cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    record("I3c", "void:index_help", outcome_of(cell), bool(seen3),
           "a pkey index answering the PREDICATE is still index help — the exemption is "
           "the collection lookup, not the substring '_pkey'")

    # ---- I4: one arm perturbed by a single row ---------------------------------------
    # Drives main() end to end, because the arms_disagree void is applied in main()'s
    # per-size loop, not in run_cell.  Output goes to a control path, never the run's.
    touched = []
    def perturb(rows, arm="", _t=touched):
        if arm != "C" or not rows:
            return rows
        _t.append(arm)
        out = list(rows)
        victim = dict(out[0])
        victim["id"] = "__control_injected_row__"
        out[0] = victim
        return out

    ctl_out = os.path.join(_HERE, "..", "..", ".autodev", "evidence", "T-4", "control_measurements.json")
    os.environ["T4_OUT"] = ctl_out
    with swap("perturb_rows", perturb):
        T.main(["control_t4.py", str(N), "invented"])
    with open(ctl_out) as fh:
        rep = json.load(fh)
    size_block = rep["cells"]["invented"][str(N)]
    c_cell = size_block["arms"]["C"]
    record("I4", "void:arms_disagree", outcome_of(c_cell), bool(touched),
           f"arm C's first row re-keyed; identity ran on the tiebroken arms "
           f"(all_agree={size_block['identity'].get('all_agree')})")

    # arm A must NOT have been voided by that: it is not held to identity, and §4.2 needs
    # its median as the same-session Python baseline.
    a_out = outcome_of(size_block["arms"]["A"])
    record("I4b", T.MEASURED, a_out, True,
           "arm A survives an identity failure elsewhere — §4.2 is defined against its "
           "same-session median")

    # ---- I5: a size never attempted ---------------------------------------------------
    missing = {s: rep["cells"]["invented"][s]["arms"]["C"]["outcome"]
               for s in ("20000", "100000", "1000000")}
    all_na = set(missing.values()) == {T.NOT_ATTEMPTED}
    record("I5", T.NOT_ATTEMPTED, sorted(set(missing.values()))[0] if missing else "?",
           all_na, f"sizes not in the run's size list: {missing}")

    # ---- I6/I7/X: §6.1's exclusion clause, driven through the REAL harness -------------
    # These replace a pair of checks that called aggregate() on a hand-built list. That is
    # a unit test of a helper function, which §6.1 rules out in as many words -- and it was
    # passing while the exclusion path in run_cell stayed exactly as dead as conformance.py's
    # three branches were, because no repetition could ever void. A rep that RAISES is now
    # the mechanism, so the clause is reachable and is exercised where it lives.
    real_c = T.ARMS["C"]

    def raises_once(conn_, table_, spec_, _n=[0]):
        _n[0] += 1
        if _n[0] == 4:          # 1 = warm-up, 2.. = repetitions
            raise RuntimeError("control-injected failure on one repetition")
        return real_c(conn_, table_, spec_)

    T.ARMS["C"] = raises_once
    try:
        with T.widget(SPEC):
            cell = T.run_cell(conn, TABLE, N, SPEC, "C", 5)
    finally:
        T.ARMS["C"] = real_c
    st = cell.get("stats", {})
    ok = (outcome_of(cell) == T.MEASURED and st.get("n") == 4
          and st.get("excluded_void_reps") == 1)
    record("I6", "measured-minus-the-voided-rep",
           "measured-minus-the-voided-rep" if ok
           else f"outcome={outcome_of(cell)} n={st.get('n')} "
                f"excluded={st.get('excluded_void_reps')}",
           True, "5 reps, 1 raised: the median is computed from the OTHER 4 and the "
                 "exclusion is counted, not silently absorbed")

    def always_raises(conn_, table_, spec_):
        raise RuntimeError("control-injected: every repetition fails")

    T.ARMS["C"] = always_raises
    try:
        with T.widget(SPEC):
            cell = T.run_cell(conn, TABLE, N, SPEC, "C", 3)
    finally:
        T.ARMS["C"] = real_c
    record("I7", "void:rep_error", outcome_of(cell), True,
           "when nothing survives, the cell voids rather than reporting an empty statistic "
           "-- and one raise no longer discards the whole exclusive window")

    # ---- verdict ----------------------------------------------------------------------
    passed = not failures
    print(f"\n{'=' * 78}")
    print(f"NEGATIVE CONTROL: {'PASSED' if passed else 'FAILED'} "
          f"— {len(results) - len(failures)}/{len(results)} checks")
    if not passed:
        print(f"FAILED: {', '.join(failures)}")
        print("\nPer FRAMING.md §6.1, the run reports NOTHING and the control failure is "
              "what gets handed up.  No millisecond may be quoted.")
    else:
        print("The void path has been driven through the real harness for every "
              "admissibility gate.\nThe ordering rule of §6.1 is discharged: timing may "
              "now begin.")
    print(f"{'=' * 78}\n")

    out = {"control": "T-4 §6.1 negative control", "table": TABLE,
           "widget": SPEC["derive_name"], "invented": SPEC["invented"],
           "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "harness_sha256": T.script_fingerprints(),
           "passed": passed, "checks": results, "failures": failures}
    if "--json" in sys.argv:
        p = sys.argv[sys.argv.index("--json") + 1]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"wrote {p}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
