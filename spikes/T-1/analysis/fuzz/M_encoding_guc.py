"""T-1 fuzz seat, battery M.

M1  Does the RESULT ENCODING itself depend on extra_float_digits?  Every compiled
    numeric result is wrapped in to_jsonb(float8) (compile.py:244, 281-293, 359,
    382-398, 404-424).  If to_jsonb(float8) reads the GUC, then the value the
    caller receives -- not just string()'s text -- is GUC-dependent.

M2  xpr.truthy casts the jsonb number's text to `numeric` (runtime.sql:67).
    numeric has a wider range than float8 but is not unbounded.

M3  What jsonb itself refuses to store.
"""
import sys

sys.path.insert(0, '.')
import differ

conn = differ.conn()

print("=== M1. to_jsonb(float8) vs the GUC ===")
probe = [1 / 3, 0.1, 1.2345678901234567, 5e-324, 1e21]
with conn.cursor() as cur:
    for efd in (1, 0, -3):
        cur.execute("SET extra_float_digits = %s", (efd,))
        row = []
        for v in probe:
            cur.execute("SELECT to_jsonb(%(v)s::float8)::text", {"v": v})
            row.append(cur.fetchone()[0])
        print("    efd=%-3d %s" % (efd, "  ".join("%-22s" % r for r in row)))
    cur.execute("SET extra_float_digits = 1")
print("    (if these rows differ, the compiled expression's RETURNED VALUE is GUC-dependent,")
print("     not merely its string() rendering)")
print()

print("=== M2/M3. what jsonb refuses, and where xpr.truthy stops ===")
probes = [
    ("select jsonb_typeof('1e400'::jsonb)", "jsonb accepts 1e400?"),
    ("select xpr.truthy('1e400'::jsonb)", "truthy on 1e400"),
    ("select xpr.truthy('1e-400'::jsonb)", "truthy on 1e-400 (Python: 0.0 -> FALSE)"),
    ("select jsonb_typeof('1e100000'::jsonb)", "jsonb accepts 1e100000?"),
    ("select xpr.truthy('1e100000'::jsonb)", "truthy on 1e100000"),
    ("select jsonb_typeof('1e1000000'::jsonb)", "beyond numeric's exponent range?"),
    ("select xpr.f8('1e400'::jsonb)", "f8 on 1e400 -- guarded to NULL"),
    ("select xpr.num('1e-400'::jsonb)", "num on 1e-400 -- UNGUARDED underflow"),
    ("select xpr.length('\"ab\"'::jsonb)", "control"),
    ("select ('{\"s\":\"a\\u0000b\"}')::jsonb", "NUL inside a jsonb string"),
    ("select length(('{\"s\":\"a\\u0041b\"}')::jsonb ->> 's')", "ordinary escape, control"),
]
for sql, note in probes:
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            r = cur.fetchone()[0]
        out = repr(r)[:70]
    except Exception as e:
        out = "RAISED " + str(e).splitlines()[0][:70]
    print("    %-52s %s" % (note, out))
