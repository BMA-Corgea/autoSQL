"""T-6 P4 - what did the loud refusal COST?

A refusal is an allowed outcome under the standing ruling, and a refusal that
replaces a silent wrong number is a straight win. But xpr.num refuses at COERCION
time, deep inside an expression -- it cannot know whether that value would have
changed the final answer. So some refusals land on expressions that previously
produced the RIGHT answer, because the wrong NULL was absorbed downstream (another
term dominated a max(), a comparison went the same way regardless).

This counts them, per battery, at the pinned setting. It is arithmetic over the
recorded counts of T-3 (no refusal) and T-6 (refusal), on identical seeds, so
every expression population is the same.
"""
import io, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
T3 = os.path.join(HERE, "..", "..", "T-3", "out")
T6 = os.path.join(HERE, "..", "out")

def counts(path):
    t = io.open(path, encoding="utf-8").read()
    g = lambda k: (lambda m: int(m.group(1)) if m else 0)(re.search(r"^\s+%s\s+(\d+)" % k, t, re.M))
    rk = dict((a, int(b)) for a, b in re.findall(r"refusal:(\w+)\s+(\d+)", t))
    return dict(agree=g("AGREE"), diverge=g("DIVERGE"), refusal=g("SQL_REFUSAL"),
                raise_=g("SQL_RAISE"), coercion=rk.get("coercion", 0))

rows, tot = [], dict(fixed=0, cost=0, coercion=0)
for prof in ["sub_ordinary", "sub_unicode", "sub_extreme"]:
    a = counts(os.path.join(T3, "H_%s_efd1.txt" % prof))
    b = counts(os.path.join(T6, "H_%s_efd1_strict.txt" % prof))
    # Every coercion refusal in T-6 was, in T-3, either a divergence (a real bug the
    # refusal fixes) or an agreement (a correct answer the refusal now costs).
    fixed = a["diverge"] - b["diverge"]
    cost = b["coercion"] - fixed
    rows.append((prof, a["diverge"], b["coercion"], fixed, cost, a["agree"] + a["diverge"] + a["refusal"]))
    tot["fixed"] += fixed; tot["cost"] += cost; tot["coercion"] += b["coercion"]

out = ["P4 - the price of the loud refusal, at the pinned setting (efd=1)", "=" * 92,
       "%-14s %10s %10s %12s %12s %10s" % (
           "battery", "T-3 diverge", "refusals", "bugs fixed", "answers lost", "ran"),
       "-" * 92]
for prof, d3, ref, fixed, cost, ran in rows:
    out.append("%-14s %10d %10d %12d %12d %10d" % (prof, d3, ref, fixed, cost, ran))
out.append("-" * 92)
out.append("%-14s %10s %10d %12d %12d" % ("TOTAL", "", tot["coercion"], tot["fixed"], tot["cost"]))
out.append("")
share = 100.0 * tot["cost"] / tot["coercion"] if tot["coercion"] else 0
out.append("Of %d coercion refusals at the pinned setting, %d (%.0f%%) replaced a SILENT WRONG"
           % (tot["coercion"], tot["fixed"], 100 - share))
out.append("NUMBER -- a straight win -- and %d (%.0f%%) replaced an answer that was already"
           % (tot["cost"], share))
out.append("CORRECT, because the bad NULL was absorbed downstream and never reached the result.")
out.append("")
out.append("This is inherent to the design, not a defect in it: xpr.num refuses where the")
out.append("coercion happens, and at that point nothing knows whether the value will matter.")
out.append("Refusing only values that change the answer is not expressible in the compiled SQL.")
text = "\n".join(out)
io.open(os.path.join(HERE, "P4_refusal_cost.txt"), "w").write(text + "\n")
print(text)
