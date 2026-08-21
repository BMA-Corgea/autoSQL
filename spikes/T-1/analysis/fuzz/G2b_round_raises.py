"""T-1 fuzz seat, battery G2b -- xpr.round, item by item.

G2 batched its probes, so any chunk containing one raising row skipped the
comparison for the whole chunk.  This re-runs every probe individually and
classifies the outcome, so nothing is skipped and the SQL-raise rate is honest.
"""
import math
import random
import struct
import sys
from collections import Counter

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
    if k == 3:
        return rng.choice([-1, 1]) * struct.unpack("<d", struct.pack("<Q", rng.getrandbits(52)))[0]
    if k == 4:
        return rng.choice([-1, 1]) * 10.0 ** rng.randint(-300, 300) * rng.random()
    if k == 5:
        return rng.choice([0.0, -0.0, 1.0, -1.0, 0.5, 5e-324, 2.2250738585072014e-308,
                           1.7976931348623157e308, 2.0**52, 2.0**53, 2.0**-1074])
    return rng.choice([-1, 1]) * rng.random() * 10.0 ** rng.randint(-320, -290)


rng = random.Random(13)
N = 8000
counts = Counter()
witness = {}
mismatch = []
conn = differ.conn()
for _ in range(N):
    x = rand_double(rng)
    nd = float(rng.choice([0, 0, 1, 2, 3, -1, -2, -3, 6, 10, 15, 17,
                           rng.randint(-20, 20), rng.randint(-8, 8)]))
    try:
        p = expr._FUNCTIONS["round"]([x, nd], {})
        py_raise = None
    except Exception as e:
        p, py_raise = None, repr(e)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT xpr.round(%(x)s::float8, %(n)s::float8)", {"x": x, "n": nd})
            s = cur.fetchone()[0]
        sql_raise = None
    except Exception as e:
        s, sql_raise = None, str(e).splitlines()[0]

    if py_raise and sql_raise:
        k = "BOTH_RAISE"
    elif py_raise:
        k = "PY_RAISE_ONLY"
    elif sql_raise:
        k = "SQL_RAISE_ONLY"
    elif p == s or (p is None and s is None) or (p == 0 and s == 0):
        k = "AGREE"
    else:
        k = "MISMATCH"
        mismatch.append((x, nd, p, s))
    counts[k] += 1
    witness.setdefault(k, (x, nd, p, s, py_raise, sql_raise))

print("=== G2b. xpr.round vs _fn_round, %d probes, one query each ===" % N)
for k, v in counts.most_common():
    print("    %-16s %6d   %5.2f%%" % (k, v, 100.0 * v / N))
print()
for k in ("SQL_RAISE_ONLY", "PY_RAISE_ONLY", "BOTH_RAISE", "MISMATCH"):
    if k in witness:
        x, nd, p, s, pr, sr = witness[k]
        print("    witness %-15s round(%r, %r)" % (k, x, nd))
        print("        python = %r%s" % (p, "   RAISED " + pr if pr else ""))
        print("        sql    = %r%s" % (s, "   RAISED " + sr if sr else ""))
print()
print("    SQL_RAISE_ONLY is a totality violation: expr.py:640 says the evaluator")
print("    never raises for data reasons, and Postgres aborts the whole query.")
