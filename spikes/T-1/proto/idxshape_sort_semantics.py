"""Does an index-backed SQL sort reproduce sources.py's _sort_key order?"""
import os
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from api.dashboard.sources import _sort_key
import psycopg2
con = psycopg2.connect(os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike")
con.autocommit=True; cur=con.cursor()
VALUES = [None, True, False, 5, 2.5, "apple", "Zebra", [1,2], {"a":1}]
py = sorted(VALUES, key=_sort_key)
cur.execute("SELECT v FROM (SELECT jsonb_array_elements(%s::jsonb) v) t ORDER BY v ASC", (json.dumps(VALUES),))
sq = [r[0] for r in cur.fetchall()]
print("sources.py _sort_key ascending :", json.dumps(py))
print("jsonb btree ascending          :", json.dumps(sq))
print("SAME ORDER?", py == sq)
