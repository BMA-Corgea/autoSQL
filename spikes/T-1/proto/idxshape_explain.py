"""T-1 index-shape seat: run EXPLAIN (ANALYZE, BUFFERS) for each compiled predicate
under each index configuration.  Verbatim plan text is captured; nothing is summarised
here -- summarising happens in the write-up, from this output.
"""
import os
import json
import sys
import time

sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
import psycopg2  # noqa: E402

# Scrubbed 2026-08-21 before first commit: the password is not in this repo, because the
# same role owns the live glp_strong database on that container. Set AUTOSQL_SPIKE_DSN,
# or let libpq read PGPASSWORD/~/.pgpass. See spikes/T-1/proto/README-db.md.
DSN = os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike"
PREDS = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
CTX = {"now": "2026-08-19T12:00:00Z"}

# collection each predicate targets (a dashboard widget always scopes to one noun type)
COLL = {"W1": "Submission", "W2": "Submission", "W3": "Submission", "W4": "Submission",
        "W5": "Submission", "W6": "LedgerRecord", "W7": "Submission",
        "W8": "LedgerRecord", "W9": "LedgerRecord", "D1": "Submission", "S1": "Submission"}


def explain(cur, sql, params, analyze=True, seqscan=True):
    cur.execute("SET enable_seqscan = %s" % ("on" if seqscan else "off"))
    opts = "ANALYZE, BUFFERS, COSTS" if analyze else "COSTS OFF"
    cur.execute("EXPLAIN (%s) %s" % (opts, sql), params)
    return "\n".join(r[0] for r in cur.fetchall())


def timed(cur, sql, params, n=3):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        ts.append((time.perf_counter() - t0) * 1000.0)
    return len(rows), sorted(ts)[len(ts) // 2]


CONFIGS = [
    ("A_pk_only", []),
    ("B_gin_jsonb_path_ops",
     ["CREATE INDEX idxprobe_data_gin_path ON idxprobe USING GIN (data jsonb_path_ops)"]),
    ("C_gin_jsonb_ops",
     ["CREATE INDEX idxprobe_data_gin_default ON idxprobe USING GIN (data jsonb_ops)"]),
    ("D_btree_expression_per_key",
     ["CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8))",
      "CREATE INDEX idxprobe_status_txt ON idxprobe ((data->>'status'))",
      "CREATE INDEX idxprobe_actor_txt ON idxprobe ((data->>'actor'))",
      "CREATE INDEX idxprobe_due_txt ON idxprobe ((data->>'due_date'))"]),
]


def drop_all(cur):
    cur.execute("""SELECT indexname FROM pg_indexes
                   WHERE tablename='idxprobe' AND indexname <> 'idxprobe_pkey'""")
    for (n,) in cur.fetchall():
        cur.execute('DROP INDEX "%s"' % n)


results = {}
con = psycopg2.connect(DSN)
con.autocommit = True
cur = con.cursor()
cur.execute("SET extra_float_digits = 1")

for cname, ddl in CONFIGS:
    drop_all(cur)
    build_ms = {}
    for stmt in ddl:
        t0 = time.perf_counter()
        cur.execute(stmt)
        build_ms[stmt.split()[2]] = round((time.perf_counter() - t0) * 1000.0, 1)
    cur.execute("VACUUM ANALYZE idxprobe")
    cur.execute("""SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)),
                          pg_relation_size(indexrelid)
                   FROM pg_stat_user_indexes WHERE relname='idxprobe' ORDER BY 1""")
    sizes = [dict(name=r[0], pretty=r[1], bytes=r[2]) for r in cur.fetchall()]
    results[cname] = {"ddl": ddl, "build_ms": build_ms, "index_sizes": sizes, "queries": {}}

    for pid, p in PREDS.items():
        if not p["compiled"]:
            continue
        params = dict(p["params"])
        params["ctx"] = json.dumps(CTX)
        params["coll"] = COLL[pid]
        if pid in ("D1", "S1"):
            continue
        sql = ("SELECT data FROM idxprobe WHERE collection = %(coll)s AND xpr.truthy("
               + p["sql"] + ")")
        try:
            plan_on = explain(cur, sql, params, analyze=True, seqscan=True)
            plan_off = explain(cur, sql, params, analyze=False, seqscan=False)
            cur.execute("SET enable_seqscan = on")
            nrows, ms = timed(cur, sql, params)
            results[cname]["queries"][pid] = {
                "sql": sql, "rows": nrows, "median_ms": round(ms, 1),
                "plan_analyze": plan_on, "plan_noseqscan": plan_off}
        except Exception as e:  # noqa: BLE001
            con.rollback()
            results[cname]["queries"][pid] = {"sql": sql, "error": repr(e)}
    print(cname, "done", file=sys.stderr)

json.dump(results, open(OUT, "w"), indent=1)
print("wrote", OUT, file=sys.stderr)
