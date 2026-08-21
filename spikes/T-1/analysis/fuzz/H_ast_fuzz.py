"""T-1 fuzz seat, battery H -- the broad differential fuzz.

Random expression SOURCE (parsed by the real expr.parse) x random record,
evaluated by the real expr.evaluate and by the compiled SQL against live
Postgres, then diffed with the mirrored comparison rule.

Distributions are deliberately BORING by default (--profile ordinary): the
values look like dashboard data.  --profile extreme turns on the pathological
magnitudes.  Reporting both keeps the reachability claim honest, because a
divergence rate measured on adversarial inputs says nothing about production.

Usage: python H_ast_fuzz.py [ordinary|extreme|unicode] [N] [seed]
"""
import json
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, '.')
from differ import run_case

PROFILE = sys.argv[1] if len(sys.argv) > 1 else "ordinary"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 2026

FIELDS = ["a", "b", "c", "s", "t", "d", "e", "l", "o", "n", "flag"]

DATES = ["2024-01-01", "2024-02-29", "2023-12-31T23:59:59Z", "2024-06-15T12:30",
         "1999-01-01 00:00:00", "2024-01-01T00:00:00+05:30", "not a date", "",
         "0001-01-01", "9999-12-31", "2024-13-45"]

STRINGS = ["", "abc", "FAIL", "Fail", "pass", "0", "12", "1.5", " 7 ", "x y",
           "2024-01-01", "true", "null", "-3", "1e3", "abcabc"]

UNI_STRINGS = ["straße", "İstanbul", "ÅNGSTRÖM", "ǅ", "ﬁ", "ΣΊΣΥΦΟΣ", "ᾀ",
               "１２３", "١٢٣", " 12 ", "é", "é", "🙂", "ﬀ", "ß"]


def rnd_num(rng):
    if PROFILE == "extreme":
        return rng.choice([
            0.0, -0.0, 1.0, -1.0, 0.5, 1e-7, 1e16, 1e17, 1e21, 1e22,
            5e-324, 1e-320, 2.2250738585072014e-308, 1e295, 1.7e296, 1e300,
            1.7976931348623157e308, 2.0**53, 2.0**53 + 2, 0.1, 1 / 3,
            rng.uniform(-1e6, 1e6), rng.choice([-1, 1]) * 10.0 ** rng.randint(-300, 300),
        ])
    return rng.choice([0, 1, -1, 2, 3, 7, 10, 100, 0.5, 1.5, -2.25, 3.14159,
                       42, 1000, 99999, 0.1, -0.001, 12345.678, 2, 5])


