"""T-1 measurement seat -- THROWAWAY loader.  Creates measure_instances_<N> tables in
autosql_spike with the EXACT DDL of gims-ledger migrations/pg/0001_instances.sql:13-18
and COPYs a generated corpus into each."""
from __future__ import annotations
import os
import sys, time, json
import psycopg2

# Scrubbed 2026-08-21 before first commit: the password is not in this repo, because the
# same role owns the live glp_strong database on that container. Set AUTOSQL_SPIKE_DSN,
# or let libpq read PGPASSWORD/~/.pgpass. See spikes/T-1/proto/README-db.md.
DSN = os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike"

DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       JSONB NOT NULL,
    PRIMARY KEY (collection, key)
);
"""

def main(n: int, csv_path: str, gin: bool):
    t = f"measure_instances_{n}"
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {t}")
    cur.execute(DDL.format(t=t))
    t0 = time.perf_counter()
    with open(csv_path) as fh:
        cur.copy_expert(f"COPY {t} (collection, key, data) FROM STDIN WITH (FORMAT csv)", fh)
    load_s = time.perf_counter() - t0
    if gin:  # mirrors migrations/pg/0002_instances_data_gin.sql:36-37
        g0 = time.perf_counter()
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_data_gin ON {t} USING GIN (data jsonb_path_ops)")
        gin_s = time.perf_counter() - g0
    else:
        gin_s = None
    cur.execute(f"VACUUM ANALYZE {t}")
    cur.execute(f"SELECT count(*), pg_size_pretty(pg_total_relation_size('{t}')), pg_total_relation_size('{t}') FROM {t}")
    cnt, pretty, raw = cur.fetchone()
    print(json.dumps({"table": t, "rows": cnt, "copy_seconds": round(load_s, 2),
                      "gin_seconds": (round(gin_s, 2) if gin_s is not None else None),
                      "total_size": pretty, "total_bytes": raw}))
    conn.close()

if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], gin=(len(sys.argv) > 3 and sys.argv[3] == "gin"))
