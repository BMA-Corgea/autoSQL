# T-1 recon — storage substrate

**Question:** Establish the storage substrate the generated SQL would run against, in the
`gims-ledger` tree.

**Tree:** `/home/corgea/Desktop/Coding Projects/GUTS/spine/L1-memory/gims-ledger` @ `7b7a049`
(per FRAMING.md §2, C1: this is the tree that actually has the Postgres layer; `GIMS-Project`
does not). All paths below are relative to this tree unless stated otherwise.

**Postgres used for empirical verification:** docker container `glp-strong-db`,
`pgvector/pgvector:pg16`, confirmed `PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1)` via
`docker exec glp-strong-db psql -U glp_owner -d autosql_spike -tAc "select version()"`.
Scratch database `autosql_spike` created for this recon (`CREATE DATABASE autosql_spike`,
run against `postgres` db as `glp_owner`) — `glp_strong`'s own contents were not touched.

---

## 1. The DDL: `instances` / `instances_archive`

Exact text of `migrations/pg/0001_instances.sql`:

```sql
CREATE TABLE IF NOT EXISTS instances (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       JSONB NOT NULL,
    PRIMARY KEY (collection, key)
);

CREATE TABLE IF NOT EXISTS instances_archive (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       JSONB NOT NULL,
    PRIMARY KEY (collection, key)
);
```
Source: `migrations/pg/0001_instances.sql:12-23`.

- **Columns:** `collection TEXT NOT NULL`, `key TEXT NOT NULL`, `data JSONB NOT NULL`. Three
  columns, no more — no `created_at`, no `updated_at`, no numeric surrogate id.
- **`data` is `JSONB`, not `json`.** Stated directly in the DDL (`data JSONB NOT NULL`,
  `migrations/pg/0001_instances.sql:15` and `:22`).
