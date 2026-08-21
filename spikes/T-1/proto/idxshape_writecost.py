"""Write amplification, isolated from client round-trip cost: one COPY of 20,000 rows."""
import os
import io, sys, time
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
import psycopg2
# Scrubbed 2026-08-21 before first commit: the password is not in this repo, because the
# same role owns the live glp_strong database on that container. Set AUTOSQL_SPIKE_DSN,
# or let libpq read PGPASSWORD/~/.pgpass. See spikes/T-1/proto/README-db.md.
DSN = os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike"
con = psycopg2.connect(DSN); con.autocommit = True; cur = con.cursor()
CONFIGS = [
    ("none (PK only)", []),
    ("GIN (data jsonb_path_ops)", ["CREATE INDEX w_gin_path ON idxprobe USING GIN (data jsonb_path_ops)"]),
    ("GIN jsonb_path_ops, fastupdate=off", ["CREATE INDEX w_gin_path2 ON idxprobe USING GIN (data jsonb_path_ops) WITH (fastupdate=off)"]),
    ("GIN (data jsonb_ops)", ["CREATE INDEX w_gin_def ON idxprobe USING GIN (data jsonb_ops)"]),
    ("1 btree expression index", ["CREATE INDEX w_b1 ON idxprobe (((data->>'score')::float8))"]),
    ("4 btree expression indexes",
     ["CREATE INDEX w_b1 ON idxprobe (((data->>'score')::float8))",
      "CREATE INDEX w_b2 ON idxprobe ((data->>'status'))",
      "CREATE INDEX w_b3 ON idxprobe ((data->>'actor'))",
      "CREATE INDEX w_b4 ON idxprobe ((data->>'due_date'))"]),
    ("12 btree expression indexes",
     ["CREATE INDEX w_c%d ON idxprobe ((data->>'%s'))" % (i, k) for i, k in enumerate(
       ["score","status","actor","due_date","received_date","client","comments",
        "submission_id","priority","Sample Weight (g)","Analyte Type","kind"])]),
]
lines = [l for l in open(sys.argv[1])][:20000]
def drop_extra():
    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='idxprobe' AND indexname<>'idxprobe_pkey'")
    for (n,) in cur.fetchall(): cur.execute('DROP INDEX "%s"' % n)
print(f"{'config':<38}{'idx_MB':>9}{'copy20k_ms':>12}{'us/row':>9}{'vs_base':>9}")
base = None
for name, ddl in CONFIGS:
    drop_extra(); cur.execute("DELETE FROM idxprobe WHERE collection='WRITETEST'"); cur.execute("VACUUM ANALYZE idxprobe")
    for s in ddl: cur.execute(s)
    cur.execute("SELECT coalesce(sum(pg_relation_size(indexrelid)),0) FROM pg_stat_user_indexes WHERE relname='idxprobe' AND indexrelname<>'idxprobe_pkey'")
    isize = cur.fetchone()[0]
    buf = io.StringIO("".join("WRITETEST\tw-%07d\t%s\n" % (i, l.split("\t")[2].rstrip("\n")) for i, l in enumerate(lines)))
    t0 = time.perf_counter(); cur.copy_expert("COPY idxprobe (collection,key,data) FROM STDIN", buf); ms = (time.perf_counter()-t0)*1000
    if base is None: base = ms
    print(f"{name:<38}{isize/1048576:>9.1f}{ms:>12.0f}{ms*1000/len(lines):>9.1f}{ms/base:>8.2f}x")
drop_extra(); cur.execute("DELETE FROM idxprobe WHERE collection='WRITETEST'"); cur.execute("VACUUM ANALYZE idxprobe")
cur.execute("SELECT count(*) FROM idxprobe"); print("restored row count:", cur.fetchone()[0])
