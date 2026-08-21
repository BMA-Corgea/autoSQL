"""T-1 fuzz seat, battery F1b -- how OFTEN does xpr.ecma_num disagree with _num_to_str,
and why.

Batched: one query per 5000 values via unnest, so this can cover a large sample.
Every value is kept under the 1.7976931348623157e296 f8 guard so this experiment
measures FORMATTING only.
"""
import math
import random
import struct
import sys

sys.path.insert(0, '.')
import differ
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr


def batch(vals):
    out = []
    with differ.conn().cursor() as cur:
        for i in range(0, len(vals), 5000):
            chunk = vals[i:i + 5000]
            cur.execute(
                "SELECT xpr.ecma_num(v), v::text FROM unnest(%(v)s::float8[]) WITH ORDINALITY t(v,o) ORDER BY o",
                {"v": chunk})
            out.extend(cur.fetchall())
    return out


def sample(rng, n):
    vals = []
    while len(vals) < n:
        b = rng.getrandbits(64)
        v = struct.unpack("<d", struct.pack("<Q", b))[0]
        if math.isfinite(v) and abs(v) < 1.79e296:
            vals.append(v)
    return vals


def main():
    rng = random.Random(7)
    N = 200000
    vals = sample(rng, N)
    rows = batch(vals)
    bad = []
    for v, (s, pgtext) in zip(vals, rows):
        p = expr._num_to_str(v)
        if p != s:
            bad.append((v, p, s, pgtext))
    print("=== F1b. xpr.ecma_num vs _num_to_str over %d uniformly-random finite doubles ===" % N)
    print("    (all |v| < 1.79e296, so the f8-guard defect cannot contribute)")
    print("    mismatches: %d  (%.4f%%, 1 in %d)" % (
        len(bad), 100.0 * len(bad) / N, (N // max(len(bad), 1))))
    print()
    print("    %-24s %-26s %-26s %s" % ("double (python repr)", "python _num_to_str",
                                        "xpr.ecma_num", "float8out text"))
    for v, p, s, t in bad[:25]:
        print("    %-24r %-26r %-26r %r" % (v, p, s, t))
    print()
    # characterise: is the python answer always SHORTER?
    shorter = sum(1 for v, p, s, t in bad if len(p.lstrip('-')) < len(s.lstrip('-')))
    print("    python answer has FEWER significant characters in %d of %d mismatches" % (shorter, len(bad)))
    # do both still round-trip to the same double?
    same = sum(1 for v, p, s, t in bad if float(p) == float(s) == v)
    print("    both spellings still parse back to the identical double: %d of %d" % (same, len(bad)))
    print("    -> this is a TEXT divergence, not a numeric one: string()/concat() emit")
    print("       different characters, and expr.py:12-13 makes byte-identical text the contract.")
    # magnitude buckets
    from collections import Counter
    c = Counter(int(math.floor(math.log10(abs(v)))) for v, p, s, t in bad if v != 0)
    print()
    print("    decimal-exponent histogram of the mismatches:")
    for k in sorted(c):
        print("      1e%-5d %s (%d)" % (k, "#" * min(c[k], 60), c[k]))


main()
