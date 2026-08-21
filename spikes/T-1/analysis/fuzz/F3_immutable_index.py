"""T-1 fuzz seat, battery F3.

xpr.ecma_num is declared IMMUTABLE (runtime.sql:80) but its digit source is
`abs(x)::text`, which is a function of the extra_float_digits GUC (runtime.sql:15-18
admits the dependency; compile.py KNOWN_DIVERGENCES/extra_float_digits_guc calls it
"a caveat").

IMMUTABLE is not a caveat.  It is a promise Postgres relies on to (a) constant-fold,
(b) build expression indexes, and (c) skip rechecking index conditions.  This probe
builds an expression index in a session with a different GUC and then asks the same
question two ways.
"""
import json
import sys

sys.path.insert(0, '.')
import differ
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr

VALUE = 1.0 / 3.0                       # 0.3333333333333333 -- GUC-sensitive
PY = expr._num_to_str(VALUE)

with differ.conn().cursor() as cur:
    cur.execute("DROP TABLE IF EXISTS fuzz_guc")
    cur.execute("CREATE TABLE fuzz_guc (id int primary key, data jsonb)")
    cur.executemany("INSERT INTO fuzz_guc VALUES (%s, %s::jsonb)",
                    [(i, json.dumps({"a": VALUE})) for i in range(1, 201)])

    print("=== F3. an IMMUTABLE function that reads a GUC, put into an index ===")
    print("    200 rows, every one {\"a\": %r}" % VALUE)
    print("    expr string($.a)  ->  %r   (expr.py:322-348)" % PY)
    print()

    cur.execute("SET extra_float_digits = -3")
    cur.execute("SELECT xpr.str(data -> 'a') FROM fuzz_guc LIMIT 1")
    print("    xpr.str under extra_float_digits = -3 : %r" % cur.fetchone()[0])
    print("    -- an index is now built in THAT session --")
    cur.execute("CREATE INDEX fuzz_guc_ix ON fuzz_guc (xpr.str(data -> 'a'))")

    cur.execute("SET extra_float_digits = 1")     # back to the PG16 default
    cur.execute("SELECT xpr.str(data -> 'a') FROM fuzz_guc LIMIT 1")
    live = cur.fetchone()[0]
    print("    xpr.str under extra_float_digits = 1  : %r   (this is the correct answer)" % live)
    print()

    cur.execute("ANALYZE fuzz_guc")
    for label, on in (("index scan forced", True), ("seq scan forced", False)):
        if on:
            cur.execute("SET enable_seqscan = off")
            cur.execute("RESET enable_indexscan"); cur.execute("RESET enable_bitmapscan")
        else:
            cur.execute("RESET enable_seqscan")
            cur.execute("SET enable_indexscan = off"); cur.execute("SET enable_bitmapscan = off")
        cur.execute("EXPLAIN (COSTS OFF) SELECT count(*) FROM fuzz_guc WHERE xpr.str(data->'a') = %s", (live,))
        plan = [r[0].strip() for r in cur.fetchall()]
        node = next((p for p in plan if "Scan" in p), plan[0])
        cur.execute("SELECT count(*) FROM fuzz_guc WHERE xpr.str(data->'a') = %s", (live,))
        n = cur.fetchone()[0]
        print("    WHERE string($.a) = %r  [%-18s]  -> %3d rows   (%s)" % (live, label, n, node))

    cur.execute("RESET enable_seqscan")
    cur.execute("RESET enable_indexscan"); cur.execute("RESET enable_bitmapscan")
    cur.execute("DROP TABLE fuzz_guc")

print()
print("    If the two row counts differ, the same predicate on the same rows returns")
print("    two different answers depending only on the plan the planner picked --")
print("    which is what an incorrect IMMUTABLE declaration buys.")
