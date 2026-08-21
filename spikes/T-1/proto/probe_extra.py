"""T-1 measurement seat -- THROWAWAY follow-on probes that bench.py does not cover:

  (1) bytes actually returned by each path (payload, server-measured);
  (2) the cost of a RUN-TIME fallback: compile.py cannot detect the float8 overflow
      raise (KNOWN_DIVERGENCES/float8_overflow_raises, guarded:false), so Postgres aborts
      the query mid-scan and the whole widget must then be re-run on Path A.
"""
from __future__ import annotations
import json, statistics, sys, time
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")
import psycopg2
from core.dashboard import expr as EXPR
import compile as CC
import bench as B

conn = psycopg2.connect(B.DSN); conn.autocommit = True
cur = conn.cursor()
cur.execute("SET extra_float_digits = 1")
out = {}

# ---- (1) payload bytes returned by each path ------------------------------------------
pay = {}
for n in (1000, 10000, 20000, 25000, 100000, 1000000):
    t = f"measure_instances_{n}"
    cur.execute(f"SELECT count(*), sum(octet_length(data::text)) FROM {t} WHERE collection=%s",
                (B.COLLECTION,))
    rows_a, bytes_a = cur.fetchone()
    sql, params = B.build_b("B2", t)
    cur.execute(f"SELECT count(*), sum(octet_length(x::text)) FROM ({sql}) s(x)", params)
    rows_b, bytes_b = cur.fetchone()
    pay[n] = {"path_a_rows": rows_a, "path_a_payload_bytes": int(bytes_a),
              "path_b_rows": rows_b, "path_b_payload_bytes": int(bytes_b),
              "ratio": round(int(bytes_a) / int(bytes_b), 1)}
    print(n, pay[n], flush=True)
out["payload"] = pay

# ---- (2) run-time fallback: a raise that compile.py cannot see coming -------------------
POISON = "measure_instances_poison"
cur.execute(f"DROP TABLE IF EXISTS {POISON}")
cur.execute(f"CREATE TABLE {POISON} (LIKE measure_instances_100000 INCLUDING ALL)")
cur.execute(f"INSERT INTO {POISON} SELECT * FROM measure_instances_100000")
cur.execute(f"INSERT INTO {POISON} VALUES (%s, %s, %s::jsonb)",
            (B.COLLECTION, "S-POISON",
             json.dumps({"id": "S-POISON", "status": "open", "due_date": "2026-08-20",
                         "big": 1e200})))
cur.execute(f"ANALYZE {POISON}")

WHERE_POISON = "$.days_left != null and $.days_left < 7 and ($.big * $.big) != 0"
w_ast = EXPR.parse(WHERE_POISON)
d_ast = EXPR.parse(B.WIDGET["derive"][B.DERIVE_NAME])
w_in = B.subst(w_ast, B.DERIVE_NAME, d_ast)
params = {"coll": B.COLLECTION, "ctx": json.dumps(B.CTX),
          "fstatus": json.dumps(B.WIDGET["filters"]["status"])}
c = CC.compile_ast(w_in, column="data")
w_sql = c.sql
for k, v in c.params.items():
    params[f"w_{k}"] = v
    w_sql = w_sql.replace(f"%({k})s", f"%(w_{k})s")
c2 = CC.compile_ast(d_ast, column="data")
d_sql = c2.sql
for k, v in c2.params.items():
    params[f"s_{k}"] = v
    d_sql = d_sql.replace(f"%({k})s", f"%(s_{k})s")
sql = (f"SELECT data FROM {POISON} WHERE collection = %(coll)s "
       f"AND (data -> 'status') = %(fstatus)s::jsonb AND xpr.truthy({w_sql}) "
       f"ORDER BY {B.sort_sql(d_sql)} LIMIT 50")

out["poison"] = {"where": WHERE_POISON, "compiled_ok": True,
                 "uncompilable_raised": False}

# does the Python evaluator survive it?  (expr is total: expr.py:640)
rec = {"id": "S-POISON", "status": "open", "due_date": "2026-08-20", "big": 1e200}
out["poison"]["python_value"] = repr(EXPR.evaluate(EXPR.parse("$.big * $.big"), rec, B.CTX))

ts = []
for _ in range(5):
    t0 = time.perf_counter()
    try:
        cur.execute(sql, params); cur.fetchall()
        out["poison"]["sql_raised"] = False
    except psycopg2.Error as e:
        out["poison"]["sql_raised"] = True
        out["poison"]["sqlstate"] = e.pgcode
        out["poison"]["message"] = str(e).strip().splitlines()[0]
    ts.append((time.perf_counter() - t0) * 1000)
out["poison"]["time_to_raise_ms"] = round(statistics.median(ts), 2)

# the fallback that must follow: the whole widget, again, on Path A
a = B.reps(lambda: B.path_a(conn, POISON), 3)
out["poison"]["path_a_after_raise_ms"] = a["agg"]["total_ms"]["median"]
out["poison"]["total_fallback_ms"] = round(
    out["poison"]["time_to_raise_ms"] + a["agg"]["total_ms"]["median"], 2)
out["poison"]["path_a_alone_ms"] = a["agg"]["total_ms"]["median"]
out["poison"]["overhead_pct"] = round(
    out["poison"]["time_to_raise_ms"] / a["agg"]["total_ms"]["median"] * 100, 1)
print(json.dumps(out["poison"], indent=1), flush=True)

p = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/probes.json"
json.dump(out, open(p, "w"), indent=2, default=str)
print("WROTE", p)
