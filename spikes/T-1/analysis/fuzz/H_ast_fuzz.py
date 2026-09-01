"""T-1 fuzz seat, battery H -- the broad differential fuzz.

Random expression SOURCE (parsed by the real expr.parse) x random record,
evaluated by the real expr.evaluate and by the compiled SQL against live
Postgres, then diffed with the mirrored comparison rule.

Distributions are deliberately BORING by default (--profile ordinary): the
values look like dashboard data.  --profile extreme turns on the pathological
magnitudes.  Reporting both keeps the reachability claim honest, because a
divergence rate measured on adversarial inputs says nothing about production.

T-3 (2026-08-22, EXPERIMENTS.md 1.4 items 2-4): three SUBSET profiles added --
sub_ordinary, sub_extreme, sub_unicode.  They generate ONLY expressions inside
the corrected 32-construct subset (7 functions: abs coalesce count if length
max min; arithmetic without %; all six comparisons -- with ==/!= over container
operands witnessed at runtime and DISCARDED, reading A of the closure
qualifier), verify EVERY generated expression mechanically against the subset
(closure_subset_coverage.py's walker -- never by inspection), widen the value
domain to the framing 5.3 magnitude table, split refusals from unexplained
raises (differ.py's T-3 verdicts), and print witnesses, fingerprints and wall
clock.  The three original profiles are untouched: their RNG draw sequences are
byte-identical to the 2026-08-19 record.

Usage: python H_ast_fuzz.py [ordinary|extreme|unicode|sub_ordinary|sub_extreme|sub_unicode] [N] [seed]
"""
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, '.')
import differ
from differ import run_case

PROFILE = sys.argv[1] if len(sys.argv) > 1 else "ordinary"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 2026

SUBSET = PROFILE.startswith("sub_")
BASE = PROFILE[4:] if SUBSET else PROFILE     # ordinary / extreme / unicode

FIELDS = ["a", "b", "c", "s", "t", "d", "e", "l", "o", "n", "flag"]

DATES = ["2024-01-01", "2024-02-29", "2023-12-31T23:59:59Z", "2024-06-15T12:30",
         "1999-01-01 00:00:00", "2024-01-01T00:00:00+05:30", "not a date", "",
         "0001-01-01", "9999-12-31", "2024-13-45"]

STRINGS = ["", "abc", "FAIL", "Fail", "pass", "0", "12", "1.5", " 7 ", "x y",
           "2024-01-01", "true", "null", "-3", "1e3", "abcabc"]

UNI_STRINGS = ["straße", "İstanbul", "ÅNGSTRÖM", "ǅ", "ﬁ", "ΣΊΣΥΦΟΣ", "ᾀ",
               "１２３", "١٢٣", " 12 ", "é", "é", "🙂", "ﬀ", "ß"]

# framing 5.3 half two: the magnitudes the domain MUST reach (py-mode-representable
# ones; above-DBL_MAX JSON numbers cannot exist in a Python record and are reached by
# spikes/T-3/t3_domain_gate.py in raw mode instead).
GUARD_LO = 1.79769313486231551e296     # largest that round-tripped pre-fix
GUARD_HI = 1.79769313486231587e296     # smallest CORRUPTED pre-fix (A2_boundary)
DBL_MAX = 1.7976931348623157e308
BELOW_DBL_MAX = 1.7976931348623155e308
SUB_EXTREME_NUMS = [
    0.0, -0.0, 1.0, -1.0, 0.5, 0.1, 1 / 3, 1e-7, 42.0, 12345.678,
    1e16, 1e17, 1e21, 1e22,
    5e-324, 1e-320, 2.2250738585072014e-308,          # subnormals + smallest normal
    2.0 ** 53, 2.0 ** 53 + 2,                          # integer-precision boundary
    1e200,                                             # composes infinity: 1e200*1e200
    1e295, 1.7e296, GUARD_LO, GUARD_HI,                # the old guard boundary
    1e300, BELOW_DBL_MAX, DBL_MAX,                     # the real limit, from below
]
SUB_COERCE_STRINGS = [" 7 ", "1e3", "１２３"]           # framing 5.3, D.6's class


