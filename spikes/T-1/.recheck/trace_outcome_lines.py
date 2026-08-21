"""T-1 recheck · line-coverage prober for conformance.py's outcome-assignment branches.

Runs conformance.py's normal entry point (main() -> selftest() + run()) under a line
tracer and reports the execution count of every line in the file, then prints the counts
for the four outcome-assignment branches specifically.

This settles FINDINGS.md 5.9(6) by measurement rather than by reading: it says how many
times each branch actually ran during a normal run.

Usage:
  "/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python" \
      "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.recheck/trace_outcome_lines.py"
"""
import importlib.util
import sys
from collections import Counter

CONF = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance.py"

BRANCHES = {
    "A  DID_NOT_COMPILE   (except Uncompilable)": (377, 382),
    "B  SQL_ERROR         (except SqlRaised)":    (396, 404),
    "C  COMPILED_AGREES   (if agree and not leak)": (443, 448),
    "D  COMPILED_DIVERGES (else)":                (449, 455),
}
# The single line inside each branch that performs the assignment.
ASSIGN = {377: "DID_NOT_COMPILE", 378: "entry.update(outcome=DID_NOT_COMPILE)",
          380: 'counts["DID_NOT_COMPILE"] += 1',
          396: "SQL_ERROR", 398: "entry.update(outcome=SQL_ERROR)",
          402: 'counts["SQL_ERROR"] += 1',
          443: "if agree and not leak", 444: "entry.update(outcome=COMPILED_AGREES)",
          445: 'counts["COMPILED_AGREES"] += 1',
          449: "else:", 451: "outcome=COMPILED_DIVERGES",
          455: 'counts["COMPILED_DIVERGES"] += 1'}

hits = Counter()


def tracer(frame, event, arg):
    if frame.f_code.co_filename == CONF:
        if event == "line":
            hits[frame.f_lineno] += 1
        return tracer
    return None


INJECT = "--inject" in sys.argv

if INJECT:
    # Trace the SAME conformance.py, but driven through proto/conformance_injection_test.py
    # so branches A, B and D are provoked.  Confirms the tracer is measuring the branches
    # and not just reporting zeros for lines it cannot see.
    ispec = importlib.util.spec_from_file_location(
        "inj", "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/"
               "conformance_injection_test.py")
    inj = importlib.util.module_from_spec(ispec)
    sys.modules["inj"] = inj
    ispec.loader.exec_module(inj)
    globals()["CONF"] = CONF   # same file object path; inj imported it under another name
    sys.argv = [sys.argv[0]]   # so inj.main() runs the injecting (not control) path
    sys.settrace(tracer)
    try:
        rc = inj.main()
    finally:
        sys.settrace(None)
else:
    spec = importlib.util.spec_from_file_location("conformance_traced", CONF)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["conformance_traced"] = mod
    spec.loader.exec_module(mod)

    sys.settrace(tracer)
    try:
        rc = mod.main()
    finally:
        sys.settrace(None)

src = open(CONF).read().split("\n")
print("\n" + "=" * 78)
print("LINE HIT COUNTS — conformance.py outcome-assignment branches, "
      + ("UNDER INJECTION" if INJECT else "normal run"))
print("=" * 78)
for label, (lo, hi) in BRANCHES.items():
    total = sum(hits.get(n, 0) for n in range(lo, hi + 1))
    print(f"\n{label}   lines {lo}-{hi}   TOTAL HITS = {total}")
    for n in range(lo, hi + 1):
        h = hits.get(n, 0)
        mark = "  " if h else "**"   # ** marks a line that NEVER executed
        print(f"  {mark} {n:4d}  hits={h:<5d} | {src[n-1].rstrip()}")

print("\n" + "-" * 78)
print("SUMMARY (the assignment lines only)")
print("-" * 78)
for n in sorted(ASSIGN):
    print(f"  line {n:4d}  hits={hits.get(n,0):<5d}  {ASSIGN[n]}")
print(f"\nmain() returned {rc}")
print(f"total distinct lines of conformance.py executed: {len(hits)}")
