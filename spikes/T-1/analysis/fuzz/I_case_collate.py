"""T-1 fuzz seat, battery I.

lower()/upper()  --  compile.py:341-349 emits Postgres lower()/upper() over
xpr.str; expr.py:537-538 uses Python str.lower()/str.upper().
compile.py KNOWN_DIVERGENCES/unicode_case_and_collation records this with
guarded:false, in_fixture:false.  This battery MEASURES it: an exhaustive sweep
of every assigned single code point in the BMP plus the supplementary planes'
cased blocks, comparing the two case mappings character by character.

Also: xpr.ord pins string comparison to COLLATE "C" (runtime.sql:173-176), which
compares UTF-8 BYTES; Python compares CODE POINTS.  UTF-8 preserves code point
order, so this should agree -- verified rather than assumed.
"""
import sys
import unicodedata

sys.path.insert(0, '.')
import differ

BATCH = 3000


def sweep(fn_name, py_fn):
    """Compare Postgres <fn_name>() with Python's for every assigned code point."""
    cps = [c for c in range(1, 0x110000)
           if not (0xD800 <= c <= 0xDFFF) and unicodedata.category(chr(c)) != "Cn"]
    mismatches = []
    with differ.conn().cursor() as cur:
        for i in range(0, len(cps), BATCH):
            chunk = cps[i:i + BATCH]
            chars = [chr(c) for c in chunk]
            cur.execute(
                "SELECT %s(s) FROM unnest(%%(s)s::text[]) WITH ORDINALITY t(s,o) ORDER BY o" % fn_name,
                {"s": chars})
            got = [r[0] for r in cur.fetchall()]
            for c, ch, g in zip(chunk, chars, got):
                p = py_fn(ch)
                if p != g:
                    mismatches.append((c, ch, p, g))
    return len(cps), mismatches


def summarize(title, total, ms):
    print("=== %s ===" % title)
    print("    assigned code points swept : %d" % total)
    print("    mismatches                 : %d   (%.3f%%)" % (len(ms), 100.0 * len(ms) / total))
    # bucket by what kind of disagreement it is
    grew = [m for m in ms if len(m[2]) != len(m[3])]
    print("    of which the two sides return DIFFERENT LENGTHS: %d" % len(grew))
    print("    first 30:")
    for c, ch, p, g in ms[:30]:
        print("      U+%04X %-28s python=%-14r postgres=%-14r" % (
            c, unicodedata.name(ch, "?")[:28], p, g))
    print()
    return ms


tot, up = sweep("upper", str.upper)
up = summarize("I1. upper()  Python str.upper vs Postgres upper() under C.UTF-8", tot, up)
tot, lo = sweep("lower", str.lower)
lo = summarize("I2. lower()  Python str.lower vs Postgres lower() under C.UTF-8", tot, lo)

print("=== I3. named witnesses, end to end through the compiler ===")
from differ import run_case
for s in ["straße", "İstanbul", "ǅungla", "ﬁle", "ΣΊΣΥΦΟΣ", "ΑΣ", "ς", "ﬀ", "ŉ", "ẞ"]:
    a = run_case("upper($.s)", {"s": s})
    b = run_case("lower($.s)", {"s": s})
    print("    %-12s upper: %-12s py=%-14s sql=%-14s | lower: %-12s py=%-14s sql=%s" % (
        ascii(s), "<" + a["verdict"] + ">", a.get("python"), a.get("sql_value"),
        "<" + b["verdict"] + ">", b.get("python"), b.get("sql_value")))
print()

print("=== I4. string ORDERING: COLLATE \"C\" (bytes) vs Python (code points) ===")
import random
rng = random.Random(3)
pool = [chr(rng.randrange(1, 0x110000)) for _ in range(4000)]
pool = [c for c in pool if not (0xD800 <= ord(c) <= 0xDFFF)]
bad = 0
with differ.conn().cursor() as cur:
    for i in range(0, len(pool) - 1, 2):
        a, b = pool[i], pool[i + 1]
        cur.execute("SELECT %(a)s COLLATE \"C\" < %(b)s", {"a": a, "b": b})
        if cur.fetchone()[0] != (a < b):
            bad += 1
            if bad < 6:
                print("      U+%04X vs U+%04X: python=%s postgres=%s" % (
                    ord(a), ord(b), a < b, not (a < b)))
print("    pairs compared: %d   ordering mismatches: %d" % (len(pool) // 2, bad))
