# Regenerating the T-1 measurement corpus

**Written 2026-08-21 to close the note the owner attached to Q31** ("Leave it gone" — *"leave notes for
how to generate a corpus"*). The scratch database this spike measured against is gone and is not
coming back — `README-db.md` records exactly what happened to it, including the fact that a worker
briefly recreated an empty `autosql_spike` on the **live** container on 2026-08-21 and the driving
session dropped it again the same evening. The timing run (**T-4**, "Run 2" in `../EXPERIMENTS.md`)
cannot start until someone can rebuild those tables, so this file is the rebuild procedure.

**"Corpus"** here just means *the pile of fake rows the benchmark measures against* — six Postgres
tables of made-up records, from 1,000 rows up to 1,000,000.

---

## 0. The headline, before you spend any time

Two separate statements, and the difference matters:

| | |
|---|---|
| **Can `gen_data.py` + `load_data.py` rebuild the corpus the existing sweep measured?** | **Yes — verified end to end today, on a throwaway container, all six sizes.** Every number this file quotes was produced by actually running it on 2026-08-21, not read off an old document. Where it reproduces a figure the old record claimed, that is said explicitly. Two independent passes ran the procedure that day; §5's reference values are the second pass's, which re-measured every size, added the selectivity check, and settled a size figure two of the project's own documents disagreed on. |
| **Do they produce the corpus the *timing run* needs?** | **No — not as they stand.** `../EXPERIMENTS.md` §2.3 requires two extra fields (`queue_depth`, `retest_count`) that `gen_data.py` does not generate. That is a four-line edit, it is Run 2's own build item (§2.4 item 2), and §7 below gives the exact patch, the measured effect, and the reason **every checksum in this file goes stale the moment you apply it.** |

So: this file rebuilds the **original** corpus faithfully, and tells you precisely what changes when
Run 2 extends it.

---

## 1. What the corpus is

### The tables

Six tables, in one throwaway database called `autosql_spike`, one table per size:

```
measure_instances_1000
measure_instances_10000
measure_instances_20000
measure_instances_25000
measure_instances_100000
measure_instances_1000000
```

Those six are what `proto/bench.py` defaults to (`bench.py:506`). `../EXPERIMENTS.md` §2.3 makes
**20,000 · 100,000 · 1,000,000 required** for the timing run, with 1,000 · 10,000 · 25,000 optional
"if the window allows" — they exist to keep the curve comparable with the old sweep. Building all
six costs about 70 seconds (§6), so build all six.

**One table per size, not one shared table.** This is deliberate and you should not consolidate them.
Every query in the benchmark reads the whole table top to bottom (a **sequential scan** — Postgres
has no way to skip rows here, see §9). If all sizes lived in one 1.156-million-row table, the
"1,000,000-row" measurement would actually be scanning 1,156,000 rows and charging the extra 156,000
to the 1M result. `analysis/measurement.md` §3 states the same reason.

### What one row looks like

The **column definitions** are copied byte-for-byte from the real GIMS migration
(`gims-ledger/migrations/pg/0001_instances.sql:13-18`), which is the entire point — the benchmark has
to measure the table shape GIMS actually uses:

```sql
CREATE TABLE IF NOT EXISTS measure_instances_<N> (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       JSONB NOT NULL,
    PRIMARY KEY (collection, key)
);
```

**Precisely — the names differ, the shape does not.** The three column lines and the
`PRIMARY KEY (collection, key)` line are character-identical to the migration. The `CREATE TABLE`
line is not: production's table is called `instances`, and the corpus calls each table
`measure_instances_<N>` (`load_data.py:14-21`, which keeps the migration's `IF NOT EXISTS`). The GIN
index is the same story — `load_data.py:35` builds `idx_measure_instances_<N>_data_gin` where
migration `0002_instances_data_gin.sql:36-37` builds `idx_instances_data_gin`; the definition,
`USING GIN (data jsonb_path_ops)`, is identical. **Nothing about the shape being measured differs.
Only the names do**, and they have to, because six sizes cannot all be called `instances`.

`collection` is the literal string `noun:Sample` in every row. `key` is `S-0`, `S-1`, … `S-<N-1>`.
`data` is the record. Here is row 0 exactly as the generator emits it (verified 2026-08-21):

```json
{"id":"S-0","status":"closed","due_date":"2027-03-11","priority":2,
 "field_0":"foxtrot-4787","field_1":{"code":"lima","n":36},"field_2":872.8432,
 "field_3":699.5347,"field_4":{"code":"papa","n":0},"field_5":{"code":"oscar","n":47},
 "field_6":null,"field_7":true,"field_8":null,"field_9":{"code":"lima","n":70},
 "field_10":-195.9299,"field_11":"bravo-9921","field_12":"mike-9954",
 "field_13":{"code":"juliet","n":44},"field_14":"juliet-9407"}
```

The rules behind that shape (`gen_data.py:24-47`):

| part | rule | why it is that way |
|---|---|---|
| `id` | always `S-<i>` | a stable identity so two runs' answers can be compared row for row |
| `status` | ~60% `"open"`, else `closed`/`hold`/`void` | the widget filters on it; 60% keeps a realistic majority |
| `due_date` | ISO date, uniform over −30…+370 days from 2026-08-19, **omitted entirely in 5% of rows** | the missing key is the point — it reproduces the `S-4` case in GIMS's own test fixture, where a record simply has no due date |
| `priority` | integer 1–5 | filler with a small value domain |
| `field_0` … `field_N` | 5–15 extra keys per row, random mix of string / float / bool / null / small nested object | real records carry junk the widget never looks at; scanning cost depends on total document size, so the junk has to be there |

Mean stored document size is **283 bytes** (measured: 283.3 / 282.7 / 282.3 / 282.4 / 283.0 / 284.1
across the six sizes, 2026-08-21). On the wire, as `jsonb::text`, it is 315–317 bytes/row —
`../FINDINGS.md` §4.2 records that split, and the larger figure is the one payload numbers use.

### The seed, and why a fixed seed is the whole game

`gen_data.py:14` sets `SEED = 1729` and seeds one `random.Random(SEED)` for the entire file. Nothing
in the generator reads the clock, the OS entropy pool, or the machine name.

That means **the corpus is a pure function of the row count** — same seed, same Python, same bytes,
on any machine, forever. Three consequences, all of which the timing run depends on:

1. **A measurement anyone re-runs is only comparable if the data is identical.** A benchmark that
   re-randomises its data every run cannot tell "the code got slower" from "this run drew harder
   rows". With a fixed seed, a difference between two runs is a difference in the *code or the host*,
   which is the only kind of difference worth reporting.
2. **You can verify a load, byte for byte.** Because the bytes are predictable, §5's checksums exist
   at all. Without the seed there would be nothing to compare a freshly-loaded table against.
3. **The sizes nest.** The first 1,000 rows of the 10,000-row table are *identical* to the whole
   1,000-row table — verified today at both the file level and inside Postgres (§5, prefix check).
   So the size sweep varies exactly one thing: how many rows. Nothing else moves.

**Do not change the seed. Do not "improve" the generator's randomness.** If you change either, every
number in `FINDINGS.md`, `analysis/measurement.md` and this file stops applying, and the timing run
loses its only baseline.

One small mechanical note: the CSV the generator writes uses **CRLF** line endings (Python's `csv`
module default; verified). Postgres `COPY … FORMAT csv` handles that correctly. Do not "fix" it — the
checksums in §5 are checksums of CRLF files.

---

## 2. What you need on the machine

| | | verified 2026-08-21 |
|---|---|---|
| **Docker** | to run a throwaway Postgres | Docker 29.1.3 present |
| **The Postgres image** `pgvector/pgvector:pg16` | this is the image the whole spike measured on | present locally (438 MB); `docker run --rm pgvector/pgvector:pg16 postgres --version` → **PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1)**, an exact match for the recorded environment |
| **CPython 3.12** | to run the generator | system `python3` is 3.12.3 |
| **`psycopg2`** | the loader talks to Postgres from the host | **the system `python3` does NOT have it.** `GIMS-Project/.venv/bin/python` does (psycopg2 2.9.12, Python 3.12.3). On a machine with no GIMS checkout: `python3 -m venv /tmp/corpusvenv && /tmp/corpusvenv/bin/pip install psycopg2-binary` |
| **Disk** | ~1.2 GiB free (§6) | 19.2 GiB free of 457 GiB, **96% used** — it fits, but not comfortably |
| **`psql`** | *not* needed on the host | there is no `psql` on this machine; every SQL command below runs through `docker exec` |

The image matters more than it looks. `pgvector/pgvector:pg16` is not chosen for pgvector — it is
chosen because that is the image the recorded measurements ran on, and a different minor version can
change plan choice and therefore timings.

---

## 3. Bringing up a Postgres to load into

> ### ⚠️ Do not load this into `glp-strong-db`.
> That container (host port **55433**) hosts the owner's live `glp_strong` data. The spike originally used
> it, which is exactly why `README-db.md` had to scrub a password out of this tree: the role
> `glp_owner` owns the live database as well as the scratch one, so its password is a working
> credential for real data. **Use a throwaway container instead**, on a different port. Port 55433 is
> occupied by the live container anyway (verified today), so the commands below use **55434**.

```bash
docker run -d --name autosql-corpus \
  --shm-size=1g \
  -p 127.0.0.1:55434:5432 \
  -e POSTGRES_USER=glp_owner \
  -e POSTGRES_PASSWORD=spike \
  -e POSTGRES_DB=autosql_spike \
  pgvector/pgvector:pg16

# wait for it (takes ~2s on this machine)
until docker exec autosql-corpus pg_isready -U glp_owner -d autosql_spike >/dev/null 2>&1; do sleep 1; done
docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAc "select version()"
# -> PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu, ...
```

Four things in that command are load-bearing:

- **`--shm-size=1g`** — this is the fix for the failure that killed the original 1M load. See §8.
- **`-p 127.0.0.1:55434:5432`** — bound to loopback only, so nothing outside the machine can reach
  it, and on a port that does not collide with the live container.
- **`POSTGRES_USER=glp_owner`** — keeps the corpus owned by a role of the same name, so nothing in
  the DDL, the ownership or the checksums depends on a rename. It is a *different* `glp_owner`, in a
  *different* cluster, that owns nothing real. **It does not save you from setting the DSN** — see
  the box below.
- **`POSTGRES_DB=autosql_spike`** — creates the database at container start. **Note that
  `load_data.py` does not create a database**; it connects to one that already exists (`load_data.py:25`).
  Skip this and every load fails with `FATAL: database "autosql_spike" does not exist`.

> ### ⚠️ `AUTOSQL_SPIKE_DSN` is mandatory, not a convenience.
> **Every script in this directory defaults to port 55433 — the live container — when the variable
> is unset.** Verified by reading them: `load_data.py:12` and `bench.py:33-34` are both
> `os.environ.get("AUTOSQL_SPIKE_DSN") or "host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike"`.
> Matching the role name in your throwaway container does nothing about this — the fallback pins the
> **port**, and the string `55434` appears in no script here.
>
> That matters because of what the loader does first: `load_data.py:27` is
> `DROP TABLE IF EXISTS measure_instances_<N>`, followed by a `CREATE` and a `COPY`, aimed at
> whatever cluster the DSN reached. Run it with the variable unset and those statements are aimed at
> `glp-strong-db`. On this machine that connection currently fails for want of a password (there is
> no `~/.pgpass`, verified) — but "it happens to fail" is not a safety property, and the credentials
> block immediately below tells you to export `PGPASSWORD`.
>
> **`conformance.py` cannot be redirected at all.** Its connection is a literal
> `dict(host="127.0.0.1", port=55433, user="glp_owner", dbname="autosql_spike")` at
> `conformance.py:55`, and the file contains no `os.environ` reference — `AUTOSQL_SPIKE_DSN` never
> reaches it. Edit that line to your throwaway port before running it.
>
> **Set the DSN in every shell, before every command below. There is no supported path that omits
> it.**

### Credentials

Per `README-db.md`, every script here reads its connection details from the environment and the
password is deliberately absent from the repo. Two different mechanisms, because two scripts were
written differently:

```bash
# load_data.py and bench.py read one connection string:
export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=spike dbname=autosql_spike"

# conformance.py builds its connection from keyword arguments instead and takes the password the
# normal libpq way.  NOT needed for a corpus rebuild, and NOT sufficient on its own: its port is
# hard-coded to 55433 (conformance.py:55).  Set this only after you have edited that line.
export PGPASSWORD=spike
```

**`PGPASSWORD` alone is not enough for `conformance.py`** — it supplies the password, not the port,
and per the box above that script's port is hard-coded to the live container. `conformance.py` is not
part of a corpus rebuild in any case (§4 uses `gen_data.py` and `load_data.py` only), so if all you
are doing is rebuilding the corpus you do not need `PGPASSWORD` at all.

`spike` is a throwaway password for a throwaway container that is bound to loopback and deleted when
you are done. It guards nothing, which is the point: **the reason the real password was scrubbed does
not apply to a container that holds only fake rows.** If you ever do point these scripts at the live
container instead, the `README-db.md` rules apply again in full and the password must come from your
environment or `~/.pgpass` — never from a file in this repo.

---

## 4. Generating and loading — the literal commands

Set up the paths once:

```bash
PROTO="/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto"
WORK="$(mktemp -d)"                                   # CSVs land here, not in the repo
PY="/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python"   # the one with psycopg2
export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=spike dbname=autosql_spike"
export PYTHONDONTWRITEBYTECODE=1                      # keep __pycache__ out of the spike tree
```

Then, one size at a time — **generate, load, delete the CSV before generating the next one.** The
1,000,000-row CSV alone is 342 MiB and there is not much disk on this machine (§6):

```bash
cd "$WORK"
for n in 1000 10000 20000 25000 100000 1000000; do
  echo "--- $n ---"
  python3   "$PROTO/gen_data.py"  "$n" "$WORK/c$n.csv"     # writes the CSV, prints avg_json_bytes
  "$PY"     "$PROTO/load_data.py" "$n" "$WORK/c$n.csv" gin # creates + loads the table, prints sizes
  rm -f "$WORK/c$n.csv"
done
```

What each step does:

- **`gen_data.py <n> <path>`** writes an `<n>`-line CSV of `collection,key,json` and prints
  `{"rows": …, "json_bytes": …, "avg_json_bytes": …}`. Pure Python, no database involved.
- **`load_data.py <n> <path> gin`** (`load_data.py:23-45`) drops any existing
  `measure_instances_<n>`, recreates it with the GIMS DDL, streams the CSV in with `COPY` (Postgres's
  bulk loader — far faster than row-by-row `INSERT`), then:
  - **`gin`** as the third argument builds the **GIN index** the real GIMS table carries
    (`migrations/pg/0002_instances_data_gin.sql:36-37`). An index is a side structure that lets
    Postgres jump straight to matching rows. **`../EXPERIMENTS.md` §2.3 requires it**, and not because
    it helps — Q11 means the generated queries can never use it (across 36 measured query plans it was
    used *zero* times). It is there so the corpus is honestly shaped like production, and so Run 2 can
    *demonstrate* the index is unused rather than assume it. **Omit the word `gin` and you have built
    a different table from the one the run is specified against.**
  - **`VACUUM ANALYZE`** — makes Postgres collect statistics about the freshly-loaded table. Without
    it the planner is guessing about a table it has never seen, and plan choice (and therefore every
    timing) is unreliable. This is also the step that used to blow up at 1M; see §8.
  - prints `{"table": …, "rows": …, "copy_seconds": …, "gin_seconds": …, "total_size": …}` — **capture
    this output.** The original run did not, and `../EXPERIMENTS.md` §2.6 had to strike its own load
    timings as uncitable as a result.

`load_data.py` starts with `DROP TABLE IF EXISTS`, so re-running any size is safe and idempotent.

### One more step the timing run needs — the SQL runtime

The corpus is data only. The compiled arms of the benchmark also need the **`xpr` schema** — 21
helper SQL functions that make Postgres reproduce Python's expression semantics exactly. On the old
database these already existed, which is why `../EXPERIMENTS.md` §2.4 lists them under "exists and is
reused". **On a fresh container they do not exist**, and nothing in the loader installs them:

```bash
docker cp "$PROTO/runtime.sql" autosql-corpus:/tmp/runtime.sql
docker exec autosql-corpus psql -U glp_owner -d autosql_spike -q -f /tmp/runtime.sql
docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAc \
  "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='xpr'"
# -> 21     (verified 2026-08-21; anything other than 21 means the install did not complete)
```

Two further tables — `measure_instances_tolerant` and `measure_instances_poison` — are **not** part of
the corpus and must not be built by hand. `bench.py` and `probe_extra.py` create them for themselves,
inline, at run time.

---

## 5. Verifying the corpus is actually correct

**Do this every time, before any timing.** It catches two quiet failures, and both of them are quiet
in the same way — nothing errors, nothing looks wrong, and the measurements come out looking fine:

1. **A table that loaded *most* of its rows.** Every millisecond you then measure is a measurement of
   a smaller table than the one you are reporting.
2. **A corpus whose selectivity is out of band.** `../EXPERIMENTS.md` §2.5 item 6 **voids Run 2** if
   measured selectivity falls outside 4.5%–6.0% at any size. Caught here it costs a rebuild; caught
   after the run it costs the whole exclusive measurement window.

### First, settle the tables — or the sizes will not match

Run a plain `VACUUM` on each table before reading any size. One statement per `-c`: `VACUUM` cannot
run inside a transaction block, and `psql -c "VACUUM a; VACUUM b"` wraps both in one.

```bash
for n in 1000 10000 20000 25000 100000 1000000; do
  docker exec autosql-corpus psql -U glp_owner -d autosql_spike -q -c "VACUUM measure_instances_$n"
done
```

**Why this step exists — measured, not assumed.** PostgreSQL 16 extends a table in bulk while `COPY`
runs, so a freshly loaded table carries trailing pages that hold nothing. The `VACUUM ANALYZE` at the
end of `load_data.py` does not always release them; a later autovacuum does. On the 10,000-row table
today the loader printed a total of **8 256 kB**, and twenty-two seconds later — after autovacuum had
run on it (`pg_stat_user_tables.autovacuum_count` 0 → 1) — the identical table read **8 216 kB**.
Nothing about the data changed. An explicit `VACUUM` makes the reading deterministic: a second
`VACUUM` moved no size at any of the six (verified).

### The content and size checks

Run this for each size (substitute `<N>`):

```sql
SELECT count(*)                                                        AS rows,
       md5(string_agg(md5(data::text), '' ORDER BY (right(key,-2))::bigint)) AS content_md5,
       sum(('x'||substr(md5(data::text),1,8))::bit(32)::bigint)        AS xor_sum,
       count(*) FILTER (WHERE data->>'status' = 'open')                AS open_rows,
       count(*) FILTER (WHERE data ? 'due_date')                       AS with_due_date,
       pg_relation_size('measure_instances_<N>')       / 1024          AS heap_kb,
       pg_indexes_size('measure_instances_<N>')        / 1024          AS index_kb,
       pg_total_relation_size('measure_instances_<N>') / 1024          AS total_kb
FROM measure_instances_<N>;
```

**Sizes in kB, not `pg_size_pretty`.** The pretty form rounds — it prints `16 MB` for anything from
roughly 15.5 to 16.5 MB — which is enough to hide a materially wrong table, and enough to make the
reference table below impossible to check by hand. `load_data.py` prints the pretty form; this check
deliberately does not.

as one command:

```bash
for n in 1000 10000 20000 25000 100000 1000000; do
  docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAF'|' -c "
    SELECT '$n', count(*),
           md5(string_agg(md5(data::text), '' ORDER BY (right(key,-2))::bigint)),
           sum(('x'||substr(md5(data::text),1,8))::bit(32)::bigint),
           count(*) FILTER (WHERE data->>'status'='open'),
           count(*) FILTER (WHERE data ? 'due_date'),
           pg_relation_size('measure_instances_$n')/1024,
           pg_indexes_size('measure_instances_$n')/1024,
           pg_total_relation_size('measure_instances_$n')/1024
    FROM measure_instances_$n;"
done
```

### And the selectivity check — this is the one that can void the timing run

`../EXPERIMENTS.md` §2.5 item 6 makes **measured selectivity outside 4.5%–6.0%**, at any size,
grounds for **voiding Run 2**. Selectivity is a property of the corpus, so it is catchable here — in
seconds, before anyone books the two-to-three-hour exclusive measurement window — rather than
afterwards, when the only remedy is to throw the measurements away.

**Selectivity** is the fraction of rows that survive the widget's filter. The widget
(`bench.py:39-46`) keeps a row when `status` is `"open"` **and** `days_left < 7`, where `days_left`
is `days_between(today(), $.due_date)` evaluated against the pinned `now` of `2026-08-19T12:00:00Z`
(`bench.py:47`).
Written as plain SQL it needs neither the compiler nor the `xpr` schema:

```bash
for n in 1000 10000 20000 25000 100000 1000000; do
  docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAF'|' -c "
    SELECT '$n',
           count(*) FILTER (WHERE data->>'status' = 'open'
                              AND data ? 'due_date'
                              AND ((data->>'due_date')::date - DATE '2026-08-19') < 7) AS qualifying,
           round(100.0 * count(*) FILTER (WHERE data->>'status' = 'open'
                              AND data ? 'due_date'
                              AND ((data->>'due_date')::date - DATE '2026-08-19') < 7)
                 / count(*), 3) AS selectivity_pct
    FROM measure_instances_$n;"
done
```

**Why the `::date` cast is allowed here and nowhere else.** `../analysis/measurement.md` §4 marks the
B4 "ceiling" arm UNSAFE precisely because `::date` *raises* on a malformed date — the totality
violation `xpr.pdate_ms` exists to prevent. That warning is about production records. It does not
apply to this check, because every `due_date` in this corpus comes from
`datetime.date.isoformat()` (`gen_data.py:31`) and is therefore well-formed by construction. **Do not
lift this query out of §5 and point it at real data.**

### The expected values

**All measured 2026-08-21** by running exactly the procedure above, with the **unmodified**
`gen_data.py` (`SEED = 1729`), CPython 3.12.3, PostgreSQL 16.14 on `pgvector/pgvector:pg16`.

**Content. These are byte-stable, and they are the checks to trust:**

| rows | CSV bytes | CSV md5 | `content_md5` | `xor_sum` | `open_rows` | `with_due_date` |
|---:|---:|---|---|---:|---:|---:|
| 1 000 | 355 398 | `f308a3d6097279a4260eff6071f9a376` | `cb897527ffb8880dae6cb50b3522ffb7` | 2 129 339 103 058 | 576 | 962 |
| 10 000 | 3 555 177 | `31bd016850e442014c7b2e5f6c80987b` | `e47fffd8668c7e86a96da29b56fcc4d2` | 21 445 508 006 250 | 6 022 | 9 512 |
| 20 000 | 7 111 399 | `947365d91d34b011388143fbecf1f102` | `5afba2dfab6a70e316ae6bdfc92c3d49` | 43 036 592 690 947 | 12 099 | 18 997 |
| 25 000 | 8 893 446 | `efc5f1f3f91082653bd827d3cea6ba2d` | `703c70272bd059defb1456f2282e61f8` | 53 727 479 121 172 | 15 184 | 23 749 |
| 100 000 | 35 671 116 | `a68cd5936dd8d4e1b5cdef477bab4e08` | `5a314862483b65f021b9f6bf0ac64dd3` | 214 309 125 581 975 | 60 134 | 95 061 |
| 1 000 000 | 358 818 019 | `acc2a9c6bb566bfc364363a6fd630a0d` | `000b9b89fdb427a0df0cc999fddb8de3` | 2 149 494 639 183 118 | 598 997 | 950 318 |

**Selectivity. The band is 4.5%–6.0% at every size, and it is a pass/fail gate:**

| rows | qualifying rows | selectivity | inside 4.5–6.0%? |
|---:|---:|---:|:--:|
| 1 000 | 50 | **5.000%** | yes |
| 10 000 | 510 | **5.100%** | yes |
| 20 000 | 1 055 | **5.275%** | yes |
| 25 000 | 1 338 | **5.352%** | yes |
| 100 000 | 5 202 | **5.202%** | yes |
| 1 000 000 | 52 327 | **5.233%** | yes |

Every size sits between 5.000% and 5.352% — the 5.00%–5.35% range `../EXPERIMENTS.md` §2.3 quotes
for the original sweep, to the rounding — and the qualifying-row counts reproduce `../analysis/measurement.md` §5.5's
"qualifying rows in table" column digit for digit (50 / 510 / 1 055 / 1 338 / 5 202 / 52 327). None
of them is near an edge of the band, so a rebuild that lands near 4.5% or 6.0% is not "borderline
but acceptable" — it is a rebuilt corpus that is not this one, and the seed or the generator is the
place to look.

**Size on disk, in kB, read after the settling `VACUUM`:**

| rows | heap | index | FSM + VM | TOAST | **total** |
|---:|---:|---:|---:|---:|---:|
| 1 000 | 432 | 496 | 32 | 8 | **968** |
| 10 000 | 4 248 | 3 928 | 32 | 8 | **8 216** |
| 20 000 | 8 488 | 7 752 | 32 | 8 | **16 280** |
| 25 000 | 10 608 | 9 616 | 32 | 8 | **20 264** |
| 100 000 | 42 448 | 37 552 | 40 | 8 | **80 048** |
| 1 000 000 | 428 696 | 288 008 | 144 | 8 | **716 856** |

**Those rows sum, and showing the middle columns is the reason.** `total` is
`pg_total_relation_size`, which is **not** heap + index: it also counts the **free space map** and
**visibility map** — two small bookkeeping files Postgres keeps beside every table — and the
**TOAST** side table with its index, which here is 0 bytes of data plus an 8 kB empty index, because
a 283-byte document never overflows an 8 kB page. An earlier version of this table labelled the last
column `heap+index`, and it did not add up: 432 + 496 is 928, not 968. The missing 40 kB is 24 kB of
free space map, 8 kB of visibility map and 8 kB of empty TOAST index.

**What `load_data.py` prints instead.** The loader reports `pg_total_relation_size` in
`pg_size_pretty` form at the instant the load finishes, before anything has settled:

| | 1 000 | 10 000 | 20 000 | 25 000 | 100 000 | 1 000 000 |
|---|---:|---:|---:|---:|---:|---:|
| at load, pretty | 968 kB | 8 256 kB | 16 MB | 20 MB | 78 MB | 700 MB |
| at load, bytes | 991 232 | 8 454 144 | 17 088 512 | 21 094 400 | 82 214 912 | 734 101 504 |

Those are the figures §6 quotes and the ones the old record recorded. They run up to 2.5% larger than
the settled figures above, for the reason at the top of this section. Capture them anyway — §4 says
to — but compare a rebuild against the settled table, not against these.

### These size figures reproduce the old record — with one exception the claim has to carry

`../analysis/measurement.md` §3 recorded 968 kB / 8 256 kB / 16 MB / 20 MB / 78 MB and **700 MB
(419 MB heap + 281 MB GIN)** at 1M, from the database that no longer exists. Rebuilding from scratch
today landed on the same at-load bytes at all six sizes — including **734 101 504 bytes** at 1M,
digit for digit what §3 quotes. With the checksums above, that is the strongest single piece of
evidence that this procedure regenerates *the same corpus* and not merely a similar one.

**The exception is at 10,000 rows, and it is the project disagreeing with itself.**
`../analysis/measurement.md` §3 says **8 256 kB**. `../FINDINGS.md` §4.2 re-read the live table and
says **8 216 kB**, calling it "a 0.5% error", and `../FINDINGS.md` §4.12 row 13 carries it as a
cosmetic defect logged against `measurement.md`.

**Both documents are right, and today's rebuild is why we can say so.** It produced *both numbers,
from the same table, twenty-two seconds apart* — 8 256 kB at load, 8 216 kB once autovacuum had
released the trailing pages. `measurement.md` §3's figure is quoted as `load_data.py` output
verbatim, so it is a load-time reading; `FINDINGS.md` §4.2's is a later read-only re-read of a table
that had been sitting there for hours. Neither seat mis-measured. The number moves.

What that does **not** undermine: the reproduction. The content checks — CSV md5, `content_md5`,
`xor_sum`, row counts, distributions and selectivity — are byte-stable and reproduce exactly, and
*both* of the disputed size figures were reproduced as well.

What it **does** undermine: any reading of the size figures as a byte-exact fingerprint. They are
not one. An on-disk size is only comparable when the moment it was read is stated, which is why this
section settles the tables first and quotes the settled numbers. Treat the sizes as corroboration
and the checksums as the evidence.

The distribution columns reproduce the record too: at 100,000 rows the old record's independently
re-derived figures were **60.13% `open`** and **4.94% missing `due_date`** (`../FINDINGS.md` §4.2) —
today's load gives 60 134 open (60.13%) and 95 061 with a due date (4.94% missing).

### How to read each check

- **`rows`** — must equal N exactly. This alone catches the short-table failure.
- **`content_md5`** — every row's document hashed, in row order, then hashed again. Catches wrong
  content, duplicated rows, or a row loaded in the wrong place, which a count cannot. It sorts the
  whole table, so at 1M it takes a few seconds; that is fine.
- **`xor_sum`** — the same idea without the sort: a plain sum over per-row hashes, order-independent
  and cheap. Use it if you want a fast check at 1M. It cannot detect a re-ordering, but re-ordering is
  not a failure mode `COPY` produces.
- **`open_rows` / `with_due_date`** — human-legible spot checks. If these are near-but-not-equal to
  the table, you have the right generator with the wrong seed. If they are proportionally right but
  the count is short, the load truncated.
- **`heap_kb` / `index_kb` / `total_kb`** — `heap` is the table's own data file, `index` is the
  primary key plus the GIN index, `total` is everything including the two maps and the TOAST side
  table. An `index_kb` far below `heap_kb`, or missing entirely, means the `gin` argument was
  forgotten (§4). A `total_kb` off by a percent or two while every checksum matches means the tables
  were not settled with `VACUUM` — re-read them, do not re-load them.
- **`selectivity_pct`** — must be inside **4.5%–6.0%** at every size. Outside it,
  `../EXPERIMENTS.md` §2.5 item 6 voids Run 2, so stop: check `SEED` and `gen_data.py` before
  anything else. Do not adjust it after timing has started.

**One free cross-check, no reference values needed** — the nesting property from §1. The first 1,000
rows of the 10,000-row table must hash to the 1,000-row table's `content_md5`:

```bash
docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAc "
  SELECT md5(string_agg(md5(data::text), '' ORDER BY (right(key,-2))::bigint))
  FROM measure_instances_10000 WHERE (right(key,-2))::bigint < 1000;"
# -> cb897527ffb8880dae6cb50b3522ffb7   (verified 2026-08-21: identical to the 1,000-row table)
```

If that holds, your generator is producing the reference stream even if you have lost this file's
reference table.

**Caveat on `content_md5`, stated rather than hidden:** it hashes `data::text`, which is Postgres's
own normalisation of the JSON (jsonb reorders keys and canonicalises numbers). It is therefore stable
within PostgreSQL 16.14 and **may legitimately differ on a different major version**. The CSV md5 in
the same table has no such dependency — it is a hash of the generator's own bytes, so it is the check
to trust if you are on a different Postgres. If the CSV md5 matches and `content_md5` does not, you
have a Postgres difference, not a corpus problem.

---

## 6. How long it takes, and how much disk

**Measured 2026-08-21**, all six sizes, on this 20-core host — with the caveat that this was a
**busy** host (1-minute load average 3.3–5.1 during the run), not the quiet exclusive host the timing
run itself requires. Treat these as "roughly this long", not as measurements of anything:

| rows | generate (wall) | `copy_seconds` | `gin_seconds` | CSV on disk | table on disk |
|---:|---:|---:|---:|---:|---:|
| 1 000 | 0.04 s | 0.01 | 0.01 | 347 KiB | 968 kB |
| 10 000 | 0.25 s | 0.09 | 0.10 | 3.4 MiB | 8 256 kB |
| 20 000 | 0.45 s | 0.21 | 0.19 | 6.8 MiB | 16 MB |
| 25 000 | 0.54 s | 0.28 | 0.25 | 8.5 MiB | 20 MB |
| 100 000 | 2.20 s | 1.28 | 1.23 | 34 MiB | 78 MB |
| 1 000 000 | 24.37 s | 11.49 | 19.91 | **342 MiB** | **700 MB** |
| **total** | **~28 s** | | | | **823.9 MiB** |

**"table on disk" here is the at-load figure** — `pg_total_relation_size` in `pg_size_pretty` form,
as `load_data.py` prints it the moment a load finishes. §5's size table is the same measure read
after the tables settle, and runs 0–2.5% smaller; the six settled figures total 822.9 MiB against
823.9 MiB here. Either total is "about 823 MB". They are two readings of one thing, not two things
to add together.

The 1M load, including its `VACUUM ANALYZE`, took **32.0 s wall**. Container start to ready: ~2 s.
**Whole rebuild, all six sizes: comfortably under two minutes**, assuming the Docker image is already
pulled. `../EXPERIMENTS.md` §2.6 quotes "roughly 823 MB of database across the six sizes" — today's
rebuild totals 823.9 MiB, so that figure stands.

**Disk you need:**

- **~824 MiB** for the finished database.
- **plus the largest CSV you have on disk at once — 342 MiB** if you delete each one after loading, as
  §4 does. Keep all six and it is 395 MiB instead; there is no reason to.
- **Peak: about 1.2 GiB.** Free space today: **19.2 GiB of 457 GiB, 96% used** (measured 2026-08-21
  after teardown). `../EXPERIMENTS.md` §2.6 puts it well — *"It fits, but not comfortably; generate and
  drop the CSVs one size at a time."*

**Not measured, and do not invent a number for it:** how long a *fresh* `docker pull` of
`pgvector/pgvector:pg16` takes on a slow connection. The image was already cached here (438 MB).

---

## 7. What Run 2 must change, and what breaks when it does

`../EXPERIMENTS.md` §2.3 specifies a corpus with two extra fields, because the timing run's widget is
built around `coalesce()` over a frequently-missing key. **`gen_data.py` does not generate them.**
This is §2.4 item 2 of Run 2's own build list, and Q7 explicitly permits editing these scripts in
place. The patch, appended at the end of `make_row()` just before `return row`:

```python
    row["queue_depth"] = rnd.randint(0, 200)
    if rnd.random() < 0.15:
        row["retest_count"] = rnd.randint(0, 3)     # absent 85% of the time -- what coalesce is for
```

I applied that to a **scratch copy** (not to `gen_data.py` in this tree — that edit belongs to the
run that needs it) and measured, at N = 100,000, on 2026-08-21:

| | measured | required by §2.3 |
|---|---|---|
| selectivity of `queue_depth + retest_count*25 > 195` | **5.31%** | between 4.5% and 6.0% — **passes** |
| `retest_count` absent | 85.09% | ~85% by construction |
| mean stored JSON | **303.2 bytes/row** (was 283.0) | "must be reported" — it moves every payload and scan number in the run |

So the threshold of 195 that §2.3 derived from a 200,000-draw simulation (5.36%) holds up against the
real generator at 100,000 rows (5.31%). Run 2 does not need to re-tune the literal.

**Three consequences nobody should discover the hard way:**

1. **Every checksum in §5 goes stale.** New fields mean new bytes, so the CSV md5s, `content_md5`s,
   `xor_sum`s and table sizes all change. Re-baseline them, in the same way, and record the new table
   in this file next to the old one rather than replacing it — the old corpus is what the existing
   sweep's numbers refer to.
2. **The extended corpus is not row-identical to the old one.** Measured, not assumed: adding those
   draws shifts the random stream, so **only row 0 keeps its old values; rows 1 onward all change**
   (checked over 1,000 rows: 1 of 1,000 unchanged). The distributions are the same, the specific
   values are not. `../EXPERIMENTS.md` §2.3 is right that the date-widget control still runs on "the
   same corpus" in the sense that matters — same shape, same generator, same session — but do not
   quote an old absolute number as if it had been measured on these exact rows.
3. **Regenerate before timing, never after.** §2.3 is blunt about this and it is worth repeating: if
   selectivity lands outside 4.5–6.0%, tune the literal and rebuild *before* you time anything —
   "never by tuning until a timing looks good."

---

## 8. The two tuning notes, explained

These are recorded in `../EXPERIMENTS.md` §2.6 as a "known load failure to plan around". Here is what
they actually mean.

### `/dev/shm` — why the 1,000,000-row load used to die

The original 1M load **aborted after `COPY` and the GIN build had both succeeded**, at its
`VACUUM ANALYZE`, with:

```
psycopg2.errors.DiskFull: could not resize shared memory segment to 67128640 bytes
```

`/dev/shm` is a small in-memory filesystem inside the container that Postgres uses for **shared
memory between parallel worker processes**. Docker's default size for it is **64 MB** — verified
today: `docker exec glp-strong-db df -h /dev/shm` still reads `64M`. A parallel `VACUUM` on a
419 MB table wanted a ~64 MB segment, could not get it, and the whole statement failed. The timing
print was lost with it, which is why the record has no load timings for 1M at all.

**Two ways out. Take the first one:**

- **Give the container more `/dev/shm`.** `--shm-size=1g` on `docker run`, as §3 does. **Verified
  today: with 1 GB of `/dev/shm`, the 1,000,000-row load completes end to end — `COPY` 11.49 s, GIN
  19.91 s, `VACUUM ANALYZE` included, 32.0 s wall, no error.** This is the clean fix, it is set once
  at container creation, and it changes no database setting.
- **Or turn the parallelism off**, which is what was done originally:
  ```sql
  ALTER SYSTEM SET max_parallel_maintenance_workers = 0;  SELECT pg_reload_conf();
  ```
  `max_parallel_maintenance_workers` controls how many helper processes Postgres may use for
  maintenance work like `VACUUM` and index builds. At 0 it does everything in one process, needs no
  shared segment, and cannot hit this failure — it is just slower. **This is the worse option**,
  because `ALTER SYSTEM` is **cluster-wide and persistent**: it silently changes every other database
  in that cluster and survives restarts. On the live container it was set to 0 for the load and
  reverted afterwards (`ALTER SYSTEM RESET max_parallel_maintenance_workers`), and
  `../EXPERIMENTS.md` §2.6 notes it has since been back at **2** — so anyone reloading against that
  container without `--shm-size` would hit the original failure again, exactly as before.

Since §3 tells you to use a throwaway container anyway, `--shm-size=1g` costs nothing and the
`ALTER SYSTEM` route can be skipped entirely.

### `synchronize_seqscans` — not a load setting, but do not leave for the timing run without reading this

Not a corpus concern, flagged here because it is the setting most likely to make a rebuilt corpus
produce nonsense timings. `../FINDINGS.md` §4.9 measured a **170× spread on an identical query and
identical table** — 40.76 ms versus 6 916.85 ms — from this one setting. It lets a sequential scan
join one already in progress and start from the middle of the table, so two runs of the same query can
read the table in different orders and hit wildly different amounts of cache. `../EXPERIMENTS.md` §2.4
item 9 requires Run 2 to pin it and record it; §2.5 item 8 makes an unrecorded value grounds for
voiding the run. Read it after loading, before timing:

```bash
docker exec autosql-corpus psql -U glp_owner -d autosql_spike -tAc "SHOW synchronize_seqscans"
```

---

## 9. Tearing it down

```bash
docker rm -f -v autosql-corpus
rm -rf "$WORK"
```

**The `-v` is not optional, and this is a real trap.** The Postgres image declares its data directory
as a volume, so `docker run` without an explicit `-v` creates an **anonymous volume** — and plain
`docker rm -f` leaves it behind. Verified today: after removing the container, ~1 GiB of corpus was
still on disk in a dangling volume, invisible to `docker ps -a`. On a machine at 96% disk, that
matters. If you have already removed a container without `-v`:

```bash
docker volume ls -q -f dangling=true | while read v; do
  echo "$(docker volume inspect -f '{{.CreatedAt}}' "$v")  $v"; done | sort
# find the one created when you started the container, then:  docker volume rm <id>
```

Check nothing else was disturbed — the live container should still be running and untouched:

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
# -> glp-strong-db   0.0.0.0:55433->5432/tcp, ...
```

---

## 10. Decisions made in writing this, and what would overturn them

The owner is away; these were ruled from his recorded answers rather than handed back as questions. Each
one says what it was derived from. **Any single line from him overturns any of these.**

| decision | derived from | reversibility |
|---|---|---|
| **Rebuild into a throwaway container, never `glp-strong-db`** | Q31 "Leave it gone", plus `README-db.md`'s own stated reason for scrubbing the password: `glp_owner` owns the live `glp_strong` database on that container. Loading fake rows next to live data is exactly the risk that scrub was protecting against. | total — the container is deleted in §9 |
| **A literal throwaway password (`spike`) printed in this file** | `README-db.md`'s concern is precisely "a working credential for real data" in git history. A loopback-bound container holding only generated rows is not that. The `AUTOSQL_SPIKE_DSN` / `PGPASSWORD` mechanism is kept exactly as documented, so pointing at a real database still requires a real password from the environment. | total — change one env var |
| **Port 55434** | 55433 is occupied by the live container (verified). No preference of the owner's exists on port numbers. | total |
| **Image `pgvector/pgvector:pg16`** | it is the image every recorded measurement in this spike ran on, and it yields exactly PostgreSQL 16.14 today (verified). A different image is a different experiment. | total |
| **All six sizes, not the three §2.3 requires** | §2.3 makes 1,000 / 10,000 / 25,000 optional "if the window allows"; §6 measures the whole rebuild at under two minutes, so the window always allows. | total — drop sizes from the loop |
| **§5 reads sizes only after an explicit `VACUUM`** | nothing of the owner's bears on it. The choice was between a deterministic reading and one that drifts by up to 2.5% depending on when autovacuum last touched the table (measured, §5). Determinism was chosen so §5 can be a pass/fail check rather than a judgement call; the at-load figures the old record used are kept alongside, not replaced. | total — drop the `VACUUM` loop and read whatever the tables happen to be |
| **§5 gates selectivity at 4.5–6.0% before any timing** | `../EXPERIMENTS.md` §2.5 item 6 already makes that band the void condition for Run 2, and §2.3 says to regenerate "before you time anything." Checking it at verification rather than after measurement applies his own rule where it costs seconds instead of a measurement window. | none needed — it is a read-only query |
| **`gen_data.py` left unmodified in this tree** | Q7 lets the follow-up runs edit these scripts, and §2.4 item 2 assigns the edit to Run 2. Writing it now would silently invalidate §5's reference values for anyone rebuilding the *original* corpus before Run 2 starts. The patch and its measured effects are in §7 instead. | total — §7 is a four-line patch |

**No preference of the owner's was invented anywhere above.** Where there was genuinely nothing to derive
from — container name, port number, the throwaway password string — the cheapest-to-reverse option was
taken and labelled as such.

---

## 11. Glossary

Written per Q41 — *"explain the SQL, skip the coding basics."*

- **Corpus** — the body of generated rows the benchmark measures against. Here: six tables of fake
  records, 1,000 to 1,000,000 rows.
- **Seed** — the fixed number (1729) that makes the "random" generator produce the same rows every
  time. See §1; it is the reason any of this is verifiable.
- **`COPY`** — Postgres's bulk loader. Streams a whole file into a table in one statement, far faster
  than a stream of `INSERT`s. The loader uses psycopg2's `copy_expert`, which streams **from the
  host**, so the CSV never needs to be copied into the container.
- **`jsonb`** — Postgres's binary JSON column type. It normalises what it stores (key order, number
  formatting), which is why §5's `content_md5` is a hash of Postgres's version of the document rather
  than of your file.
- **Sequential scan** — Postgres reading every row of a table in order because nothing lets it skip
  any. Under Q11 this is what every autoSQL query does, always; its cost is proportional to row count.
- **Index / GIN index** — a side structure that lets Postgres jump to matching rows instead of reading
  all of them. GIN is the flavour used for JSON. The corpus carries one because production does; the
  generated queries never use it (§4).
- **Heap** — the part of a table that holds the rows themselves, as distinct from the indexes built
  over them. §5's `heap_kb` is exactly that: the table's own data file, counting no index, no
  bookkeeping map and no TOAST side table. It is Postgres's word, and it is unrelated to the "heap" a
  Python process allocates from — where `../EXPERIMENTS.md` §2.3 says the Python path "holds about
  2.4 GB of heap per request at 1M", that is the other sense entirely.
- **Free space map / visibility map** — two small bookkeeping files Postgres keeps beside every
  table: which pages still have room for a row, and which pages hold nothing needing a vacuum. Tens
  of kB at these sizes. They count toward `pg_total_relation_size`, which is why §5's size columns do
  not sum to heap + index on their own.
- **TOAST** — Postgres's overflow storage for a value too large to fit in an 8 kB page. This corpus
  never uses it: a 283-byte document fits easily, so the TOAST table holds 0 bytes and only its empty
  index costs anything (8 kB).
- **`VACUUM ANALYZE`** — cleans up dead rows and, more importantly here, collects the statistics the
  query planner needs. Skipping it makes the planner guess, and plan choice drives timings. A plain
  `VACUUM` (no `ANALYZE`) is also what §5 runs before reading sizes, for a different reason: it
  releases the empty trailing pages `COPY` leaves behind, which is what makes a size reading
  repeatable.
- **Selectivity** — what fraction of rows survive the filter. The single biggest lever on how long
  either path takes, which is why §2.3 pins it to 4.5–6.0% rather than leaving it to chance.
- **DSN** — "data source name": the connection string (`host=… port=… user=… dbname=…`) the scripts
  read from `AUTOSQL_SPIKE_DSN`.
- **`/dev/shm`** — a small in-memory filesystem inside the container that Postgres's parallel worker
  processes use to share memory. Docker defaults it to 64 MB, which is what broke the 1M load (§8).
- **Run 1 / Run 2** — the two follow-up experiments specified in `../EXPERIMENTS.md`: the correctness
  run (ticket **T-3**) and the timing run (ticket **T-4**). Only Run 2 needs this corpus.

---

## Sources

Every claim above is either cited to a file or labelled as measured on 2026-08-21 by running the
procedure in §3–§5 against a throwaway `pgvector/pgvector:pg16` container, which was destroyed
afterwards. Two passes ran that day, on two throwaway containers: the first on port 55434, and a
second one — which produced §5's settled size table, the selectivity table, and the autovacuum
finding — on a container named `autosql-doccheck` on port **55436**, deliberately off 55434 so it
could not collide with anyone following §3 at the same time. Both were removed with `docker rm -f -v`
and left no dangling volume. The live `glp-strong-db` container was read twice (`df -h /dev/shm`, and
`docker ps` to confirm it was still up and untouched) and **never connected to and never written**.

- `gen_data.py` — the generator; seed at line 14, row rules at lines 24-47.
- `load_data.py` — the loader; DDL at lines 14-21, `COPY`/GIN/`VACUUM` at lines 27-39.
- `README-db.md` — the credential rules, and the record of what the database was.
- `bench.py:506` — the six default sizes.
- `../EXPERIMENTS.md` §2.3 — required sizes, the widget, the corpus and its two new fields, the
  selectivity bar; §2.6 — corpus rebuild cost, disk, and the `/dev/shm` failure.
- `../analysis/measurement.md` §3 — the original corpus table, per-size on-disk cost, and the 1M
  load failure; §4 — the B4 arm and why `::date` is unsafe on real records; §5.5 — the qualifying-row
  counts §5's selectivity check reproduces; §11 — the cluster setting that was changed and reverted.
- `../FINDINGS.md` §4.2 — mean record size, the wire-size split, and the live re-read that gives
  8 216 kB at 10 k; §4.9 — the `synchronize_seqscans` 170× spread; §4.12 row 13 — the same 10 k size
  logged as a cosmetic defect against `measurement.md`.
- `gims-ledger/migrations/pg/0001_instances.sql:13-18` and `0002_instances_data_gin.sql:36-37` — the
  production table and index the corpus copies, read-only (§1).
- `../../../ANSWERS-FROM-OWNER.md` (repo root) — Q7, Q11, Q31, Q41.
