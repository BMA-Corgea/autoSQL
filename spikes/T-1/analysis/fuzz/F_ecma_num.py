"""T-1 fuzz seat, battery F.

xpr.ecma_num (runtime.sql:79-128)  vs  _num_to_str (expr.py:322-348).

Two separate attacks:
  F1  random-double differential fuzz of the FORMATTING itself
  F2  the GUC.  ecma_num's digit source is `abs(x)::text`, which is the shortest
      round-trip representation only while extra_float_digits >= 0.  The function
      is nevertheless declared IMMUTABLE.  IMMUTABLE is a promise to the planner
      and to CREATE INDEX; a function that reads a GUC and claims IMMUTABLE can
      put wrong values INTO an index and leave them there.
"""
import json
import math
import random
import struct
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr


def rand_double(rng):
    kinds = ["uniform", "bits", "small_int", "exp", "tiny", "huge", "special"]
    k = rng.choice(kinds)
    if k == "uniform":
        return rng.uniform(-1e6, 1e6)
    if k == "bits":
        while True:
            b = rng.getrandbits(64)
            v = struct.unpack("<d", struct.pack("<Q", b))[0]
            if math.isfinite(v):
                return v
    if k == "small_int":
        return float(rng.randint(-10**6, 10**6))
    if k == "exp":
        return rng.choice([-1, 1]) * (10.0 ** rng.randint(-30, 30)) * rng.random()
    if k == "tiny":
        return rng.choice([-1, 1]) * (10.0 ** rng.randint(-320, -1)) * rng.random()
    if k == "huge":
        # stay under the 1.7976931348623157e296 guard so F1 measures FORMATTING,
        # not the separate f8-guard defect
        return rng.choice([-1, 1]) * (10.0 ** rng.randint(1, 290)) * rng.random()
    return rng.choice([0.0, -0.0, 1e21, 1e-7, 1e-6, 5e-324, 1.7976931348623157e308,
                       0.1, 1 / 3, 2**53, 2**53 + 2.0, 1e16, 1e17, 1e20, 1e22,
                       123456789012345678901.0, 1e-5, 1e-4, 9.999999999999999e20])


def ecma_sql(vals):
    """One round trip: ask Postgres for xpr.ecma_num of each value."""
    out = []
    with differ.conn().cursor() as cur:
        for v in vals:
            cur.execute("SELECT xpr.ecma_num(%(v)s::float8)", {"v": v})
            out.append(cur.fetchone()[0])
    return out


def main():
    rng = random.Random(20260819)
    N = 4000
    vals = [rand_double(rng) for _ in range(N)]
    # never feed the f8 guard bug into this experiment
    vals = [v for v in vals if abs(v) < 1.79e296]
    sqls = ecma_sql(vals)
    bad = []
    for v, s in zip(vals, sqls):
        p = expr._num_to_str(v)
        if p != s:
            bad.append((v, p, s))
    print("=== F1. random-double differential: xpr.ecma_num vs _num_to_str ===")
    print("    %d finite doubles, extra_float_digits = 1 (the PG16 default)" % len(vals))
    print("    mismatches: %d" % len(bad))
    for v, p, s in bad[:20]:
        print("      %-26r python=%-24r sql=%-24r" % (v, p, s))
    print()

    print("=== F2. the GUC.  xpr.ecma_num is declared IMMUTABLE (runtime.sql:80) ===")
    probe = [0.1, 1 / 3, 1e-7, 2 / 3, 1.2345678901234567, 1e21, 5e-324, 123.456]
    print("    %-24s %-26s %s" % ("value", "python _num_to_str", "xpr.ecma_num @ efd="))
    hdr = "    %-24s %-26s" % ("", "")
    settings = [1, 0, -1, -5, 3]
    rows = {}
    with differ.conn().cursor() as cur:
        for efd in settings:
            cur.execute("SET extra_float_digits = %s", (efd,))
            r = []
            for v in probe:
                cur.execute("SELECT xpr.ecma_num(%(v)s::float8)", {"v": v})
                r.append(cur.fetchone()[0])
            rows[efd] = r
        cur.execute("SET extra_float_digits = 1")
    print(hdr + "  " + "  ".join("%-24s" % ("efd=%d" % e) for e in settings))
    n_guc = 0
    for i, v in enumerate(probe):
        py = expr._num_to_str(v)
        cells = [rows[e][i] for e in settings]
        flag = "" if all(c == py for c in cells) else "   <<< GUC-DEPENDENT"
        print("    %-24r %-26r %s%s" % (v, py, "  ".join("%-24r" % c for c in cells), flag))
        if not all(c == py for c in cells):
            n_guc += 1
    print("    %d of %d probe values change answer with the GUC" % (n_guc, len(probe)))
    print()

    print("=== F3. can a wrong value be FROZEN into an index? ===")
    with differ.conn().cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fuzz_guc")
        cur.execute("CREATE TABLE fuzz_guc (id int primary key, data jsonb)")
        cur.execute("INSERT INTO fuzz_guc VALUES (1, %s::jsonb)", (json.dumps({"a": 0.1}),))
        cur.execute("SET extra_float_digits = -5")            # a session that mis-set it
        cur.execute("CREATE INDEX fuzz_guc_ix ON fuzz_guc (xpr.str(data -> 'a'))")
        cur.execute("SET extra_float_digits = 1")             # back to the correct value
        cur.execute("SET enable_seqscan = off")
        cur.execute("EXPLAIN (COSTS OFF) SELECT id FROM fuzz_guc WHERE xpr.str(data->'a') = '0.1'")
        plan = " ".join(r[0] for r in cur.fetchall())
        cur.execute("SELECT id FROM fuzz_guc WHERE xpr.str(data->'a') = '0.1'")
        via_index = cur.fetchall()
        cur.execute("SET enable_seqscan = on")
        cur.execute("SET enable_indexscan = off"); cur.execute("SET enable_bitmapscan = off")
        cur.execute("SELECT id FROM fuzz_guc WHERE xpr.str(data->'a') = '0.1'")
        via_seq = cur.fetchall()
        cur.execute("RESET enable_indexscan"); cur.execute("RESET enable_bitmapscan")
        cur.execute("SELECT xpr.str(data->'a') FROM fuzz_guc")
        live = cur.fetchone()[0]
    print("    row is {\"a\": 0.1};  python string($.a) == %r" % expr._num_to_str(0.1))
    print("    live (heap) value now                 : %r" % live)
    print("    index built while extra_float_digits=-5")
    print("    plan for the indexed query            : %s" % plan)
    print("    rows returned VIA THE INDEX           : %r" % (via_index,))
    print("    rows returned via a seq scan          : %r" % (via_seq,))
    if via_index != via_seq:
        print("    <<< SAME QUERY, TWO ANSWERS, depending only on the plan.")
    else:
        print("    (no split-brain observed in this configuration -- see notes)")
    with differ.conn().cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fuzz_guc")


main()
