"""T-44 corpus setup: two runtimes side by side, and the text-encoded corpus. Then verify.

Writes only NEW objects into autosql_spike. T-4's tables and its `xpr` schema (the frozen
spike runtime, 21 functions) are read, never altered.

  schema xpr_ship   runtime/runtime.sql        (the shipping runtime, 23 functions)
  schema xpr_par    spikes/T-44/runtime-par.sql (lever a)
  t44_text_N        measure_instances_N with the widget's two fields re-encoded as JSON
                    strings ("17"), which is how the owner's real number fields are stored
                    (T-5). FRAMING section 4.2 S4 (ii). Same rows, same order, same indexes.

A runtime is moved into its schema by rewriting every `xpr.<fn>(` call and the CREATE
SCHEMA line, and nothing else, so the refusal MESSAGE texts ("xpr.num refusal: ...") are
untouched. The rewrite is then verified against what Postgres actually installed: no function
body in the new schema may still call into `xpr.`.

Usage: AUTOSQL_SPIKE_DSN=<autosql_spike dsn> setup_t44.py  -> spikes/T-44/out/setup.json
"""
import hashlib
import json
import os
import re
import sys

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CALL = re.compile(r"\bxpr\.(\w+)\(")
SIZES = (1000, 20000, 100000)
RUNTIMES = {"xpr_ship": os.path.join(ROOT, "runtime", "runtime.sql"),
            "xpr_par": os.path.join(HERE, "runtime-par.sql")}
# the invented widget's predicate in native operators -- B4's own expression -- used ONLY to
# measure selectivity. Native ::numeric is exact on this corpus, where every value is an
# integer, whether it is stored as a number or as a string.
LOAD_SCORE = ("(coalesce((data->>'queue_depth')::numeric, 0) "
              "+ coalesce((data->>'retest_count')::numeric, 0) * 25)")


def in_schema(sql: str, schema: str) -> str:
    out = CALL.sub(schema + r".\1(", sql)
    out = out.replace("CREATE SCHEMA IF NOT EXISTS xpr;", f"CREATE SCHEMA IF NOT EXISTS {schema};")
    assert not CALL.search(out), "a call into xpr. survived the rewrite"
    return out


def main():
    dsn = os.environ["AUTOSQL_SPIKE_DSN"]
    if "port=55433" in dsn or "dbname=autosql_spike" not in dsn:
        raise SystemExit("REFUSING: setup runs only against autosql_spike on the throwaway container")
    c = psycopg2.connect(dsn)
    c.autocommit = True
    cur = c.cursor()
    out = {"runtimes": {}, "tables": {}}

    for schema, path in RUNTIMES.items():
        sql = open(path, encoding="utf-8").read()
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute(in_schema(sql, schema))
        cur.execute("""select p.proname, p.proparallel, p.provolatile, pg_get_functiondef(p.oid)
                         from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = %s order by p.proname, p.oid""", (schema,))
        rows = cur.fetchall()
        bodies = "\n".join(r[3] for r in rows)
        leaks = sorted(set(m.group(0) for m in CALL.finditer(bodies)))
        assert not leaks, f"{schema}: installed bodies still call into xpr.: {leaks}"
        normalized = bodies.replace(schema + ".", "xpr.")
        out["runtimes"][schema] = {
            "source": os.path.relpath(path, ROOT),
            "source_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
            "functions": len(rows),
            "proparallel": sorted(set(r[1] for r in rows)),
            "provolatile": sorted(set(r[2] for r in rows)),
            "installed_sha256_schema_normalized": hashlib.sha256(normalized.encode()).hexdigest(),
        }

    cur.execute("""select count(*), string_agg(distinct proparallel::text, ',')
                     from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'xpr'""")
    out["runtimes"]["xpr (T-4's, untouched)"] = dict(zip(("functions", "proparallel"), cur.fetchone()))

    for n in SIZES:
        src, dst = f"measure_instances_{n}", f"t44_text_{n}"
        cur.execute(f"DROP TABLE IF EXISTS {dst}")
        cur.execute(f"CREATE TABLE {dst} (LIKE {src} INCLUDING ALL)")
        cur.execute(f"""INSERT INTO {dst} (collection, key, data)
                        SELECT collection, key,
                               data || jsonb_build_object('queue_depth', data->>'queue_depth')
                                    || CASE WHEN data ? 'retest_count'
                                            THEN jsonb_build_object('retest_count', data->>'retest_count')
                                            ELSE '{{}}'::jsonb END
                          FROM {src} ORDER BY ctid""")
        cur.execute(f"VACUUM ANALYZE {dst}")
        for t in (src, dst):
            cur.execute(f"""select count(*),
                                   count(*) filter (where collection = 'noun:Sample'),
                                   round(100.0 * count(*) filter (where {LOAD_SCORE} > 195) / count(*), 3),
                                   round(avg(pg_column_size(data)), 1),
                                   count(*) filter (where jsonb_typeof(data->'queue_depth') = 'string'),
                                   count(*) filter (where jsonb_typeof(data->'queue_depth') = 'number'),
                                   count(*) filter (where data ? 'retest_count'),
                                   pg_relation_size('{t}')
                              from {t}""")
            r = cur.fetchone()
            out["tables"][t] = {"rows": r[0], "rows_in_collection": r[1], "selectivity_pct": float(r[2]),
                                "avg_data_bytes": float(r[3]), "queue_depth_strings": r[4],
                                "queue_depth_numbers": r[5], "with_retest_count": r[6], "heap_bytes": r[7]}
        cur.execute(f"select indexdef from pg_indexes where tablename = '{dst}' order by 1")
        out["tables"][dst]["indexes"] = [x[0] for x in cur.fetchall()]
        # the SAME rows: every key present in both, every non-widget field byte-identical
        cur.execute(f"""select count(*) from {src} s join {dst} d using (collection, key)
                         where (s.data - 'queue_depth' - 'retest_count') = (d.data - 'queue_depth' - 'retest_count')
                           and (s.data->>'queue_depth') = (d.data->>'queue_depth')
                           and (s.data->>'retest_count') is not distinct from (d.data->>'retest_count')""")
        out["tables"][dst]["rows_identical_apart_from_encoding"] = cur.fetchone()[0]

    cur.execute("select version()")
    out["server"] = cur.fetchone()[0].split(" on ")[0]
    json.dump(out, open(os.path.join(HERE, "out", "setup.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