def rnd_value(rng, depth=0):
    r = rng.random()
    if r < 0.30:
        return rnd_num(rng)
    if r < 0.50:
        return rng.choice(UNI_STRINGS if PROFILE == "unicode" else STRINGS)
    if r < 0.58:
        return rng.choice(DATES)
    if r < 0.66:
        return rng.choice([True, False])
    if r < 0.72:
        return None
    if r < 0.86 and depth < 2:
        return [rnd_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    if depth < 2:
        return {rng.choice(FIELDS): rnd_value(rng, depth + 1)
                for _ in range(rng.randrange(3))}
    return rnd_num(rng)


def rnd_record(rng):
    return {f: rnd_value(rng) for f in FIELDS if rng.random() < 0.75}


def lit(rng):
    r = rng.random()
    if r < 0.45:
        v = rnd_num(rng)
        return repr(float(v)) if isinstance(v, float) else str(v)
    if r < 0.75:
        s = rng.choice(UNI_STRINGS if PROFILE == "unicode" else STRINGS)
        return json.dumps(s)
    if r < 0.85:
        return rng.choice(["true", "false"])
    if r < 0.92:
        return "null"
    return json.dumps(rng.choice(DATES))


def field(rng):
    p = "$." + rng.choice(FIELDS)
    while rng.random() < 0.30:
        if rng.random() < 0.5:
            p += "." + rng.choice(FIELDS)
        else:
            p += "[%d]" % rng.randrange(-2, 3)
    return p


UNARY = ["lower", "upper", "number", "string", "length", "abs", "floor", "ceil",
         "round", "count", "sum", "avg", "min", "max", "concat"]
BINARY_FN = ["days_between", "date_add", "contains", "coalesce", "min", "max",
             "sum", "avg", "count", "concat"]


def expr_src(rng, depth=0):
    if depth > 3:
        return field(rng) if rng.random() < 0.6 else lit(rng)
    r = rng.random()
    if r < 0.22:
        return field(rng)
    if r < 0.34:
        return lit(rng)
    if r < 0.46:
        return "(%s %s %s)" % (expr_src(rng, depth + 1),
                               rng.choice(["+", "-", "*", "/", "%"]),
                               expr_src(rng, depth + 1))
    if r < 0.58:
        return "(%s %s %s)" % (expr_src(rng, depth + 1),
                               rng.choice(["==", "!=", "<", "<=", ">", ">="]),
                               expr_src(rng, depth + 1))
    if r < 0.64:
        return "(%s %s %s)" % (expr_src(rng, depth + 1),
                               rng.choice(["and", "or"]), expr_src(rng, depth + 1))
    if r < 0.68:
        return "not (%s)" % expr_src(rng, depth + 1)
    if r < 0.72:
        return "- (%s)" % expr_src(rng, depth + 1)
    if r < 0.78:
        return "if(%s, %s, %s)" % (expr_src(rng, depth + 1), expr_src(rng, depth + 1),
                                   expr_src(rng, depth + 1))
    if r < 0.80:
        return rng.choice(["today()", "now()"])
    if r < 0.90:
        return "%s(%s)" % (rng.choice(UNARY), expr_src(rng, depth + 1))
    return "%s(%s, %s)" % (rng.choice(BINARY_FN), expr_src(rng, depth + 1),
                           expr_src(rng, depth + 1))


def main():
    rng = random.Random(SEED)
    counts = Counter()
    witnesses = defaultdict(list)
    for _ in range(N):
        src = expr_src(rng)
        rec = rnd_record(rng)
        ctx = {"now": "2024-05-01T12:00:00Z"} if rng.random() < 0.7 else {}
        o = run_case(src, rec, ctx)
        v = o["verdict"]
        counts[v] += 1
        if v in ("DIVERGE", "SQL_RAISE", "PY_RAISE", "UNCOMPILABLE", "NULLNESS"):
            key = _classify(o)
            counts["cls:" + key] += 1
            if len(witnesses[key]) < 4:
                witnesses[key].append(o)

    print("=== H. broad AST fuzz -- profile=%s  N=%d  seed=%d ===" % (PROFILE, N, SEED))
    print()
    for k in ("AGREE", "DIVERGE", "SQL_RAISE", "PY_RAISE", "BOTH_RAISE",
              "UNCOMPILABLE", "NULLNESS", "PARSE_ERROR"):
        if counts.get(k):
            print("    %-14s %6d   %6.3f%%" % (k, counts[k], 100.0 * counts[k] / N))
    print()
    print("    divergence classes (auto-clustered):")
    for k in sorted(witnesses, key=lambda z: -counts["cls:" + z]):
        print("      %-42s %5d" % (k, counts["cls:" + k]))
    print()
    for k in sorted(witnesses, key=lambda z: -counts["cls:" + z]):
        print("    --- %s (%d) ---" % (k, counts["cls:" + k]))
        for o in witnesses[k][:2]:
            print("        expr : %s" % o["expr"])
            print("        rec  : %s" % json.dumps(o["record"])[:220])
            print("        py   : %s%s" % (o.get("python"),
                                           "  RAISED " + str(o.get("python_raised")) if o.get("python_raised") else ""))
            print("        sql  : %s (%s)%s" % (o.get("sql_value"), o.get("sql_typeof"),
                                                "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
            if o.get("uncompilable"):
                print("        why  : %s" % o["uncompilable"])
            print()


def _classify(o):
    v = o["verdict"]
    if v == "UNCOMPILABLE":
        return "UNCOMPILABLE: " + str(o.get("uncompilable"))[:50]
    if v == "SQL_RAISE":
        m = str(o.get("sql_raised"))
        for pat in ("overflow", "underflow", "out of range", "division_by_zero",
                    "integer out of range", "invalid input syntax"):
            if pat in m:
                return "SQL_RAISE: " + pat
        return "SQL_RAISE: " + m[:50]
    if v == "PY_RAISE":
        return "PY_RAISE: " + str(o.get("python_raised"))[:50]
    if v == "NULLNESS":
        return "NULLNESS: jsonb 'null' vs SQL NULL"
    py, sq = o.get("python"), o.get("sql_value")
    if py is not None and sq == "None":
        return "DIVERGE: value -> NULL"
    if py == "None" and sq is not None:
        return "DIVERGE: NULL -> value"
    if o.get("compare_error"):
        return "DIVERGE: SQL value not representable in Python"
    return "DIVERGE: different value"


main()
