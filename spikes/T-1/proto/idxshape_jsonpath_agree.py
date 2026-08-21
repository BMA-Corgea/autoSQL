"""Bound the jsonpath-vs-expr agreement honestly: run adversarial records through BOTH."""
import os
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")
from core.dashboard import expr
import psycopg2
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
