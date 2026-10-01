"""T-44: K1-K4 per candidate, computed from the battery outputs. Nothing is copied by hand.

K1  the three subset batteries, recursive rule: DIVERGE / NULLNESS / PY_RAISE / unexplained
    SQL_RAISE / UNCOMPILABLE all zero, for the value AND the predicate form
K2  compare_cases against the shipping pair: no new refusal, no changed SQLSTATE
K3  fixture 130/130
K4  (parallel candidates only) K1 and K2 again under debug_parallel_query = on. They count
    only when the negative control fired, and when every run's positive control launched a
    worker.

Usage: summarize_k.py  -> spikes/T-44/out/K_summary.json
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CASES = os.path.join(HERE, "..", "..", ".autodev", "evidence", "T-44", "cases")
PROFILES = ("sub_ordinary", "sub_unicode", "sub_extreme")
CANDS = {"C_par": ("A_par", "ship", "F_par"), "C_inline": ("B_inline", "inline", "F_inline"),
         "C_both": ("AB_both", "inline", "F_both")}
PARALLEL = {"C_par", "C_both"}
BAD_VALUE = ("DIVERGE", "NULLNESS", "PY_RAISE", "SQL_RAISE", "UNCOMPILABLE")
BAD_PRED = ("DIVERGE", "NULL", "PY_RAISE", "UNCOMPILABLE")


def driver_block(tag):
    s = open(os.path.join(OUT, tag + ".txt"), encoding="utf-8").read()
    return json.loads(s[s.index("{", s.index("=== T-44 driver")):])


def counts(tag):
    c = {}
    with open(os.path.join(CASES, tag + ".jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            c["v:" + r["verdict"]] = c.get("v:" + r["verdict"], 0) + 1
            if "pred" in r:
                c["p:" + r["pred"]] = c.get("p:" + r["pred"], 0) + 1
                if r["pred"] == "SQL_RAISE" and r.get("verdict") not in ("SQL_REFUSAL",):
                    c["p:SQL_RAISE_where_value_did_not_refuse"] = c.get("p:SQL_RAISE_where_value_did_not_refuse", 0) + 1
    return c


def k1(tag):
    c = counts(tag)
    bad = {k: v for k, v in c.items() if (k.startswith("v:") and k[2:] in BAD_VALUE)
           or (k.startswith("p:") and (k[2:] in BAD_PRED or k == "p:SQL_RAISE_where_value_did_not_refuse"))}
    return {"tag": tag, "counts": c, "bad": bad, "pass": not bad}


def k2(base, tag):
    r = subprocess.run([sys.executable, os.path.join(HERE, "compare_cases.py"), base, tag],
                       capture_output=True, text=True)
    first = r.stdout.splitlines()[0] if r.stdout else r.stderr
    return {"vs": base, "tag": tag, "line": first, "pass": r.returncode == 0}


def main():
    nc = {p: counts(f"NC_shipbodies_labelled_safe_{p}_efd1_recursive_PARALLEL") for p in PROFILES}
    nc_fired = all(v.get("v:SQL_RAISE", 0) > 0 for v in nc.values())
    out = {"negative_control_K4": {"fired": nc_fired,
                                   "raises_25000_per_profile": {p: v.get("v:SQL_RAISE", 0) for p, v in nc.items()}},
           "candidates": {}}
    for cand, (prefix, _comp, fix) in CANDS.items():
        rec = {"K1": [], "K2": [], "K3": None, "K4": []}
        for p in PROFILES:
            rec["K1"].append(k1(f"{prefix}_{p}_efd1_recursive"))
            for mode in ("recursive", "strict"):
                rec["K2"].append(k2(f"B0_ship_{p}_efd1_{mode}", f"{prefix}_{p}_efd1_{mode}"))
            if cand in PARALLEL:
                for mode in ("recursive", "strict"):
                    t = f"{prefix}_{p}_efd1_{mode}_PARALLEL"
                    d = driver_block(t)
                    launched = d["parallel"]["positive_control"]["workers_launched"]
                    rec["K4"].append({"tag": t, "dpq": d["debug_parallel_query"],
                                      "worker_launched": launched == ["Workers Launched: 1"],
                                      "K1_value_pred": k1(t)["pass"] if mode == "recursive" else None,
                                      "K2": k2(f"B0_ship_{p}_efd1_{mode}", t)["pass"]})
        fx = json.load(open(os.path.join(OUT, f"fixture_{fix}_efd1.json")))["totals"]
        rec["K3"] = {"totals": fx, "pass": fx["compiled_agrees"] == 130 and fx["cases"] == 130}
        rec["K1_pass"] = all(x["pass"] for x in rec["K1"])
        rec["K2_pass"] = all(x["pass"] for x in rec["K2"])
        rec["K3_pass"] = rec["K3"]["pass"]
        if cand in PARALLEL:
            rec["K4_pass"] = nc_fired and all(
                x["dpq"] == "on" and x["worker_launched"] and x["K2"] and x["K1_value_pred"] in (True, None)
                for x in rec["K4"])
        else:
            rec["K4_pass"] = "n/a (no parallel labels)"
        rec["K1_K4"] = "PASS" if (rec["K1_pass"] and rec["K2_pass"] and rec["K3_pass"]
                                  and rec["K4_pass"] in (True, "n/a (no parallel labels)")) else "FAIL"
        out["candidates"][cand] = rec
    json.dump(out, open(os.path.join(OUT, "K_summary.json"), "w"), indent=1)
    print(json.dumps({"negative_control_K4": out["negative_control_K4"],
                      **{c: {k: v for k, v in r.items() if k.endswith("_pass") or k == "K1_K4"}
                         for c, r in out["candidates"].items()}}, indent=1))


if __name__ == "__main__":
    main()
