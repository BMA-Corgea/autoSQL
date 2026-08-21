"""Bound the jsonpath-vs-expr agreement honestly: run adversarial records through BOTH."""
import os
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")
from core.dashboard import expr
import psycopg2
con = psycopg2.connect(os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike")
con.autocommit = True; cur = con.cursor()

CASES = [
    ('$.tags == "a"',        '$."tags" == "a"',        {"tags": ["a", "b"]}),
    ('$.score > 90',         '$."score" ? (@ > 90)',   {"score": "95.0"}),
    ('$.score > 90',         '$."score" ? (@ > 90)',   {"score": 95.0}),
    ('$.score > 90',         '$."score" ? (@ > 90)',   {}),
    ('$.b == 1',             '$."b" == 1',             {"b": True}),
    ('$.n == "2"',           '$."n" == "2"',           {"n": 2}),
    ('$.n < "x"',            '$."n" < "x"',            {"n": 5}),
    ('$.payload.machine == "goms"', '$."payload"."machine" == "goms"', {"payload": {"machine": "goms"}}),
    ('$.status == "open"',   '$."status" == "open"',   {"status": None}),
    ('$.arr > 1',            '$."arr" ? (@ > 1)',      {"arr": [0, 5]}),
    ('$.score >= 90',        '$."score" ? (@ >= 90)',  {"score": 90}),
]
print(f"{'expr':<32}{'record':<28}{'expr()':<10}{'jsonpath':<10}{'agree'}")
bad = 0
for e, jp, rec in CASES:
    py = expr.truthy(expr.evaluate(expr.parse(e), rec, {}))
    op = "@@" if "?" not in jp else "@?"
    cur.execute(f"SELECT (%s::jsonb {op} ('strict ' || %s)::jsonpath) IS TRUE", (json.dumps(rec), jp))
    sq = cur.fetchone()[0]
    sq = bool(sq)
    ok = (py == sq)
    bad += (not ok)
    print(f"{e:<32}{json.dumps(rec)[:26]:<28}{str(py):<10}{str(sq):<10}{'OK' if ok else '*** DIVERGES'}")
print(f"\n{len(CASES)-bad}/{len(CASES)} agree; {bad} diverge")
