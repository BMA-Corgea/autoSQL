"""T-6 P2 - what exactly did the comparison-rule change absorb?

FRAMING section 4 makes this mandatory, not optional: the rule that decides
pass/fail was changed in the middle of a re-run that previously failed, so every
case the change reclassified has to be named, and the strict number has to sit
next to the recursive one.

Two checks:
  1. ARITHMETIC - no case moved AGREE -> DIVERGE. The recursive rule also tightens
     (bools stop conflating with 1 inside containers), so a new divergence is
     possible in principle and would be a finding.
  2. SHAPE - every reclassified case is M2's container shape: both engines
     returned a container, and every leaf pair is equal as floats. Anything else
     is a PASS-WITH-NOTE per FRAMING section 5.
"""
import ast, io, os, re, sys, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
EPS = 1e-9

COUNT = re.compile(r"^\s+(AGREE|DIVERGE|SQL_REFUSAL|SQL_RAISE|NULLNESS|PARSE_ERROR)\s+(\d+)")
# The COMPACT witness list at the tail of each battery carries every divergence
# (the detailed blocks near the top are only the first couple of samples).
WIT = re.compile(r"^\s+py=(?P<py>.*?)\s\ssql=(?P<sql>.*)$", re.M)


def counts(path):
    out = {}
    for line in io.open(path, encoding="utf-8"):
        m = COUNT.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = int(m.group(2))
    return out


def leaves_float_equal(a, b):
    """Every leaf pair equal as floats, containers structurally identical."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=EPS)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(leaves_float_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(leaves_float_equal(a[k], b[k]) for k in a)
    return a == b


report = []
report.append("P2 - the strict/recursive delta, per setting")
report.append("=" * 96)
report.append("%-14s %-5s %8s %8s %8s %8s %8s   %s" % (
    "battery", "efd", "A(str)", "D(str)", "A(rec)", "D(rec)", "moved", "verdict"))
report.append("-" * 96)

problems = []
total_moved = 0
for efd in ["1", "0", "-3"]:
    for prof in ["sub_ordinary", "sub_unicode", "sub_extreme"]:
        s = counts(os.path.join(OUT, "H_%s_efd%s_strict.txt" % (prof, efd)))
        r = counts(os.path.join(OUT, "H_%s_efd%s_recursive.txt" % (prof, efd)))
        As, Ds = s.get("AGREE", 0), s.get("DIVERGE", 0)
        Ar, Dr = r.get("AGREE", 0), r.get("DIVERGE", 0)
        moved = Ar - As
        total_moved += max(moved, 0)
        if As + Ds != Ar + Dr:
            v = "POPULATION CHANGED <- INVALID"
            problems.append("%s efd=%s: agree+diverge differs between modes" % (prof, efd))
        elif moved < 0:
            v = "AGREE->DIVERGE x%d <- FINDING" % (-moved)
            problems.append("%s efd=%s: the recursive rule created %d new divergences"
                            % (prof, efd, -moved))
        elif moved == 0:
            v = "rule made no difference"
        else:
            v = "%d moved DIVERGE->AGREE" % moved
        report.append("%-14s %-5s %8d %8d %8d %8d %8d   %s" % (prof, efd, As, Ds, Ar, Dr, moved, v))

report.append("-" * 96)
report.append("")

# Shape check on the reclassified cases, read from the strict witnesses.
report.append("SHAPE of every reclassified case (strict witnesses, efd=1 sub_extreme):")
report.append("-" * 96)
text = io.open(os.path.join(OUT, "H_sub_extreme_efd1_strict.txt"), encoding="utf-8").read()
shapes, unparsed = {}, 0
for m in WIT.finditer(text):
    try:
        py = ast.literal_eval(m.group("py").strip())
        sql_raw = m.group("sql")
        sql_raw = re.sub(r"\s*\((array|object|number|string|boolean)\)\s*$", "", sql_raw)
        sql = ast.literal_eval(sql_raw)
    except Exception:
        unparsed += 1
        continue
    both_containers = isinstance(py, (list, dict)) and isinstance(sql, (list, dict))
    equal_as_floats = leaves_float_equal(py, sql)
    key = ("container" if both_containers else "SCALAR") + \
          ("/leaves-equal-as-floats" if equal_as_floats else "/LEAVES DIFFER")
    shapes[key] = shapes.get(key, 0) + 1

for k, v in sorted(shapes.items()):
    flag = "" if k == "container/leaves-equal-as-floats" else "   <- NOT the M2 shape"
    report.append("  %-42s %4d%s" % (k, v, flag))
    if flag:
        problems.append("reclassified case is not the M2 container shape: %s" % k)
if unparsed:
    report.append("  (%d witness blocks could not be parsed and were not classified)" % unparsed)

report.append("")
report.append("=" * 96)
if problems:
    report.append("PASS-WITH-NOTE or worse -- %d thing(s) to surface:" % len(problems))
    for p in problems:
        report.append("  - " + p)
else:
    report.append("CLEAN: the rule change only ever moved DIVERGE -> AGREE, it created no new")
    report.append("divergence anywhere, and every case it absorbed is M2's container shape --")
    report.append("both engines returned a container whose leaves are equal as floats.")

text_out = "\n".join(report)
io.open(os.path.join(HERE, "P2_rule_delta.txt"), "w", encoding="utf-8").write(text_out + "\n")
print(text_out)
sys.exit(1 if problems else 0)