def rnd_num(rng):
    if SUBSET and BASE == "extreme":
        if rng.random() < 0.75:
            return rng.choice(SUB_EXTREME_NUMS)
        return rng.choice([-1, 1]) * 10.0 ** rng.randint(-320, 308)
    if PROFILE == "extreme":
        return rng.choice([
            0.0, -0.0, 1.0, -1.0, 0.5, 1e-7, 1e16, 1e17, 1e21, 1e22,
            5e-324, 1e-320, 2.2250738585072014e-308, 1e295, 1.7e296, 1e300,
            1.7976931348623157e308, 2.0**53, 2.0**53 + 2, 0.1, 1 / 3,
            rng.uniform(-1e6, 1e6), rng.choice([-1, 1]) * 10.0 ** rng.randint(-300, 300),
        ])
    return rng.choice([0, 1, -1, 2, 3, 7, 10, 100, 0.5, 1.5, -2.25, 3.14159,
                       42, 1000, 99999, 0.1, -0.001, 12345.678, 2, 5])


def rnd_string(rng):
    if SUBSET:
        pool = (UNI_STRINGS if BASE == "unicode" else STRINGS) + SUB_COERCE_STRINGS
        return rng.choice(pool)
    return rng.choice(UNI_STRINGS if PROFILE == "unicode" else STRINGS)


def rnd_value(rng, depth=0):
    r = rng.random()
    if r < 0.30:
        return rnd_num(rng)
    if r < 0.50:
        return rnd_string(rng)
    if r < 0.58:
        return rng.choice(DATES)     # inert strings under the subset (no date builtins)
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
        if SUBSET and isinstance(v, float):
            # a literal token that parses to inf is a compile-time refusal by design
            # (KNOWN_DIVERGENCES/numeric_literal_inf); keep generated literals finite so
            # an UNCOMPILABLE can only ever mean a generator leak (stop rule 3).
            if v != v or v in (float("inf"), float("-inf")):
                v = 0.0
        return repr(float(v)) if isinstance(v, float) else str(v)
    if r < 0.75:
        return json.dumps(rnd_string(rng))
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

# the corrected subset's SEVEN functions -- FINDINGS.md 5.7 via closure_subset_coverage
UNARY_SUB = ["length", "abs", "count", "min", "max"]
BINARY_FN_SUB = ["coalesce", "min", "max", "count"]


