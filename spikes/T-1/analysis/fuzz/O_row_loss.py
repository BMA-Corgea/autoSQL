"""T-1 fuzz seat, battery O -- what the divergences DO when the compiled
expression is used as a WHERE predicate rather than as a projected value.

This is the shape the pushdown actually takes (recon/storage.md, gims-ledger
core/storage/sql.py list_records_where): the compiled jsonb expression becomes a
filter.  A value divergence there is a row that silently disappears from, or
appears in, the answer -- which no amount of eyeballing a number will reveal.
"""
import json
import sys

sys.path.insert(0, '.')
import differ
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
import compile as xcompile
from core.dashboard import expr

ROWS = [
    (1, {"amount": 5.0, "name": "alpha"}),
    (2, {"amount": 250.0, "name": "beta"}),
    (3, {"amount": 1e300, "name": "gamma"}),          # perfectly finite double
    (4, {"amount": 1e-7, "name": "delta"}),
    (5, {"amount": 900.0, "name": "epsilon"}),
    (6, {"amount": "١٢٣", "name": "zeta"}),           # Arabic-Indic "123"
    (7, {"amount": "１２３４", "name": "eta"}),         # fullwidth "1234"
    (8, {"amount": " 42 ", "name": "theta"}),         # NBSP-padded "42"
]

PREDICATES = [
    "$.amount > 100",
    "number($.amount) > 100",
    "$.amount >= 5",
    "not ($.amount > 100)",
]

conn = differ.conn()
with conn.cursor() as cur:
    cur.execute("DROP TABLE IF EXISTS fuzz_rows")
    cur.execute("CREATE TABLE fuzz_rows (id int primary key, data jsonb)")
    for i, r in ROWS:
        cur.execute("INSERT INTO fuzz_rows VALUES (%s, %s::jsonb)", (i, json.dumps(r)))

print("=== O. compiled predicate used as a WHERE filter ===")
print("    8 rows; row 3 holds amount=1e300, rows 6-8 hold non-ASCII numeric strings.")
print()
for src in PREDICATES:
    ast = expr.parse(src)
    # in-memory answer: the fallback path, expr.truthy as the keep/drop rule (expr.py:296-299)
    keep_py = sorted(i for i, r in ROWS if expr.truthy(expr.evaluate(ast, r, {})))
    c = xcompile.compile_ast(ast)
    params = dict(c.params)
    params["ctx"] = json.dumps({})
    q = ("SELECT id FROM fuzz_rows WHERE xpr.truthy(" + c.sql + ") ORDER BY id")
    try:
        with conn.cursor() as cur:
            cur.execute(q, params)
            keep_sql = sorted(r[0] for r in cur.fetchall())
        err = None
    except Exception as e:
        keep_sql, err = None, str(e).splitlines()[0]

    print("    %-26s in-memory keeps %s" % (src, keep_py))
    if err:
        print("    %-26s SQL            RAISED %s" % ("", err))
    else:
        print("    %-26s SQL keeps       %s" % ("", keep_sql))
        lost = [i for i in keep_py if i not in keep_sql]
        gained = [i for i in keep_sql if i not in keep_py]
        if lost or gained:
            print("    %-26s >>> rows SILENTLY DROPPED: %s   rows SILENTLY ADDED: %s"
                  % ("", lost or "none", gained or "none"))
        else:
            print("    %-26s     identical" % "")
    print()

with conn.cursor() as cur:
    cur.execute("DROP TABLE fuzz_rows")
