"""T-23 — the raw-mode battery. What the 11,367-expression claim does not cover.

WHY THIS FILE EXISTS, AND WHY IT IS NEW RATHER THAN AN EDIT
    spikes/ is FROZEN EVIDENCE. This imports differ.run_case — the same instrument T-3 and
    T-6 used — and never modifies it, the way spikes/T-4/gen_data_t4.py imports the frozen
    generator instead of editing it.

THE GAP THIS MEASURES
    T-6's correctness pass — 0 wrong numbers over 11,367 expressions, the result this
    project leads with — ran entirely in mode="py". Verified: H_ast_fuzz.py:339 calls
    run_case(src, rec, ctx) with no mode, taking differ.py's default. (T-6's run_matrix.sh
    has a variable called "mode", but it is the COMPARISON RULE, strict vs recursive — a
    naming collision that makes the gap easy to miss in the output filenames.)

    differ.py's own docstring says the two are not the same experiment:
      py  — the record is a Python object; "every number has ALREADY collapsed to an IEEE
            double before it reaches the column".
      raw — raw JSON text cast ::jsonb, Python doing json.loads on the same text; "the only
            mode that can exercise jsonb's numeric storage against Python's float parse",
            and "the shape of any row written by something that is not this Python process
            (ETL, migration, psql, another service)".

    That last clause is why this matters beyond tidiness: T-7 established that six of seven
    GIMS write paths never check the declared type, so non-Python writers are the norm.

FIRST, A NEGATIVE RESULT THAT SHAPES THE REST
    Re-running the SAME records in raw mode is very nearly a no-op, and differ.py:245 says
    why: `params["rec"] = json.dumps(record) if mode == "py" else raw`. In py mode SQL is
    ALREADY handed json.dumps(record) — the identical text. The only thing raw changes for
    such a record is that Python re-parses it, and for a py-representable value that round
    trip returns the same object.

    So "re-run the batteries in raw mode" cannot mean "same records, other flag". The
    experiment only exists where the RECORD ITSELF cannot be built in Python — a JSON number
    carrying more precision or magnitude than a double. That is what this generates.

WHAT IT REPORTS
    Counts per verdict, and every DIVERGE printed in full, because a divergence here is a
    wrong number on data a non-Python writer produces every day.
"""
from __future__ import annotations
import json, os, sys, collections

_FUZZ = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/fuzz"
sys.path.insert(0, _FUZZ)
from differ import run_case          # noqa: E402  the FROZEN instrument, driven not edited

# ── the raw-only numeric literals. Each is a JSON number that a Python object cannot
#    carry faithfully, which is precisely the population py-mode excludes by construction.
RAW_NUMS = [
    ("0.1000000000000000000000001", "differs from 0.1 only past the double"),
    ("0.1000000000000000055511151231257827", "the exact double value of 0.1, written out"),
    ("0.30000000000000004",         "the double sum 0.1+0.2, exact in jsonb"),
    ("1.0000000000000002",          "one ulp above 1.0"),
    ("0.99999999999999999",         "rounds to 1.0 as a double"),
    ("12345678901234567890123456789", "integer far beyond 2^53"),
    ("9007199254740993",            "2^53 + 1 — the first integer a double cannot hold"),
    ("1e309",                       "beyond DBL_MAX; Python float() gives inf"),
    ("-1e309",                      "beyond -DBL_MAX"),
    ("1e-400",                      "underflows a double to 0.0"),
    ("123.4500000000000000000001",  "a money-shaped value with a hidden tail"),
    ("1.7976931348623157081e308",   "just past DBL_MAX in the last digits"),
]

# ── expressions from the restricted subset. Comparison, arithmetic and the numeric
#    coercions — the shapes a dashboard actually emits.
EXPRS = [
    "$.a == 0.1", "$.a == 1", "$.a != 0.1", "$.a > 0.1", "$.a < 1",
    "$.a + 0", "$.a * 1", "$.a - 0", "$.a / 1",
    "number($.a)", "abs($.a)", "round($.a, 2)", "max($.a, 1)", "min($.a, 1)",
    "$.a == $.b", "$.a > $.b", "$.a + $.b",
]

def main() -> int:
    counts = collections.Counter()
    diverges, refusals = [], []
    n = 0
    for lit, why in RAW_NUMS:
        for src in EXPRS:
            raw = ('{"a": %s, "b": 0.1}' % lit)
            o = run_case(src, None, mode="raw", raw=raw, note=why)
            v = o["verdict"]; counts[v] += 1; n += 1
            if v == "DIVERGE":
                diverges.append((src, lit, why, o.get("python"), o.get("sql_value")))
            elif v in ("SQL_REFUSAL", "SQL_RAISE", "PY_RAISE", "NULLNESS"):
                refusals.append((v, src, lit, o.get("refusal_kind")))

    print("T-23 — raw-mode battery")
    print("=" * 78)
    print(f"{n} expressions over {len(RAW_NUMS)} raw-only JSON numbers "
          f"({len(EXPRS)} expressions each)\n")
    for v, c in counts.most_common():
        print(f"  {v:14s} {c:5d}")
    print()
    if diverges:
        print(f"*** {len(diverges)} DIVERGE — the two engines answered the same question "
              f"differently ***\n")
        for src, lit, why, py, sql in diverges:
            print(f"  {src:16s} a = {lit}")
            print(f"      {why}")
            print(f"      python={py}   sql={sql}\n")
    else:
        print("no divergence")
    print(f"refusals/raises: {len(refusals)}")
    for v, src, lit, kind in refusals[:12]:
        print(f"  {v:12s} {src:16s} a = {lit[:34]}  {kind or ''}")
    if len(refusals) > 12:
        print(f"  … and {len(refusals) - 12} more")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
