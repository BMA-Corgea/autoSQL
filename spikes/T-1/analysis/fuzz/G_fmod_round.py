"""T-1 fuzz seat, battery G -- function-level differential fuzz of the two
hand-written numeric kernels.

  xpr.fmod  (runtime.sql:220-242)  vs  math.fmod         (expr.py:622-624)
  xpr.round (runtime.sql:247-259)  vs  _fn_round         (expr.py:517-527)

These are tested at the FUNCTION level (direct SQL calls) rather than through the
compiler, so the f8 range-guard defect cannot mask or manufacture a result.
"""
import math
import random
import struct
import sys

sys.path.insert(0, '.')
import differ
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr


def rand_double(rng):
    k = rng.randrange(7)
    if k == 0:
        return rng.uniform(-1e3, 1e3)
    if k == 1:
        while True:
            v = struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]
            if math.isfinite(v):
                return v
    if k == 2:
        return float(rng.randint(-10**9, 10**9))
    if k == 3:                                     # subnormal
        return rng.choice([-1, 1]) * struct.unpack("<d", struct.pack("<Q", rng.getrandbits(52)))[0]
    if k == 4:
        return rng.choice([-1, 1]) * 10.0 ** rng.randint(-300, 300) * rng.random()
    if k == 5:
        return rng.choice([0.0, -0.0, 1.0, -1.0, 0.5, 5e-324, 2.2250738585072014e-308,
                           1.7976931348623157e308, 2.0**52, 2.0**53, 2.0**-1074])
    return rng.choice([-1, 1]) * rng.random() * 10.0 ** rng.randint(-320, -290)


def fuzz_fmod(n=40000, seed=11):
    rng = random.Random(seed)
    pairs = []
    while len(pairs) < n:
        x, y = rand_double(rng), rand_double(rng)
        pairs.append((x, y))
    bad = []
    with differ.conn().cursor() as cur:
        for i in range(0, len(pairs), 2000):
            chunk = pairs[i:i + 2000]
            xs = [p[0] for p in chunk]
            ys = [p[1] for p in chunk]
            try:
                cur.execute(
                    "SELECT xpr.fmod(x, y) FROM unnest(%(x)s::float8[], %(y)s::float8[]) "
                    "WITH ORDINALITY t(x, y, o) ORDER BY o", {"x": xs, "y": ys})
                res = [r[0] for r in cur.fetchall()]
            except Exception as e:                                  # a raise is itself a finding
                for x, y in chunk:
                    try:
                        cur.execute("SELECT xpr.fmod(%(x)s::float8, %(y)s::float8)", {"x": x, "y": y})
                        res_one = cur.fetchone()[0]
                    except Exception as e2:
                        bad.append((x, y, "PY:" + repr(_pyfmod(x, y)), "SQL RAISED " + str(e2).splitlines()[0]))
                        continue
                continue
            for (x, y), s in zip(chunk, res):
                p = _pyfmod(x, y)
                if not _same(p, s):
                    bad.append((x, y, p, s))
    return len(pairs), bad


def _pyfmod(x, y):
    # expr.py:622-624: None if rn == 0 else math.fmod(ln, rn)
    if y == 0:
        return None
    return math.fmod(x, y)


def _same(p, s):
    if p is None or s is None:
        return p is None and s is None
    if math.isnan(p) and math.isnan(s):
        return True
    return p == s or (p == 0 and s == 0)


def fuzz_round(n=40000, seed=13):
    rng = random.Random(seed)
    bad = []
    raises = []
    cases = []
    for _ in range(n):
        x = rand_double(rng)
        nd = rng.choice([0, 0, 1, 2, 3, -1, -2, -3, 6, 10, 15, 17,
                         rng.randint(-20, 20), rng.randint(-8, 8)])
        cases.append((x, float(nd)))
    with differ.conn().cursor() as cur:
        for i in range(0, len(cases), 2000):
            chunk = cases[i:i + 2000]
            xs = [c[0] for c in chunk]
            ns = [c[1] for c in chunk]
            try:
                cur.execute(
                    "SELECT xpr.round(x, n) FROM unnest(%(x)s::float8[], %(n)s::float8[]) "
                    "WITH ORDINALITY t(x, n, o) ORDER BY o", {"x": xs, "n": ns})
                res = [r[0] for r in cur.fetchall()]
            except Exception as e:
                cur.execute("ROLLBACK") if False else None
                for x, nd in chunk:
                    try:
                        cur.execute("SELECT xpr.round(%(x)s::float8, %(n)s::float8)", {"x": x, "n": nd})
                        res_one = cur.fetchone()[0]
                    except Exception as e2:
                        raises.append((x, nd, str(e2).splitlines()[0]))
                continue
            for (x, nd), s in zip(chunk, res):
                try:
                    p = expr._FUNCTIONS["round"]([x, nd], {})
                except Exception as e:
                    raises.append((x, nd, "PYTHON RAISED " + repr(e)))
                    continue
                if not _same(p, s):
                    bad.append((x, nd, p, s))
    return len(cases), bad, raises


print("=== G1. xpr.fmod vs math.fmod ===")
n, bad = fuzz_fmod()
print("    %d random (x, y) pairs incl. subnormals, 2^-1074, DBL_MAX, +-0" % n)
print("    mismatches: %d" % len(bad))
for x, y, p, s in bad[:25]:
    print("      fmod(%r, %r)  python=%r  sql=%r" % (x, y, p, s))
print()

print("=== G2. xpr.round vs _fn_round ===")
n, bad, raises = fuzz_round()
print("    %d random (x, ndigits) pairs" % n)
print("    value mismatches: %d" % len(bad))
for x, nd, p, s in bad[:25]:
    print("      round(%r, %r)  python=%r  sql=%r" % (x, nd, p, s))
print("    raises (either side): %d" % len(raises))
seen = set()
for x, nd, msg in raises:
    k = msg[:60]
    if k in seen:
        continue
    seen.add(k)
    print("      round(%r, %r)  -> %s" % (x, nd, msg))
