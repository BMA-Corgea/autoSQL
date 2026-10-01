"""T-44 negative control. It runs BEFORE any millisecond is quoted (FRAMING sections 2 and 6).

T-4 section 6.1's discipline applies to the new harness. Every void path, every exclusion, and
the verdict engine itself is driven deliberately, THROUGH THE REAL HARNESS, with each
injection's expected outcome declared before it runs. The injections run run_cell / identity /
judge from bench_t44, never a copy of them, on the 1,000-row tables (seconds, not minutes).
If any injection comes back other than declared, the run reports nothing.

The loaded-host amendment (section 10) changes ONE expectation from T-4's. A high load
reading must NOT void: it must be recorded, rep by rep, and the cell must come back measured.
That is I1, the inverse of T-4's injection 1.

Usage: AUTOSQL_SPIKE_DSN=<autosql_spike> control_t44.py <out.json>
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_t44 as H                                   # noqa: E402  the real harness

T4 = H.T4
N = 1000
ROUNDS = 2
results = []


def record(name, expect, got, ok, detail=""):
    results.append({"injection": name, "expected": expect, "got": got, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: expected {expect}; got {got} {detail}", flush=True)


def with_seam(name, fake, fn):
    old = getattr(H, name)
    setattr(H, name, fake)
    try:
        return fn()
    finally:
        setattr(H, name, old)


def main():
    out_path = sys.argv[1]
    conn = T4.connect()

    # I0 -- baseline: the unmodified harness on the small table, both encodings.
    base = {}
    for enc in ("num", "text"):
        cell = H.run_cell(conn, N, enc, ROUNDS)
        base[enc] = cell
        arms = cell["arms"]
        ok = (cell["outcome"] == "measured"
              and all(a.get("outcome") == "measured" for a in arms.values())
              and all(arms[c].get("K5") == "PASS" for c in H.CANDIDATES)
              and all(cell["identity"]["arms"][a]["agree"] for a in cell["identity"]["arms"]))
        record(f"I0 unmodified harness, {N}/{enc}", "all 7 arms measured, identity agrees, K5 PASS x3",
               {a: (v.get("outcome"), v.get("K5", "-")) for a, v in arms.items()}, ok)

    # I1 -- load 40 is RECORDED and NEVER voids (the inverse of T-4's injection 1).
    cell = with_seam("read_loadavg", lambda: (40.0, 40.0, 40.0), lambda: H.run_cell(conn, N, "num", ROUNDS))
    loads = [r["load1"] for a in cell["arms"].values() for r in a.get("reps", [])]
    ok = (cell["outcome"] == "measured" and all(a.get("outcome") == "measured" for a in cell["arms"].values())
          and loads and all(x == 40.0 for x in loads)
          and cell["host_start"]["loadavg"]["1min"] == 40.0)
    record("I1 1-min load 40 injected", "cell MEASURED, every rep records load1=40.0",
           {"outcome": cell["outcome"], "reps_with_load_40": sum(x == 40.0 for x in loads), "reps": len(loads)}, ok)

    # I2 -- a short corpus voids the WHOLE cell, and no statistics exist for it.
    cell = with_seam("read_row_count", lambda conn_, t: N - 1, lambda: H.run_cell(conn, N, "num", ROUNDS))
    ok = cell.get("outcome") == "void" and cell.get("void_reason") == "corpus_incomplete" and "arms" not in cell
    record("I2 row count short by one", "cell VOID corpus_incomplete, no arms/stats",
           {"outcome": cell.get("outcome"), "reason": cell.get("void_reason"), "has_arms": "arms" in cell}, ok)

    # I3 -- index help voids every compiled arm that shows it, and voided arms are not timed.
    def plan_with_index(conn_, sql, params):
        real = T4.capture_plan(conn_, sql, params)
        return real + f"\n  ->  Index Scan using idx_measure_instances_{N}_data_gin on measure_instances_{N}"
    cell = with_seam("capture_plan", plan_with_index, lambda: H.run_cell(conn, N, "num", ROUNDS))
    compiled = [a for a in H.ARM_ORDER if a != "A"]
    ok = (all(cell["arms"][a].get("outcome") == "void" and cell["arms"][a].get("void_reason") == "index_help"
              and "stats" not in cell["arms"][a] for a in compiled)
          and cell["arms"]["A"].get("outcome") == "measured")
    record("I3 a GIN index scan in every compiled plan", "6 compiled arms VOID index_help, untimed; A measured",
           {a: cell["arms"][a].get("void_reason") or cell["arms"][a].get("outcome") for a in H.ARM_ORDER}, ok)
    j = H.judge({f"{n}/{e}": copy.deepcopy(cell) for n in (20000, 100000) for e in ("num", "text")})
    ok = all(v["speed_verdict"] == "INCOMPLETE" for v in j["per_candidate"].values())
    record("I3b judge over index-voided cells", "every candidate INCOMPLETE (never PASS, never FAIL)",
           {c: v["speed_verdict"] for c, v in j["per_candidate"].items()}, ok)

    # I4 -- one row perturbed in ONE arm: a candidate fails K5 (a wrong number); a reported
    #       arm voids. One injection per arm this harness adds.
    for target in ("C_ship", "C_par", "C_inline", "C_both", "C_spike", "B4"):
        def perturb(rows, arm, target=target):
            if arm != target or not rows:
                return rows
            rows = copy.deepcopy(rows)
            rows[0]["load_score"] = (rows[0].get("load_score") or 0) + 1
            return rows
        cell = with_seam("perturb_rows", perturb, lambda: H.run_cell(conn, N, "num", ROUNDS))
        a = cell["arms"][target]
        others_ok = all(cell["identity"]["arms"][x]["agree"] for x in cell["identity"]["arms"] if x != target)
        if target in H.CANDIDATES:
            ok = a.get("K5") == "FAIL" and a.get("outcome") == "measured" and others_ok
            want = f"{target} K5 FAIL (wrong number), still timed; every other arm agrees"
        else:
            ok = a.get("outcome") == "void" and a.get("void_reason") == "arms_disagree" and others_ok
            want = f"{target} VOID arms_disagree; every other arm agrees"
        record(f"I4 one row perturbed in {target}", want,
               {"outcome": a.get("outcome"), "reason": a.get("void_reason"), "K5": a.get("K5", "-"),
                "others_agree": others_ok}, ok)
        if target == "C_par":
            fast = copy.deepcopy(cell)
            for x in fast["arms"].values():
                if "stats" in x:
                    x["stats"].update(median=1.0, p95=1.0)
            fast["arms"]["A"]["stats"].update(median=500.0, p95=500.0)
            j = H.judge({f"{n}/{e}": copy.deepcopy(fast) for n in (20000, 100000) for e in ("num", "text")})
            ok = j["per_candidate"]["C_par"]["speed_verdict"] == "FAIL"
            record("I4b judge: K5 failed but 1 ms everywhere", "C_par FAIL (a wrong number is never fast enough)",
                   j["per_candidate"]["C_par"]["speed_verdict"], ok)

    # I5 -- a repetition that raises is excluded from the statistics, visibly.
    calls = {"n": 0}

    def flaky(arm, conn_, table, spec):
        if arm == "C_both":
            calls["n"] += 1
            if calls["n"] == 2:                         # call 1 is the warm-up; this is rep 1
                raise RuntimeError("injected repetition failure")
        return H.ARMS[arm](conn_, table, spec)
    cell = with_seam("call_arm", flaky, lambda: H.run_cell(conn, N, "num", 3))
    s = cell["arms"]["C_both"]["stats"]
    ok = s.get("excluded_void_reps") == 1 and s.get("n") == 2 and cell["arms"]["C_both"]["outcome"] == "measured"
    record("I5 one C_both repetition raises", "excluded_void_reps=1, n=2 of 3, still measured",
           {"excluded": s.get("excluded_void_reps"), "n": s.get("n")}, ok)

    # I6 -- the verdict engine against the bar, on synthetic statistics.
    def synth(c_med, c_p95, a_med=500.0, c20=150.0, a20=100.0, k5="PASS", drop=None):
        cells = {}
        for n in (20000, 100000):
            for e in ("num", "text"):
                if drop == f"{n}/{e}":
                    continue
                arms = {"A": {"outcome": "measured", "stats": {"median": a_med if n == 100000 else a20, "p95": 0}}}
                for c in H.CANDIDATES:
                    arms[c] = {"outcome": "measured", "K5": k5,
                               "stats": {"median": c_med if n == 100000 else c20, "p95": c_p95 if n == 100000 else c20}}
                cells[f"{n}/{e}"] = {"outcome": "measured", "arms": arms}
        return cells
    cases = [
        ("bar met exactly-ish", synth(299, 599), "PASS"),
        ("median 301 (within 25%)", synth(301, 599), "NEAR-MISS"),
        ("median 375 (the 25% edge)", synth(375, 599), "NEAR-MISS"),
        ("median 376 (beyond 25%)", synth(376, 599), "FAIL"),
        ("p95 751 (beyond 25%)", synth(299, 751), "FAIL"),
        ("under 300 but slower than Python", synth(299, 599, a_med=290), "FAIL"),
        ("20k regression > +100 ms", synth(299, 599, c20=201, a20=100), "FAIL"),
        ("a required cell missing, nothing failed", synth(299, 599, drop="100000/text"), "INCOMPLETE"),
        ("a decisive miss plus a missing cell", synth(400, 599, drop="20000/text"), "FAIL"),
        ("fast but K5 failed", synth(10, 10, k5="FAIL"), "FAIL"),
    ]
    for name, cells, want in cases:
        got = H.judge(cells)["per_candidate"]["C_inline"]["speed_verdict"]
        record(f"I6 judge: {name}", want, got, got == want)

    passed = all(r["pass"] for r in results)
    out = {"control": "T-44 negative control", "passed": passed, "n": len(results),
           "failed": [r["injection"] for r in results if not r["pass"]], "results": results,
           "rounds_per_cell": ROUNDS, "table_size": N}
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(f"NEGATIVE CONTROL: {'PASSED' if passed else 'FAILED'} {sum(r['pass'] for r in results)}/{len(results)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
