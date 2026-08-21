"""Does an index-backed SQL sort reproduce sources.py's _sort_key order?"""
import os
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from api.dashboard.sources import _sort_key
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
con.autocommit=True; cur=con.cursor()
VALUES = [None, True, False, 5, 2.5, "apple", "Zebra", [1,2], {"a":1}]
py = sorted(VALUES, key=_sort_key)
cur.execute("SELECT v FROM (SELECT jsonb_array_elements(%s::jsonb) v) t ORDER BY v ASC", (json.dumps(VALUES),))
sq = [r[0] for r in cur.fetchall()]
print("sources.py _sort_key ascending :", json.dumps(py))
print("jsonb btree ascending          :", json.dumps(sq))
print("SAME ORDER?", py == sq)
