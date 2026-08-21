"""T-1 fuzz seat, battery D.

mode="raw": the record is raw JSON *text* cast ::jsonb in SQL, and Python does
json.loads(text) on the SAME text.  This is the shape of any row NOT written by
this Python process (ETL, migration, psql, another service, a restored dump).

It is the only mode that can exercise jsonb's `numeric` storage against Python's
IEEE-double parse, i.e. compile.py KNOWN_DIVERGENCES/jsonb_numeric_is_not_ieee_double,
which the conformance seat recorded as UNCONFIRMED because a record built from
Python floats has already collapsed before it reaches jsonb.

Reachability note recorded on the spot, not asserted: gims-ledger
api/storage_aws.py:743-754 writes with psycopg's Jsonb(record) from a Python dict,
so THAT writer cannot produce these rows; api/storage_aws.py:694 reads with
json.loads(cell), so it WILL mis-read them if anything else wrote them.  The same
file's own comment at :326-335 already documents this exact class of Postgres/Python
number disagreement as a production parity bug they had to fix once.
"""
import sys
sys.path.insert(0, '.')
from differ import run_case

print("=== D. raw-JSON rows: jsonb `numeric` vs Python `float` ===")
print()

cases = [
    # (expr, raw json text, note)
    ('$.a == $.b', '{"a": 1.0000000000000001, "b": 1.0000000000000002}',
     "18 sig digits: the SAME double in Python, DISTINCT numerics in jsonb"),
    ('$.a == 1', '{"a": 1.00000000000000001}',
     "19 sig digits -> Python double is exactly 1.0"),
    ('$.a != $.b', '{"a": 1.0000000000000001, "b": 1.0000000000000002}',
     "the != face of the same case"),
    ('contains($.l, $.a)', '{"l": [1.0000000000000002], "a": 1.0000000000000001}',
     "contains() array branch uses jsonb equality, _eq uses float equality"),
    ('$.a < $.b', '{"a": 1.0000000000000001, "b": 1.0000000000000002}',
     "ORDER goes through xpr.f8 so it should agree -- control"),
    ('if($.a, 1, 2)', '{"a": 1e-400}',
     "truthy() casts to NUMERIC: 1e-400 is nonzero in jsonb, 0.0 (falsy) in Python"),
    ('if($.a, 1, 2)', '{"a": 1e-4000}',
     "even further below float8"),
    ('not $.a', '{"a": 1e-400}', "the not() face"),
    ('$.a and true', '{"a": 1e-400}', "the and() face"),
    ('number($.a)', '{"a": 1e-400}',
     "number() on a jsonb numeric that underflows float8"),
    ('$.a + 0', '{"a": 1e-400}', "arithmetic on it"),
    ('string($.a)', '{"a": 1e-400}', "string() on it"),
    ('number($.a)', '{"a": 1e400}', "jsonb numeric ABOVE DBL_MAX"),
    ('$.a', '{"a": 1e400}', "bare read of a jsonb numeric above DBL_MAX"),
    ('$.a == 100', '{"a": 1e2}',
     "jsonb drops the exponent spelling (storage_aws.py:326-335) -- control"),
    ('length($.s)', '{"s": "\\ud83d\\ude00"}',
     "astral char via surrogate pair: Python len==1, PG length==1"),
    ('$.a == $.b', '{"a": 0.1, "b": 0.10}', "trailing-zero spelling -- control"),
    ('$.a == 0.3', '{"a": 0.30000000000000004}', "control: must be false both sides"),
]

div = 0
for src, raw, note in cases:
    o = run_case(src, mode="raw", raw=raw, note=note)
    star = "" if o["verdict"] == "AGREE" else "  <<<"
    print("   %-14s %-24s %s" % ("<" + o["verdict"] + ">", src, raw))
    print("                  %s%s" % (note, star))
    if o["verdict"] != "AGREE":
        div += 1
        print("                  python decoded record = %s" % o.get("py_record_decoded"))
        print("                  py=%s  sql=%s (%s)%s" % (
            o.get('python'), o.get('sql_value'), o.get('sql_typeof'),
            '  RAISED ' + str(o.get('sql_raised')) if o.get('sql_raised') else ''))

print()
print("%d of %d raw-JSON probes diverge" % (div, len(cases)))
