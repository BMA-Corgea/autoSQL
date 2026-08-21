"""T-1 fuzz seat, battery L -- the leftovers.

Large array indices, NUL bytes, very large strings, the text face of a numeric
divergence that the 1e-9 epsilon hides, and the ctx clock.
"""
import json
import sys

sys.path.insert(0, '.')
import differ
from differ import run_case

print("=== L1. the epsilon HIDES a text divergence ===")
for lst in ([0.1] * 10, [0.1] * 3, [1e9, 0.0001, -1e9]):
    a = run_case("sum($.l)", {"l": lst})
    b = run_case("string(sum($.l))", {"l": lst})
    c = run_case("concat(\"total=\", sum($.l))", {"l": lst})
    print("    list %-24s sum %-10s py=%-22s sql=%s" % (
        repr(lst)[:24], "<" + a["verdict"] + ">", a.get("python"), a.get("sql_value")))
    print("    %-29s string %-7s py=%-22s sql=%s" % (
        "", "<" + b["verdict"] + ">", b.get("python"), b.get("sql_value")))
    print("    %-29s concat %-7s py=%-22s sql=%s" % (
        "", "<" + c["verdict"] + ">", c.get("python"), c.get("sql_value")))
print("    -> a numeric AGREE inside float_epsilon can still be a VISIBLE text divergence,")
print("       because string()/concat() are exact and the epsilon does not apply to them.")
print()

print("=== L2. array indices that do not fit int4 ===")
for idx in [3, 2147483647, 2147483648, 3000000000, -3000000000]:
    src = "$.a[%d]" % idx
    o = run_case(src, {"a": [1, 2, 3]})
    print("    %-24s %-14s py=%-8s sql=%-8s%s" % (
        src, "<" + o["verdict"] + ">", o.get("python"), o.get("sql_value"),
        "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
print()

print("=== L3. a NUL character inside a string value ===")
rec = {"s": "a" + chr(0) + "b"}
print("    python len('a\\x00b') = %d ; expr length($.s) = ?" % len(rec['s']))
o = run_case("length($.s)", rec)
print("    %-14s py=%-8s sql=%-8s%s" % ("<" + o["verdict"] + ">", o.get("python"),
                                        o.get("sql_value"),
                                        "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))
print("    -> a record Python can hold cannot be STORED as jsonb at all; the pushdown")
print("       path is unreachable for it, which is a fallback trigger, not a wrong answer.")
print()

print("=== L4. generated-SQL size vs expression size ===")
for depth in (1, 5, 10, 20, 40):
    src = "1"
    for _ in range(depth):
        src = "round(%s + $.a, 2)" % src
    try:
        import compile as xc
        sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
        from core.dashboard import expr as _e
        c = xc.compile_ast(_e.parse(src))
        print("    nesting %-3d  source %5d chars -> SQL %8d chars  (x%.0f)" % (
            depth, len(src), len(c.sql), len(c.sql) / len(src)))
    except Exception as e:
        print("    nesting %-3d  source %5d chars -> %s" % (depth, len(src), repr(e)[:90]))
print("    MAX_SOURCE_LEN is 2000 (expr.py:39); MAX_SQL_CHARS is 200000 (compile.py:51)")
print()

print("=== L5. the clock: xpr.now_ms is STABLE, everything else IMMUTABLE ===")
with differ.conn().cursor() as cur:
    cur.execute("SELECT provolatile FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='xpr' ORDER BY proname")
    vol = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT proname, provolatile FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='xpr' ORDER BY proname")
    for name, v in cur.fetchall():
        tag = {"i": "IMMUTABLE", "s": "STABLE", "v": "VOLATILE"}[v]
        note = ""
        if name in ("ecma_num", "str", "f8", "num") and tag == "IMMUTABLE":
            note = "   <-- reads/depends on extra_float_digits (see battery F)"
        print("    %-12s %-10s%s" % (name, tag, note))
