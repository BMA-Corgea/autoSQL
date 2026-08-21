"""T-1 fuzz seat, battery K.

sum()/avg() -- expr.py:506-509 uses Python's builtin sum().  On CPython 3.12+
builtin sum() performs NEUMAIER COMPENSATED summation over floats (this venv is
3.12.3).  xpr.reduce_arr (runtime.sql:409-420) uses Postgres's sum(float8),
which is a plain left-to-right accumulation.

The two are not the same function.  They agree only when no cancellation occurs.
"""
import math
import random
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case, matches
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr

print("=== K0. the mechanism, stated once and checked ===")
vals = [1e16, 1.0, -1e16]
manual = 0.0
for v in vals:
    manual += v
print("    builtin sum(%r)               = %r" % (vals, sum(vals)))
print("    plain left-to-right accumulation = %r" % manual)
print("    -> CPython 3.12's sum() is compensated; %s" % sys.version.split()[0])
with differ.conn().cursor() as cur:
    cur.execute("SELECT sum(v ORDER BY o) FROM unnest(%(v)s::float8[]) WITH ORDINALITY t(v,o)",
                {"v": vals})
    print("    postgres sum(float8 ORDER BY ord) = %r" % cur.fetchone()[0])
print()


def profiles(rng):
    """Lists that look like dashboard data, and lists that stress cancellation."""
    k = rng.randrange(6)
    n = rng.randrange(2, 9)
    if k == 0:                                   # money-ish, mixed sign
        return [round(rng.uniform(-10000, 10000), 2) for _ in range(n)]
    if k == 1:                                   # one big number, small corrections
        big = rng.choice([1e9, 1e12, 1e15, 1e16, 1e17])
        return [big] + [rng.uniform(-10, 10) for _ in range(n - 2)] + [-big]
    if k == 2:                                   # running balance: credits and debits
        v = [rng.uniform(0, 1e6) for _ in range(n)]
        return v + [-x for x in v]
    if k == 3:                                   # tiny + huge
        return [rng.uniform(-1, 1) * 10.0**rng.randint(-8, 8) for _ in range(n)]
    if k == 4:                                   # plain positives
        return [rng.uniform(0, 1000) for _ in range(n)]
    return [rng.choice([0.1, 0.2, 0.3, 1 / 3, 1e16, -1e16, 1.0, -1.0, 1e-8])
            for _ in range(n)]


NAMES = {0: "money, mixed sign", 1: "big value +- small corrections",
         2: "credits then matching debits", 3: "mixed magnitudes",
         4: "plain positives", 5: "hand-picked awkward values"}


def run(profile_filter=None, N=20000, seed=5):
    rng = random.Random(seed)
    tot = Counter = {}
    bad = []
    n_tested = 0
    with differ.conn().cursor() as cur:
        for _ in range(N):
            k = rng.randrange(6)
            if profile_filter is not None and k != profile_filter:
                continue
            rng2 = rng
            saved = rng.getstate()
            rng.setstate(saved)
            lst = None
            # regenerate with the chosen k
            n = rng.randrange(2, 9)
            if k == 0:
                lst = [round(rng.uniform(-10000, 10000), 2) for _ in range(n)]
            elif k == 1:
                big = rng.choice([1e9, 1e12, 1e15, 1e16, 1e17])
                lst = [big] + [rng.uniform(-10, 10) for _ in range(max(n - 2, 1))] + [-big]
            elif k == 2:
                v = [rng.uniform(0, 1e6) for _ in range(n)]
                lst = v + [-x for x in v]
            elif k == 3:
                lst = [rng.uniform(-1, 1) * 10.0**rng.randint(-8, 8) for _ in range(n)]
            elif k == 4:
                lst = [rng.uniform(0, 1000) for _ in range(n)]
            else:
                lst = [rng.choice([0.1, 0.2, 0.3, 1 / 3, 1e16, -1e16, 1.0, -1.0, 1e-8])
                       for _ in range(n)]
            n_tested += 1
            p = expr._FUNCTIONS["sum"]([lst], {})
            cur.execute("SELECT sum(v ORDER BY o) FROM unnest(%(v)s::float8[]) "
                        "WITH ORDINALITY t(v,o)", {"v": lst})
            s = cur.fetchone()[0]
            tot[k] = tot.get(k, 0) + 1
            if not matches(s, p):
                bad.append((k, lst, p, s))
    return n_tested, tot, bad


n, tot, bad = run()
print("=== K1. sum() over %d random lists, by profile ===" % n)
from collections import Counter as C
byk = C(b[0] for b in bad)
print("    %-34s %8s %8s %8s" % ("profile", "lists", "diverge", "rate"))
for k in sorted(tot):
    print("    %-34s %8d %8d %7.2f%%" % (NAMES[k], tot[k], byk.get(k, 0),
                                         100.0 * byk.get(k, 0) / tot[k]))
print("    %-34s %8d %8d %7.2f%%" % ("TOTAL", n, len(bad), 100.0 * len(bad) / n))
print()
print("    the divergence is ALWAYS larger than the fixture's float_epsilon (1e-9)?")
worst = sorted(bad, key=lambda b: -abs((b[2] or 0) - (b[3] or 0)))[:8]
for k, lst, p, s in worst:
    print("      [%s] python=%-24r postgres=%-24r  |diff|=%r" % (
        NAMES[k], p, s, abs(p - s)))
print()
print("=== K2. end to end through the compiler ===")
for lst in ([1e16, 1.0, -1e16], [1e17, 3.0, -1e17], [0.1] * 10,
            [1e9, 0.0001, -1e9], [1234567.89, -1234567.88, 0.01]):
    o = run_case("sum($.l)", {"l": lst})
    o2 = run_case("avg($.l)", {"l": lst})
    print("    sum %-34s %-12s py=%-22s sql=%s" % (
        repr(lst)[:34], "<" + o["verdict"] + ">", o.get("python"), o.get("sql_value")))
    print("    avg %-34s %-12s py=%-22s sql=%s" % (
        "", "<" + o2["verdict"] + ">", o2.get("python"), o2.get("sql_value")))
