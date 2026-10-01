"""T-44 lever (b): is the inline coercion EXACTLY xpr.num?  Every branch, measured directly.

The batteries prove agreement with Python on whatever values they happen to draw. This probe
targets the coercion itself. The inline CASE that compile_inline emits and the runtime's
xpr.num run on the same jsonb input, in the same database and session. They must agree on the
same value, bit for bit (the sign of zero included), or on the same SQLSTATE. The inputs cover
every branch and both sides of every boundary in the inline form:
  number: in range, at and beyond the DBL_MAX literal, subnormal, underflow (raw jsonb)
  string: plain decimals at 298, 299, 300 and 301 characters; signs, leading dots, trailing
          dots, leading zeros, -0; and every near miss that must fall through to xpr.num
          (whitespace, exponent, non-ASCII digits, inner space, empty)
  boolean, null, array, object, and SQL NULL
plus num_diff's battery strings and its seeded grammar fuzz.

Usage: coerce_diff.py <dsn> <out.json>
"""
import importlib.util
import json
import math
import os
import random
import sys

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci = load("ci", os.path.join(HERE, "compile_inline.py"))
nd = load("nd", os.path.join(HERE, "num_diff.py"))


def inputs():
    strs = nd.strings_from_batteries() + nd.boundary_strings() + nd.fuzz_strings(random.Random(4402), 3000)
    for n in (297, 298, 299, 300, 301):
        strs += ["1" * n, "9" * n, "0." + "0" * (n - 3) + "1", "-" + "1" * (n - 1), "1" * (n - 2) + ".5"]
    strs += ["12", "-3", "+3", "1.5", "1.", ".5", "-.5", "+.5", "00012", "-0", "+0", "0", "0.0",
             "-0.0", "1.5 ", " 1.5", "1 5", "1e3", "1E3", "１２", "12a", "a12", "", ".", "-", "+",
             "--1", "1..2", "١٢", " 12", "1.5\n", "9" * 17, "123456789012345678901234567890"]
    js = [json.dumps(s) for s in strs]
    js += ["0", "-0", "1", "-1", "1.5", "12345.678", "1e300", "-1e300", "1e308", "1.7976931348623157e308",
           "-1.7976931348623157e308", "1.7976931348623158e308", "1.8e308", "1e309", "1e400",
           "17976931348623157" + "0" * 292, "17976931348623157" + "0" * 291 + "1",
           "17976931348623158" + "0" * 292, "5e-324", "1e-320", "2.2250738585072014e-308",
           "1e-400", "-1e-400", "0.1", "1e16", "9007199254740993", "true", "false", "null",
           "[]", "[1]", '["1"]', "{}", '{"a": 1}']
    return js


def run(cur, sql, j):
    try:
        cur.execute(sql, {"j": j})
        v = cur.fetchone()[0]
        if v is None:
            return ["NULL"]
        return ["VAL", repr(v), math.copysign(1.0, v) < 0]
    except psycopg2.Error as e:
        return ["ERR", e.pgcode]


def main():
    dsn, out = sys.argv[1:3]
    c = psycopg2.connect(dsn)
    c.autocommit = True
    comp = ci._InlineCompiler("data", "ctx")
    inline_sql = "SELECT " + comp._inline_coerce("(%(j)s)::jsonb")
    runtime_sql = "SELECT xpr.num((%(j)s)::jsonb)"
    diffs, branches = [], {}
    with c.cursor() as cur:
        cur.execute("SET extra_float_digits = 1")
        cases = inputs() + [None]                               # None -> SQL NULL
        for j in cases:
            a, b = run(cur, runtime_sql, j), run(cur, inline_sql, j)
            cur.execute("SELECT jsonb_typeof((%(j)s)::jsonb)", {"j": j})
            t = cur.fetchone()[0]
            branches[str(t)] = branches.get(str(t), 0) + 1
            same = (a == b) if a[0] != "ERR" else (b[0] == "ERR" and a[1] == b[1])
            if not same:
                diffs.append({"input": None if j is None else j[:160], "xpr.num": a, "inline": b})
    res = {"inputs": len(cases), "by_jsonb_type": branches, "differences": len(diffs),
           "diff_examples": diffs[:40]}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("inputs", "by_jsonb_type", "differences")}))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
