"""T-44 lever (a): is the rewritten xpr.num EXACTLY the shipping one?  Measured, not argued.

The shipping xpr.num (database A) and lever (a)'s rewrite (database B) are called on the same
jsonb inputs. They must agree on every input: the same value, bit for bit (the sign of zero
included), or the same SQLSTATE. Inputs:

  1. every string value in the shipping-pair battery records (all three profiles);
  2. hand-written boundary strings around each limit the rewrite reasons about: numeric's
     dscale (16383) and weight, the 1000-character and 4-digit-exponent guard, DBL_MAX and
     the named refusal, underflow, whitespace, and non-ASCII digits with exponents;
  3. a seeded grammar fuzz over the same shape the regex accepts and its near misses;
  4. non-string jsonb (numbers, booleans, null, containers), where nothing changed.

Usage: num_diff.py <dsn-shipping> <dsn-lever-a> <out.json>
"""
import glob
import json
import math
import random
import sys

import psycopg2

ROOT = "/home/corgea/Desktop/Coding Projects/autoSQL"
SEED = 4401


def strings_from_batteries():
    seen = set()

    def walk(v):
        if isinstance(v, str):
            seen.add(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    for f in sorted(glob.glob(f"{ROOT}/.autodev/evidence/T-44/cases/B0_ship_*_efd1_recursive.jsonl")):
        for line in open(f, encoding="utf-8"):
            walk(json.loads(line).get("record"))
    return sorted(seen)


def boundary_strings():
    z = "0"
    s = [
        "1e999", "-1e999", "1e308", "1.7976931348623157e308", "1.7976931348623158e308",
        "1.7976931348623159e308", "1.8e308", "-1.8e308", "179769313486231570000" + z * 288,
        "179769313486231580000" + z * 288, "1e-300", "1e-320", "5e-324", "2e-324", "1e-324",
        "1e-400", "1e-999", "1e-1000", "1e-9999", "1e-16383", "1e-16384", "1e-20000",
        "1e1000", "1e9999", "1e99999", "1e131071", "1e131072", "1e200000", "-1e200000",
        "1e2147483647", "1e-2147483647", "1e+0000000000000000005", "1e-0000000000000000005",
        "1e0999", "1e1000", "00001e0003", "+.5", "-.5e-3", "1.e5", ".5E+2", "-0", "+0", "0.0",
        "-0.0", "0e999999", "0e-999999", "0." + z * 16383, "0." + z * 16384, "0." + z * 20000,
        "1" + z * 20000 + "e-20000", "1" + z * 1000, "1" * 1000, "1" * 1001, "9" * 309,
        "9" * 310, "1" + z * 131071, "1" + z * 131072, "." + "1" * 16383, "." + "1" * 16384,
        " 1e999 ", "\t1e-400\n", " 7 ", "1e3", "１２３", "１e999", "١٢٣e9999", "１.５e-400",
        " 1e9999　", "e5", ".e1", "1e", "1e+", "--1", "1..2", "", " ", "abc", "nan",
        "inf", "Infinity", "-Infinity", "NaN", "0x10", "1_000",
    ]
    return s


def fuzz_strings(rng, n):
    nd = "٠١٢٣٤٥٦٧٨٩"         # Arabic-Indic digits: the translate() path
    out = []
    for _ in range(n):
        def digits(k):
            return "".join(rng.choice("0123456789") if rng.random() > 0.05 else rng.choice(nd)
                           for _ in range(k))
        mant = rng.choice([
            lambda: digits(rng.randint(1, 25)),
            lambda: digits(rng.randint(0, 25)) + "." + digits(rng.randint(0, 25)),
            lambda: digits(rng.choice([998, 999, 1000, 1001, 1002])),
            lambda: "0." + "0" * rng.choice([16380, 16382, 16383, 16384]) + digits(rng.randint(0, 3)),
        ])()
        if rng.random() < 0.6:
            e = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 7)))
            mant += rng.choice("eE") + rng.choice(["", "+", "-"]) + e
        if rng.random() < 0.15:
            mant = rng.choice(["", "+", "-"]) + mant
        if rng.random() < 0.1:
            mant = rng.choice([" ", "\t", "　"]) + mant + rng.choice(["", " ", "\n"])
        out.append(mant)
    return out


def call(cur, j):
    try:
        cur.execute("SELECT xpr.num(%s::jsonb)", (j,))
        v = cur.fetchone()[0]
        if v is None:
            return ["NULL"]
        return ["VAL", repr(v), math.copysign(1.0, v) < 0]
    except psycopg2.Error as e:
        return ["ERR", e.pgcode, str(e).strip().splitlines()[0][:120]]


def main():
    dsn_a, dsn_b, out = sys.argv[1:4]
    ca, cb = psycopg2.connect(dsn_a), psycopg2.connect(dsn_b)
    ca.autocommit = cb.autocommit = True
    for c in (ca, cb):
        with c.cursor() as cur:
            cur.execute("SET extra_float_digits = 1")
    rng = random.Random(SEED)
    strs = strings_from_batteries()
    n_battery = len(strs)
    strs += boundary_strings() + fuzz_strings(rng, 6000)
    inputs = [json.dumps(s) for s in strs]
    inputs += ["1e400", "-1e400", "1e-400", "-0", "0", "5e-324", "1.7976931348623157e308",
               "1797693134862315800000" + "0" * 287, "true", "false", "null", "[]", "[1]", "{}",
               '{"a": 1}', "12345.678", "-2.25"]
    diffs, kinds = [], {}
    with ca.cursor() as a, cb.cursor() as b:
        for j in inputs:
            ra, rb = call(a, j), call(b, j)
            kinds[ra[0]] = kinds.get(ra[0], 0) + 1
            if ra[0] == "ERR":
                kinds["ERR " + str(ra[1])] = kinds.get("ERR " + str(ra[1]), 0) + 1
            same = (ra == rb) if ra[0] != "ERR" else (rb[0] == "ERR" and ra[1] == rb[1])
            if not same:
                diffs.append({"input": j[:200], "len": len(j), "shipping": ra, "lever_a": rb})
    res = {"inputs": len(inputs), "from_batteries": n_battery, "seed": SEED,
           "outcomes_shipping": kinds, "differences": len(diffs), "diff_examples": diffs[:50]}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("inputs", "from_batteries", "outcomes_shipping", "differences")}))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
