"""T-1 — 130-case strict-jsonpath agreement run.

PROVENANCE, READ THIS FIRST. This file was NOT written by the investigation. It was written on
2026-08-21 by the .recheck reconstruction pass to close `f3` §3.8 open item 9 — "the 130-case
jsonpath run has no committed artifact ... copy the scratchpad script into proto/ when the tree is
writable again; it is re-derivable today from idxshape_fixture_subset.py +
idxshape_jsonpath_agree.py". Evan waived FRAMING §3's no-edit rule in writing on 2026-08-21.

It REPRODUCES f3 §3.5(d)(ii)'s published table exactly: 130 cases -> 114 OTHER, 10
cmp(path,literal) (9 agree / 1 diverges), 6 bare path (2 agree / 4 diverge); 16 expressible,
11 agree, 5 diverge. Case 33 (`$.x == null` on `{}`) reproduces as the silent divergence
LOAD-BEARING CORRECTION 2 names.

It is NOT the original scratchpad script, which was never retained. Blocks below are marked
[FROM INSTRUMENT 1] / [FROM INSTRUMENT 2] where lifted unchanged from the two committed files,
and [NOT IN EITHER INSTRUMENT] where this pass had to supply the code — that marking is itself a
finding: the AST->jsonpath translator exists in neither named instrument.

Read-only: no DDL, no table referenced, every SELECT is a scalar expression.
"""
import os
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr
import psycopg2

fx = json.load(open("/home/corgea/Desktop/Coding Projects/GIMS-Project/tests/fixtures/expr_vectors.json"))

# ---------------- [FROM INSTRUMENT 1] verbatim -------------------------------------------
LIT = {"num", "str", "bool", "null"}
def is_path(n): return n[0] == "field" and all(s[0] == "key" for s in n[1])
def classify(a):
    if a[0] == "cmp" and is_path(a[2]) and a[3][0] in LIT: return "cmp(path, literal)"
    if a[0] == "cmp" and a[2][0] in LIT and is_path(a[3]): return "cmp(literal, path)"
    if is_path(a): return "bare path"
    if a[0] in LIT: return "bare literal"
    return "OTHER (no jsonpath equivalent)"

# ---------------- [NOT IN EITHER INSTRUMENT] I had to write all of this ------------------
def jp_path(node):                       # ('field',[('key','a'),('key','b')]) -> $."a"."b"
    return "$" + "".join('."%s"' % s[1].replace('"', '\\"') for s in node[1])
def jp_lit(node):
    t = node[0]
    if t == "null": return "null"
    if t == "bool": return "true" if node[1] else "false"
    if t == "str":  return json.dumps(node[1])
    v = node[1]
    return str(int(v)) if float(v).is_integer() else repr(v)
def to_jsonpath(a):
    if is_path(a): return jp_path(a)
    if a[0] == "cmp" and is_path(a[2]) and a[3][0] in LIT:
        return "%s %s %s" % (jp_path(a[2]), a[1], jp_lit(a[3]))
    return None
# ----------------------------------------------------------------------------------------

def _spike_dsn():
    """Fails closed on purpose. The only default that ever existed pointed at port 55433 -
    the live glp-strong-db container, which holds real data owned by the same role.
    Point AUTOSQL_SPIKE_DSN at a THROWAWAY Postgres. See proto/REGENERATE-CORPUS.md."""
    import os as _os
    dsn = _os.environ.get("AUTOSQL_SPIKE_DSN")
    if not dsn:
        raise SystemExit(
            "AUTOSQL_SPIKE_DSN is not set, and there is no default.\n"
            "  Point it at a throwaway Postgres, never at port 55433 (the live container).\n"
            "  See spikes/T-1/proto/REGENERATE-CORPUS.md."
        )
    if "port=55433" in dsn:
        raise SystemExit(
            "Refusing to run against port 55433 - that is the live glp-strong-db container.\n"
            "  Use a throwaway one. See spikes/T-1/proto/REGENERATE-CORPUS.md."
        )
    return dsn


con = psycopg2.connect(_spike_dsn())
con.set_session(readonly=True, autocommit=True)
cur = con.cursor()

rows, counts = [], {"OTHER (no jsonpath equivalent)": [0,0,0], "cmp(path, literal)": [0,0,0], "bare path": [0,0,0]}
for i, case in enumerate(fx["cases"]):
    a = expr.parse(case["expr"])
    cls = classify(a)
    counts.setdefault(cls, [0,0,0])
    counts[cls][0] += 1
    jp = to_jsonpath(a)
    if jp is None or cls == "OTHER (no jsonpath equivalent)":
        continue
    rec = case.get("record", {})
    ctx = case.get("context", {})
    py = expr.truthy(expr.evaluate(a, rec, ctx))
    # [FROM INSTRUMENT 2] the comparison shape, verbatim
    cur.execute("SELECT (%s::jsonb @@ ('strict ' || %s)::jsonpath),"
                "       (%s::jsonb @@ ('strict ' || %s)::jsonpath) IS TRUE,"
                "       (%s::jsonb @@ ('lax '    || %s)::jsonpath) IS TRUE",
                (json.dumps(rec), jp, json.dumps(rec), jp, json.dumps(rec), jp))
    raw, strict_true, lax_true = cur.fetchone()
    agree = (py == strict_true)
    counts[cls][1] += agree; counts[cls][2] += (not agree)
    rows.append((i, case["name"], case["expr"], jp, py, raw, strict_true, lax_true,
                 "agrees" if agree else "DIVERGES"))

print(f"{'#':>4} {'name':<32}{'expr':<20}{'jsonpath':<26}{'expr':<7}{'raw':<7}{'sIS':<7}{'lax':<7}verdict")
for r in rows:
    print(f"{r[0]:>4} {r[1]:<32}{r[2]:<20}{r[3]:<26}{str(r[4]):<7}{str(r[5]):<7}{str(r[6]):<7}{str(r[7]):<7}{r[8]}")
print()
tot = ex = ag = dv = 0
for k, (n, a_, d_) in counts.items():
    tot += n; ex += (a_ + d_); ag += a_; dv += d_
    print(f"{k:<34} cases={n:>4}  expressible={a_+d_:>3}  agrees={a_:>3}  diverges={d_:>3}")
print(f"{'TOTAL':<34} cases={tot:>4}  expressible={ex:>3}  agrees={ag:>3}  diverges={dv:>3}")