def expr_src(rng, depth=0):
    if depth > 3:
        return field(rng) if rng.random() < 0.6 else lit(rng)
    r = rng.random()
    if r < 0.22:
        return field(rng)
    if r < 0.34:
        return lit(rng)
    if r < 0.46:
        ops = ["+", "-", "*", "/"] if SUBSET else ["+", "-", "*", "/", "%"]
        return "(%s %s %s)" % (expr_src(rng, depth + 1), rng.choice(ops),
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
        if SUBSET:
            return "coalesce(%s, %s)" % (expr_src(rng, depth + 1), expr_src(rng, depth + 1))
        return rng.choice(["today()", "now()"])
    if r < 0.90:
        return "%s(%s)" % (rng.choice(UNARY_SUB if SUBSET else UNARY),
                           expr_src(rng, depth + 1))
    return "%s(%s, %s)" % (rng.choice(BINARY_FN_SUB if SUBSET else BINARY_FN),
                           expr_src(rng, depth + 1), expr_src(rng, depth + 1))


# ------------------------------------------------------------------------------------
# T-3 subset machinery
# ------------------------------------------------------------------------------------
SUBSET_FUNCTIONS = frozenset("abs coalesce count if length max min".split())
SUBSET_BIN_OPS = frozenset(("+", "-", "*", "/"))
SUBSET_TAGS = frozenset(("num", "str", "bool", "null", "field", "neg", "not",
                         "and", "or", "cmp", "bin", "call"))
INDEX_LIMIT = 2 ** 31

_csc = None


def _load_csc():
    """closure_subset_coverage.py IS the subset checker (EXPERIMENTS.md 1.4); import its
    walker rather than re-implementing it, so the gate and the coverage meter cannot
    drift apart."""
    global _csc
    if _csc is None:
        import importlib.util
        p = ("/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/"
             "closure_subset_coverage.py")
        spec = importlib.util.spec_from_file_location("csc_t3", p)
        _csc = importlib.util.module_from_spec(spec)
        sys.modules["csc_t3"] = _csc
        spec.loader.exec_module(_csc)
    return _csc


def subset_gate(ast):
    """Mechanical: which constructs does this AST use, and are they ALL inside the
    corrected subset?  Returns (ok, why)."""
    csc = _load_csc()
    acc = csc.new_acc()
    csc.walk(ast, acc)
    if not acc["tags"] <= SUBSET_TAGS:
        return False, "tags outside subset: %s" % sorted(acc["tags"] - SUBSET_TAGS)
    if not acc["functions"] <= SUBSET_FUNCTIONS:
        return False, "functions outside subset: %s" % sorted(acc["functions"] - SUBSET_FUNCTIONS)
    if not acc["bin_ops"] <= SUBSET_BIN_OPS:
        return False, "operators outside subset: %s" % sorted(acc["bin_ops"] - SUBSET_BIN_OPS)
    if any(abs(i) >= INDEX_LIMIT for i in acc["literal_indices"]):
        return False, "literal index >= 2**31 (D19)"
    return True, None


def container_reaches_eq(ast, rec, ctx):
    """Reading A of the closure qualifier: does a container operand actually reach _eq
    at runtime for this case?  (==/!= over container operands is OUTSIDE the subset;
    such draws are discarded and counted, never silently kept.)"""
    E = differ.expr
    orig = E._eq
    seen = [False]

    def spy(a, b):
        if isinstance(a, (list, tuple, dict)) or isinstance(b, (list, tuple, dict)):
            seen[0] = True
        return orig(a, b)

    E._eq = spy
    try:
        try:
            E.evaluate(ast, rec, ctx or {})
        except Exception:
            pass
    finally:
        E._eq = orig
    return seen[0]


def _contains_value(v, pred):
    if pred(v):
        return True
    if isinstance(v, (list, tuple)):
        return any(_contains_value(x, pred) for x in v)
    if isinstance(v, dict):
        return any(_contains_value(x, pred) for x in v.values())
    return False


def _isf(target):
    return lambda v: isinstance(v, float) and not isinstance(v, bool) and v == target \
        and (target != 0.0 or str(v) == str(target))


WITNESS_ROWS = [
    ("old guard boundary, below (1.79769313486231551e296)", _isf(GUARD_LO)),
    ("old guard boundary, above (1.79769313486231587e296)", _isf(GUARD_HI)),
    ("real limit DBL_MAX (1.7976931348623157e308)", _isf(DBL_MAX)),
    ("real limit, just below (1.7976931348623155e308)", _isf(BELOW_DBL_MAX)),
    ("1e200 (infinity composable: 1e200*1e200)", _isf(1e200)),
    ("subnormal 5e-324", _isf(5e-324)),
    ("subnormal 1e-320", _isf(1e-320)),
    ("2**53", _isf(2.0 ** 53)),
    ("2**53 + 2", _isf(2.0 ** 53 + 2)),
    ("0.0", lambda v: isinstance(v, float) and v == 0.0 and str(v) == "0.0"),
    ("-0.0", lambda v: isinstance(v, float) and v == 0.0 and str(v) == "-0.0"),
    ("coercing string ' 7 '", lambda v: v == " 7 "),
    ("coercing string '1e3'", lambda v: v == "1e3"),
    ("coercing string '１２３' (full-width)", lambda v: v == "１２３"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    rng = random.Random(SEED)
    counts = Counter()
    witnesses = defaultdict(list)
    wrong_answers = []            # every class 1-4 case, in full
    unexplained = []
    domain_hits = {}              # witness row -> (expr, rec)
    discarded = 0
    t0 = time.monotonic()

    drawn = 0
    while drawn < N:
        src = expr_src(rng)
        rec = rnd_record(rng)
        ctx = {"now": "2024-05-01T12:00:00Z"} if rng.random() < 0.7 else {}
        drawn += 1

        if SUBSET:
            try:
                ast = differ.expr.parse(src)
            except Exception:
                counts["PARSE_ERROR"] += 1
                continue
            ok, why = subset_gate(ast)
            if not ok:
                print("GENERATOR LEAK (inadmissibility item 4 / stop rule 3): %s" % why)
                print("  expr: %s" % src)
                print("EVERY NUMBER THIS BATTERY HAS PRODUCED IS VOID.")
                sys.exit(3)
            if container_reaches_eq(ast, rec, ctx):
                discarded += 1
                counts["DISCARDED_container_eq"] += 1
                continue

        o = run_case(src, rec, ctx)
        v = o["verdict"]
        counts[v] += 1
        if v == "SQL_REFUSAL":
            counts["refusal:" + str(o.get("refusal_kind"))] += 1
        if SUBSET and v == "UNCOMPILABLE":
            print("STOP RULE 3: subset-legal expression came back UNCOMPILABLE")
            print("  expr: %s\n  why : %s" % (src, o.get("uncompilable")))
            print("EVERY NUMBER THIS BATTERY HAS PRODUCED IS VOID.")
            sys.exit(3)
        if v in ("DIVERGE", "SQL_RAISE", "PY_RAISE", "UNCOMPILABLE", "NULLNESS"):
            key = _classify(o)
            counts["cls:" + key] += 1
            if len(witnesses[key]) < 4:
                witnesses[key].append(o)
            if v in ("DIVERGE", "PY_RAISE") and len(wrong_answers) < 200:
                wrong_answers.append(o)
            if v == "SQL_RAISE" and len(unexplained) < 50:
                unexplained.append(o)
        if SUBSET and v != "DISCARDED":
            for name, pred in WITNESS_ROWS:
                if name not in domain_hits and _contains_value(rec, pred):
                    domain_hits[name] = (src, rec)

    wall = time.monotonic() - t0

    print("=== H. broad AST fuzz -- profile=%s  N=%d  seed=%d ===" % (PROFILE, N, SEED))
    if SUBSET:
        print("    SUBSET battery: every counted expression mechanically verified inside")
        print("    the corrected 32-construct subset (closure_subset_coverage walker);")
        print("    ==/!= draws whose operands reached _eq as containers: DISCARDED, counted.")
    print()
    for k in ("AGREE", "DIVERGE", "SQL_REFUSAL", "SQL_RAISE", "PY_RAISE", "BOTH_RAISE",
              "UNCOMPILABLE", "NULLNESS", "PARSE_ERROR", "DISCARDED_container_eq"):
        if counts.get(k):
            print("    %-24s %6d   %6.3f%%" % (k, counts[k], 100.0 * counts[k] / N))
    ran = sum(counts.get(k, 0) for k in ("AGREE", "DIVERGE", "SQL_REFUSAL", "SQL_RAISE",
                                         "PY_RAISE", "BOTH_RAISE", "NULLNESS"))
    print("    %-24s %6d   (agree+diverge+refusal+raise+nullness; refusals stay IN)" % ("ran =", ran))
    for k in sorted(counts):
        if k.startswith("refusal:"):
            print("      %-22s %6d" % (k, counts[k]))
    print()
    print("    divergence classes (auto-clustered):")
    for k in sorted(witnesses, key=lambda z: -counts["cls:" + z]):
        print("      %-52s %5d" % (k, counts["cls:" + k]))
    print()
    for k in sorted(witnesses, key=lambda z: -counts["cls:" + z]):
        print("    --- %s (%d) ---" % (k, counts["cls:" + k]))
        for o in witnesses[k][:2]:
            print("        expr : %s" % o["expr"])
            print("        rec  : %s" % json.dumps(o["record"], ensure_ascii=False)[:220])
            print("        py   : %s%s" % (o.get("python"),
                                           "  RAISED " + str(o.get("python_raised")) if o.get("python_raised") else ""))
            print("        sql  : %s (%s)%s" % (o.get("sql_value"), o.get("sql_typeof"),
                                                "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
            if o.get("uncompilable"):
                print("        why  : %s" % o["uncompilable"])
            print()

    if SUBSET:
        print("    ALL wrong-answer cases (classes 1-4), in full -- %d found:" % len(wrong_answers))
        for o in wrong_answers:
            print("      [%s] %s" % (_classify(o), o["expr"]))
            print("            rec=%s" % json.dumps(o["record"], ensure_ascii=False)[:200])
            print("            py=%s%s  sql=%s (%s)"
                  % (o.get("python"),
                     " RAISED " + str(o.get("python_raised")) if o.get("python_raised") else "",
                     o.get("sql_value"), o.get("sql_typeof")))
        print()
        print("    domain-gate witnesses (framing 5.3 half two; py-mode rows):")
        for name, _ in WITNESS_ROWS:
            hit = domain_hits.get(name)
            if hit:
                print("      REACHED   %-46s e.g. %s" % (name, hit[0][:60]))
            else:
                print("      UNTESTED  %-46s (not reached by this battery)" % name)
        print()
        print("    fingerprints (inadmissibility item 5):")
        gims = "/home/corgea/Desktop/Coding Projects/GIMS-Project/core/dashboard/expr.py"
        proto = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto"
        print("      expr.py     sha256=%s" % sha(gims)[:16])
        print("      compile.py  sha256=%s  (file)" % sha(proto + "/compile.py")[:16])
        # T-10: the FILE and what is INSTALLED are different claims. Print both.
        # A battery that names the runtime it hoped for is how 42 outputs came to
        # carry the wrong provenance during T-6.
        file_sha = sha(proto + "/runtime.sql")[:16]
        try:
            inst_sha = differ.installed_runtime_sha()[:16]
        except Exception as exc:                       # never fail a battery over a label
            inst_sha = "unavailable (%s)" % type(exc).__name__
        print("      runtime.sql sha256=%s  (file on disk)" % file_sha)
        print("      xpr schema  sha256=%s  (INSTALLED -- this is what ran)" % inst_sha)
        if inst_sha != file_sha and not inst_sha.startswith("unavailable"):
            print("      NOTE: installed runtime differs from %s/runtime.sql." % proto)
            print("            That is EXPECTED when a ticket installs its own build;")
            print("            it is a DEFECT if you believed they were the same.")
        print("      efd requested=%s read-back=%s  seed=%d  N=%d  wall=%.1fs"
              % (differ.EFD, differ.EFD_READBACK, SEED, N, wall))


def _classify(o):
    v = o["verdict"]
    if v == "UNCOMPILABLE":
        return "UNCOMPILABLE: " + str(o.get("uncompilable"))[:50]
    if v == "SQL_RAISE":
        return "SQL_RAISE (unexplained): " + str(o.get("sql_raised"))[:50]
    if v == "PY_RAISE":
        return "PY_RAISE (class 4): " + str(o.get("python_raised"))[:50]
    if v == "NULLNESS":
        return "NULLNESS: jsonb 'null' vs SQL NULL"
    py, sq = o.get("python"), o.get("sql_value")
    if py is not None and sq == "None":
        return "DIVERGE (class 2): value -> NULL"
    if py == "None" and sq is not None:
        return "DIVERGE (class 3): NULL -> value"
    if o.get("compare_error"):
        return "DIVERGE (class 1): SQL value not representable in Python"
    return "DIVERGE (class 1): different value"


if __name__ == "__main__":
    main()