- **Primary key:** composite `PRIMARY KEY (collection, key)` — one row per (collection, key)
  pair, table-wide across every part-of-speech collection in the project (comment,
  `migrations/pg/0001_instances.sql:2-5`: "ONE table per database holds every part-of-speech
  instance across all collections").
- **`instances_archive`** is byte-identical in shape to `instances` — same three columns, same
  composite PK — described as "the hard-archive sibling (Phase 6/R17) — the cloud analogue of
  the local `archive.db`" (`migrations/pg/0001_instances.sql:7-9`). `api/storage_aws.py`'s
  `PgRecordStore` is pointed at one or the other via its `table=` constructor argument
  (`api/storage_aws.py:541`, `self.table = table`; default `table: str = "instances"`), and the
  comment is explicit that this value is "internal constants, never user input"
  (`migrations/pg/0001_instances.sql:10`).
- **No other columns, no `CHECK` constraints, no foreign keys** in either table. No secondary
  key beyond the composite PK; there is no separate `id` column at all.
- **The runtime path builds the same DDL a second way.** `api/storage_aws.py:33-40` carries an
  inline `_INSTANCES_DDL` template (`CREATE TABLE IF NOT EXISTS {table} (collection TEXT NOT
  NULL, key TEXT NOT NULL, data JSONB NOT NULL, PRIMARY KEY (collection, key))`) used by
  `PgRecordStore._ensure_schema` (`api/storage_aws.py:568`) so a store is self-sufficient
  without requiring the migration runner to have been run first — it is schema-identical to
  `0001_instances.sql`, just re-derived inline rather than shared as one source of truth.

## 2. The index: `migrations/pg/0002_instances_data_gin.sql`

Exact text:

```sql
CREATE INDEX IF NOT EXISTS idx_instances_data_gin
    ON instances USING GIN (data jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_instances_archive_data_gin
    ON instances_archive USING GIN (data jsonb_path_ops);
```
Source: `migrations/pg/0002_instances_data_gin.sql:34-38`.

One `GIN` index per table, both on the whole `data` column, both using the `jsonb_path_ops`
operator class (not the default `jsonb_ops`).

### Why `jsonb_path_ops`, in the migration's own words

`migrations/pg/0002_instances_data_gin.sql:1-13`:

> `GET /ledger/{project}/records` ANDs exact-match filters (`proposal_slug` / `ticket_id` /
> `sprint_id` / `actor` / `kind`) and pushes them into SQL via `store.list_records_where`. On
> Postgres that is a single JSONB containment predicate (`data @> '{"actor":"goms"}'`), which is
> exactly what a GIN index over the `data` column can answer.
>
> `jsonb_path_ops` rather than the default `jsonb_ops`: it indexes whole key/value paths instead
> of every key and every value separately, so it is smaller and faster for the ONE operator we
> use (`@>`). It deliberately does NOT support key-existence (`?`/`?|`/`?&`); no query in this
> codebase needs those on `instances`.

So the choice is explicitly scoped to one operator, `@>`, driven by one call site
(`list_records_where`, containment-only), and the tradeoff (index size/speed for `@>` vs. losing
`?`/`?|`/`?&`) is made consciously, not incidentally.

### What `jsonb_path_ops` cannot answer — verified empirically, not just quoted

Built the exact production schema in the `autosql_spike` scratch database (both DDL statements
above, applied verbatim), loaded 50,000 synthetic rows with varied `actor` and a numeric `score`
field, ran `ANALYZE`, then tested four predicate shapes with `EXPLAIN (COSTS OFF)`:

| # | Predicate | Plan | Index used? |
|---|---|---|---|
| 1 | `data @> '{"actor":"actor_7"}'` (selective value) | `Bitmap Heap Scan on instances` / `Bitmap Index Scan on idx_instances_data_gin` | **Yes** |
| 2 | `data ? 'nonexistent_key_xyz'` (key existence) | `Seq Scan on instances` | **No** |
| 3 | `(data->>'score')::numeric > 49900` (range) | `Seq Scan on instances` | **No** |
| 4 | `(data->>'score')::numeric * 2 > 80000` (arithmetic) | `Seq Scan on instances` | **No** |

Raw output for row 1 (index-backed containment, confirming the migration's own claim):
```
 Bitmap Heap Scan on instances
   Recheck Cond: (data @> '{"actor": "actor_7"}'::jsonb)
   ->  Bitmap Index Scan on idx_instances_data_gin
         Index Cond: (data @> '{"actor": "actor_7"}'::jsonb)
```

Rows 2–4 stayed sequential scans even with `SET enable_seqscan = off`, which forces the planner
away from a seq scan whenever *any* legal index path exists — proving these are not cost-based
misses but genuine absence of an applicable index strategy:
```
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT * FROM instances WHERE data ? 'nonexistent_key_xyz';
 Seq Scan on instances
   Filter: (data ? 'nonexistent_key_xyz'::text)

EXPLAIN (COSTS OFF) SELECT * FROM instances WHERE (data->>'score')::numeric > 49900;
 Seq Scan on instances
   Filter: (((data ->> 'score'::text))::numeric > '49900'::numeric)
```
(commands and output captured directly from `docker exec glp-strong-db psql -U glp_owner -d
autosql_spike`, this session).

This matches the catalog directly. Querying `pg_opclass`/`pg_amop` for the operators each
opclass's operator family actually supports:

```sql
SELECT opcname, amopopr::regoperator
FROM pg_opclass opc JOIN pg_amop amop ON amop.amopfamily = opc.opcfamily
WHERE opc.opcname IN ('jsonb_path_ops','jsonb_ops') ORDER BY opcname, amopopr;
```
```
 jsonb_ops      | =(jsonb,jsonb)
 jsonb_ops      | <(jsonb,jsonb)
 jsonb_ops      | >(jsonb,jsonb)
 jsonb_ops      | <=(jsonb,jsonb)
 jsonb_ops      | >=(jsonb,jsonb)
 jsonb_ops      | @>(jsonb,jsonb)
 jsonb_ops      | ?(jsonb,text)
 jsonb_ops      | ?|(jsonb,text[])
 jsonb_ops      | ?&(jsonb,text[])
 jsonb_ops      | @?(jsonb,jsonpath)
 jsonb_ops      | @@(jsonb,jsonpath)
 jsonb_path_ops | @>(jsonb,jsonb)
 jsonb_path_ops | @?(jsonb,jsonpath)
 jsonb_path_ops | @@(jsonb,jsonpath)
```
(same session, `autosql_spike`). `jsonb_path_ops`'s operator family carries exactly **three**
operators: `@>`, `@?` (jsonpath exists), `@@` (jsonpath match). It has no strategy at all for `?`
/ `?|` / `?&`, and — crucially for this spike — **none of the `<`/`>`/`<=`/`>=` comparison
operators either**: those exist only in `jsonb_ops`'s family, and even there they order whole
`jsonb` values (Postgres's documented `jsonb` btree/GIN total ordering: object > array > booleans
> numbers > strings, compared element-by-element — this is a type/structure-aware ordering of
composite JSON documents, not numeric comparison of one scalar field extracted from many
documents). Neither opclass has an operator that means "the numeric value at path `$.score` is
greater than X" — that predicate does not exist as a GIN-indexable operator in Postgres 16 at all
for either `jsonb_ops` or `jsonb_path_ops`. It has to be built either as a per-path BTREE
expression index (verified below) or answered without an index.

### What would help instead — verified empirically

A plain BTREE expression index on the *specific, known* path used in a query answers the range
predicate directly:

```sql
CREATE INDEX idx_instances_score_btree ON instances (((data->>'score')::numeric));
```
```
EXPLAIN (COSTS OFF) SELECT * FROM instances WHERE (data->>'score')::numeric > 49900;
 Index Scan using idx_instances_score_btree on instances
   Index Cond: (((data ->> 'score'::text))::numeric > '49900'::numeric)
```
(same session; index dropped again immediately after, `DROP INDEX
idx_instances_score_btree`, per the "never touch `glp_strong`'s contents beyond a scratch db"
rule — this was on the scratch db and was a create+drop within this recon).

This confirms the standard Postgres mechanism (`CREATE INDEX ... ON tbl ((expr))`, an expression
index — PostgreSQL 16 "Indexes on Expressions") *does* answer a range predicate over a JSONB
field — but it must be built **per extracted path, per assumed scalar type**, ahead of time. It
is not a property of a single table-wide GIN index the way containment is.

## 3. How `list_records_where` builds its predicate today

### Postgres (`api/storage_aws.py:1010-1046`, class `PgRecordStore`)

```python
def list_records_where(self, collection: str, equals: Dict[str, Any]) -> List[Dict[str, Any]]:
    from psycopg.types.json import Jsonb  # lazy
    from core.storage.sql import _INDEXABLE_FIELDS  # THE shared whitelist — never a second copy

    filters = {f: v for f, v in equals.items() if v is not None and f in _INDEXABLE_FIELDS}
    sql = f"SELECT data FROM {self.table} WHERE collection = %s"
    params: List[Any] = [collection]
    if filters:
        sql += " AND data @> %s"
        params.append(Jsonb(filters))
    ...
```
(`api/storage_aws.py:1029-1039`)

- **Predicate shape: containment (`@>`), not per-field equality.** All whitelisted equality
  filters supplied by the caller are collapsed into **one** JSONB object (`filters`) and pushed
  as a single `data @> %s` clause — not a chain of `data->>'f' = %s` clauses. The docstring
  states the reason directly: "It is what a GIN index can answer — `->>` equality would need one
  btree expression index per field, i.e. per-field DDL at query time" (`api/storage_aws.py:1024-
  1026`).
- **Field whitelist:** `core.storage.sql._INDEXABLE_FIELDS` (imported, "never a second copy",
  `api/storage_aws.py:1017`) — `frozenset({"proposal_slug", "ticket_id", "sprint_id", "actor",
  "kind", "correlation_id", "run_id", "repo_id", "destination", "proposal", "status"})`
  (`core/storage/sql.py:252-259`). Anything outside this fixed set is **silently dropped** before
  reaching SQL (`filters = {f: v for f, v in equals.items() if v is not None and f in
  _INDEXABLE_FIELDS}`, `api/storage_aws.py:1030`) — never interpolated, never even
  parameterized.
- **Parameterization:** fully parameterized, no string interpolation of values or field names
  into SQL text on the Postgres path. `collection` is bound as `%s` (`api/storage_aws.py:1031`);
  the entire filter dict is bound as ONE parameter via `psycopg.types.json.Jsonb(filters)`
  (`api/storage_aws.py:1035-1036`) — psycopg serializes the whole dict to a single `jsonb`
  literal bound parameter, so there is exactly one placeholder for however many fields survived
  the whitelist, not one placeholder per field.
- **Equality-with-type semantics, not string equality**, called out explicitly: "both compare
  the JSON value *with its type*, so a numeric `ticket_id` in the record does not match the
  string `"123"` on either backend" (`api/storage_aws.py:1027-1028`) — this is `@>`'s scalar
  containment behavior (a JSONB scalar contains another JSONB scalar only on exact
  type-and-value match), which the docstring says was chosen specifically to match SQLite's
  `json_extract(...) = ?` "on the edge case that matters."

### SQLite twin, for contrast (`core/storage/sql.py:518-533`, class `SqlRecordStore`)

```python
def list_records_where(self, collection: str, equals: Dict[str, Any]) -> List[Dict[str, Any]]:
    filters = {f: v for f, v in equals.items() if v is not None and f in _INDEXABLE_FIELDS}
    self.ensure_field_indexes(collection, list(filters.keys()))
    clauses = ["collection = ?"]
    params: List[Any] = [collection]
    for field, value in filters.items():
        clauses.append(f"json_extract(data, '$.{field}') = ?")
        params.append(value)
    sql = "SELECT data FROM instances WHERE " + " AND ".join(clauses)
    ...
```
(`core/storage/sql.py:518-533`)

Here the predicate *is* a chain of per-field equality clauses (`json_extract(data,
'$.{field}') = ?`, one clause and one bound value per surviving field), backed by one
`json_extract` BTREE index per whitelisted field (`core/storage/sql.py:501-515`,
`ensure_field_indexes`) — because SQLite has no JSONB GIN-style containment index, so per-path
BTREE expression indexes are the only option there. Same whitelist, same silent-drop semantics,
same fixed-field constraint — different SQL shape because the underlying index technology
differs. This SQLite shape is structurally closer to what a dashboard-pushdown compiler would
need (equality per known field, index per known field) than the Postgres containment shape is —
except the whole premise of dashboard pushdown (per FRAMING.md) is that the keys are **not**
known ahead of time the way `_INDEXABLE_FIELDS` is a fixed, small, hand-maintained set.

### The RAG pushdown profile, for scale/measurement context

`core/storage/sql.py:224-247` documents a *measured* profile for one of these whitelisted
fields (`repo_id`, the pgvector RAG partition key), on the live `guts-code` project (6,333
vectors, 384-dim, 65.3 MB of JSON): loading and filtering in Python cost `826ms load + 26ms
cosine = 852ms` (all 6,333 records loaded, 76% discarded after deserialization); pushing the
`repo_id` filter down cost `210ms` (only the 1,509 matching records loaded) — a 4.1x speedup,
identical top-8 results (`core/storage/sql.py:246-247`). This profile is for an **equality**
filter on a **known, whitelisted** field pushed as `@>` containment — it is not a measurement of
range/arithmetic pushdown, and the same comment notes pgvector itself was rejected as the
bottleneck-fix because 97% of the cost was JSON deserialization, not the vector math
(`core/storage/sql.py:248-250`) — i.e. the profile's lesson is "avoid loading rows you don't
need," which is exactly the lesson dashboard pushdown is trying to apply too, just over a
different, unbounded key space.

## 4. Direct answer to the framing question

**Does `GIN (data jsonb_path_ops)` help dashboard pushdown's access pattern (range comparisons,
arithmetic, computed predicates over arbitrary keys) at all?**

**No — plainly, and for two independent reasons, both verified above:**

1. **Operator mismatch.** `jsonb_path_ops`'s operator family supports exactly three operators —
   `@>`, `@?`, `@@` (verified against `pg_opclass`/`pg_amop` in §2) — none of which express "the
   numeric value at path X compares as `>`/`<`/`>=`/`<=` to a literal" or any arithmetic
   expression over that value. Postgres 16 has **no** GIN operator, in either `jsonb_ops` or
   `jsonb_path_ops`, that means numeric range comparison on an extracted scalar. Even forcing the
   planner away from sequential scans (`SET enable_seqscan = off`) left range and arithmetic
   predicates as seq scans (§2) — this is not a cost decision the planner is making against the
   index, it is the absence of an applicable index strategy for that operator at all.
2. **Key mismatch.** Even where an operator class *could* help (a hypothetical BTREE expression
   index answering range predicates, verified working in §2), it has to be built **per path,
   per assumed scalar type, ahead of time** (`CREATE INDEX ... ON instances (((data->>'k')::
   numeric))`) — the same constraint the SQLite twin already lives under via
   `_INDEXABLE_FIELDS`/`ensure_field_indexes` (§3). Dashboard pushdown's own scope, per this
   spike's framing, is arbitrary keys chosen by whatever `derive`/`where`/`sort` expression a
   dashboard widget contains — not a fixed, small, hand-maintained field set. There is no set of
   pre-built expression indexes that covers "any key the AST might reference," short of indexing
   every possible key with every possible cast, which is not a real option.

**What would actually serve this access pattern:**

- **Nothing built ahead of time can, in general** — because the keys are not known ahead of
  time. This is the honest ceiling: pushdown for an *arbitrary* AST over an *arbitrary* JSONB key
  is fundamentally a sequential-scan-with-filter workload on this schema unless the key set is
  bounded in advance.
- **Per-path BTREE expression indexes** (`CREATE INDEX ... ON instances (((data->>'k')::type))`,
  verified in §2 to produce an `Index Scan` for range predicates) are the correct tool **only**
  for keys known and stable enough to enumerate — i.e. exactly the same shape as
  `_INDEXABLE_FIELDS` today, extended from equality to range/arithmetic-capable types. This does
  not generalize to "any key in the AST," only to a maintained whitelist, which is a narrower
  promise than dashboard pushdown as framed.
- **`jsonb_ops` GIN** (the default operator class, vs. `jsonb_path_ops`) adds `?`/`?|`/`?&`
  key-existence support over `jsonb_path_ops`, which is irrelevant to range/arithmetic — it does
  not add any comparison operator either (§2's `pg_amop` listing shows `jsonb_ops`'s `<`/`>`/
  `<=`/`>=` operate on whole-`jsonb`-value ordering, not on a numeric scalar extracted from a
  path — not the same thing as "salary > 50000"). Switching operator classes does not close this
  gap.
- **A generalized alternative that exists in Postgres but was not tested here** (out of scope for
  this question, flagged as a gap): expression indexes over `jsonb_to_record`/computed
  generated columns per-widget, or GiST/BRIN alternatives — none of these remove the fundamental
  constraint that an index must be defined over a **specific, named** expression, and dashboard
  `where`/`derive` expressions are not fixed at schema-design time.

**Bottom line:** `idx_instances_data_gin` (`jsonb_path_ops`) is correctly scoped to the one job
it was built for — exact-match containment on a small, fixed field whitelist for
`GET /ledger/{project}/records` — and it does not serve, and structurally cannot serve, the
dashboard pushdown access pattern this spike is investigating. Any SQL the T-1 compiler emits for
range/arithmetic/computed predicates over dashboard-arbitrary keys will run as a sequential scan
against `instances` under the schema as it exists today, unless a caller pre-builds the same kind
of narrow per-path expression index the whitelist model already uses — and even that only covers
whichever paths get indexed, never "any key an AST can name."

## 5. Gaps / what this recon did not attempt

- Did not measure actual scan latency of the seq-scan-backed predicates in §2 against a
  20,000-row table sized to `MAX_SCAN` (`api/dashboard/sources.py:61` per FRAMING.md) — that is
  the Measurement finding (#4) owned by a different seat per FRAMING.md §4, not this question.
- Did not test `jsonb_to_tsvector`/GIN-on-expression or BRIN indexes as alternates; flagged above
  as untested rather than claimed to not help.
- Did not examine `core/storage/ports.py`'s `RecordStore` interface contract beyond what
  `list_records_where`'s signature implies — out of scope for "storage substrate."
- `GIMS_PG_AUTO_MIGRATE` / deploy-time index-build mechanics (`migrations/README.md`,
  `api/storage_aws.py:883-975` `ensure_gin_index`/`_gin_index_missing`) were read and cited for
  completeness on how the GIN index actually gets built in production, but are operational
  detail, not load-bearing for the pushdown-access-pattern answer.
