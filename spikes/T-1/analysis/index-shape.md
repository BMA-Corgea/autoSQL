# T-1 · Finding #3 — Index shape

**Question (FRAMING.md §4, finding #3, as restated in §2):** *What does the generated SQL
actually look like over JSONB arbitrary-key records, and what index does it need?* — measured
against `migrations/pg/0002_instances_data_gin.sql`'s `GIN (data jsonb_path_ops)`, **including
the honest answer if that index is the wrong shape.**

Stage `sp-investigate`. Seat: index shape. One seat, one question.

---

## 0. The answer, up front

**1. The existing `GIN (data jsonb_path_ops)` index does not help dashboard pushdown, and it is
not the reason.** Across 36 measured plans (9 compiled predicates × 4 index configurations,
§4.1) its name never appeared once — not even under `enable_seqscan = off`. Neither did a
`GIN (data jsonb_ops)`, nor four B-tree expression indexes on the exact keys being filtered. The
index is correct for the job it was built for and is measured doing it: `data @>
'{"actor":"goms"}'` in **1.3 ms of index scan reading 9 index buffers** (§5).

**2. The blocker is the emitted SQL, not the index shape.** Two independent structural facts, both
verified in the catalog (§3):

- Neither jsonb GIN operator class contains *any* comparison operator. `jsonb_path_ops` carries
  three operators (`@>`, `@?`, `@@`); `jsonb_ops` carries six. "The number at path X > 90" is not
  among them and does not exist as a GIN-indexable operator in PostgreSQL 16.
- **`to_jsonb()` is `STABLE`, not `IMMUTABLE`** — and `compile.py`'s representation contract
  (*"every compiled subexpression has SQL type `jsonb`"*, `compile.py:12-23`) puts it in every
  compiled expression. PostgreSQL therefore **refuses to create** any index whose expression or
  predicate contains compiled output at all: `ERROR: functions in index expression must be marked
  IMMUTABLE` (§6.1). This was not anticipated by the framing and is the single most consequential
  line in this document.

Isolating the two halves settles the blame: an index on `xpr.ord(…)` **is** creatable and **is**
used by the planner; the same expression wrapped in `to_jsonb(…)` is neither (§6.1, H2a/H2b/H2d).
The `xpr` runtime is not the problem.

**3. The index autoSQL requires is per-`(collection, key, extractor)` B-tree — and it is
unreachable until four compiler changes land.** DDL in §8.2, the compiler changes in §8.3
(drop the `to_jsonb` wrapper from leaf positions; emit a real operator at the root of a
comparison; constant-fold the context clock out of `today()`/`now()`; emit the JSON key as a
literal). Without those, even an index built on the character-exact compiled operand goes unused
(§6.2). With them, the cost is measured in §9: **0.74–2.10 µs/row and 2.6–6.5 MB per index**, and
for one real project (LIMS-System: 36 noun types, 111 `(noun type, field)` pairs) that
extrapolates to **111–222 indexes, ≈290–580 MB on a 100 MB table** (§9.3, stated as an
extrapolation — nothing above 12 indexes was measured).

**4. There is one shape that serves arbitrary keys with no per-key DDL, and it is already
installed.** `data @@ 'strict $."k" == <lit>'` is index-accelerated by the *existing*
`jsonb_path_ops` GIN — **12.5 ms vs the compiled form's 139.9 ms** — for any key, with no schema
change (§10). What it gives up: range predicates get no index condition (still a scan); lax mode
disagrees with `expr` on arrays and must be `strict … IS TRUE`; and it expresses only
`cmp(path, literal)`, which is **10 of the 130 fixture cases — 7.7% of the language** (§10.1c).

**5. Three correctness hazards found along the way, all silent, all measured.** (a) An index over
`xpr.ecma_num` — declared `IMMUTABLE`, actually GUC-dependent — makes the *same query* return
**0 rows with the index and 1 without it** (§6.4). (b) The "obvious" indexable rewrite
`(data->>'score')::float8 > 90` returns **5040 rows where the compiled `$.score > 90` returns
4807** — it coerces numeric strings and `expr`'s `>` does not (§7.2). (c) That same cast index
**rejects a legal `INSERT`** (`{"score":"n/a"}` → `ERROR: invalid input syntax for type double
precision`) and then cannot be rebuilt while such a row exists (§7.3). Each is the FRAMING §5
failure mode — a silently different answer — relocated from the compiler into the index.

Everything below is the evidence. Numbers, not adjectives.

---

## 1. Method and environment

### 1.1 Environment — verified, this session

| | |
| --- | --- |
| Postgres | `PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu`, container `glp-strong-db`, image `pgvector/pgvector:pg16` |
| Database | `autosql_spike` (the spike's own scratch db) |
| Probe table | `idxprobe` — **created by this seat**, owned by this seat. No other seat's table was touched. |
| Client | `psycopg2` 2.9.12 from `GIMS-Project/.venv/bin/python` (3.12.3) |
| Compiler | `spikes/T-1/proto/compile.py`, unmodified (mtime `2026-08-19 11:23`, predates this seat) |
| Runtime | `spikes/T-1/proto/runtime.sql`'s `xpr` schema, 21 functions, unmodified (mtime `11:20`) |

Planner settings, read from `pg_settings` this session (they matter for every plan quoted below,
so they are stated once rather than assumed):

```
shared_buffers                   16384 (8kB)  = 128 MB
work_mem                          4096 (kB)   = 4 MB
effective_cache_size            524288 (8kB)  = 4 GB
maintenance_work_mem             65536 (kB)   = 64 MB
max_parallel_workers_per_gather      2
seq_page_cost                        1
random_page_cost                     4
jit                                 on
extra_float_digits                   1
```

### 1.2 The probe table — real DDL, real record shape

DDL is `migrations/pg/0001_instances.sql:12-17` verbatim, with the table renamed so no other
seat's data is at risk:

```sql
CREATE TABLE idxprobe (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       JSONB NOT NULL,
    PRIMARY KEY (collection, key)
);
```

**The record shape is copied from real GIMS data, not invented.** Two collections:

- **`LedgerRecord` — 150,000 rows.** Shape and *key frequencies* measured this session against
  the real 17,087-row `LedgerRecord` collection in
  `GUTS/spine/L1-memory/gims-ledger/projects/guts-ledger/objects.db` (opened read-only,
  `mode=ro&immutable=1`). Measured frequencies, which the generator reproduces:

  | key | present in | key | present in |
  | --- | --- | --- | --- |
  | `record_id`, `kind`, `event_type`, `actor`, `created_at`, `human_required`, `summary`, `_runID`, `work_order` | 17087/17087 (100%) | `sprint_id`, `commit_sha` | 4049 (23.7%) |
  | `payload` (nested object) | 17086 (99.99%) | `correlation_id` | 2757 (16.1%) |
  | `risk_level` | 4822 (28.2%) | `responds_to` | 142 (0.83%) |
  | `proposal_slug` | 4208 (24.6%) | `revision` | 12 (0.07%) |
  | `ticket_id` | 4197 (24.6%) | | |
  | `run_id` | 4166 (24.4%) | | |

  Note `human_required` is the **string** `"false"`, not a JSON boolean, in the real data — that
  is reproduced too, because it is exactly the kind of thing that decides whether a cast-bearing
  expression index is even well-defined.

- **`Submission` — 50,000 rows.** Fields taken from the `Submission` noun type in
  `gims-ledger/projects/LIMS-System/noun_types.json` (`submission_id`, `received_date`,
  `due_date`, `priority`, `status`, `comments`), which is the same shape
  `api/dashboard/sources.py`'s **own docstring example** assumes
  (`"derive": {"days_left": "days_between(today(), $.due_date)"}`, `"where": "$.days_left < 7"`,
  `"sort": {"field": "days_left"}` — `sources.py:25-27`). Deliberate heterogeneity, all of it
  drawn from real GIMS behaviour:
  - `due_date` absent on 8% of rows (absent key → `expr` null → SQL NULL);
  - `priority` is a real JSON boolean on 96% of rows, the **string** `"true"`/`"false"` on 3%,
    and absent on 1%;
  - `score` is a JSON number on 95% of rows and a **numeric string** on 5%;
  - `"Sample Weight (g)"` — a key with spaces and parentheses, because
    `LIMS-System/noun_types.json` really does contain `"Sample Weight (g)"`, `"Did it land?"`,
    `"Level Of ViolencE"` and a 74-digit key. "Arbitrary keys" is not a hypothetical here.

Generator: `random.Random(20260819)`, deterministic. Loaded with `\copy` from TSV.

Measured size after `VACUUM ANALYZE`:

```
 heap_plus_toast | heap_only | total_with_indexes | indexes
-----------------+-----------+--------------------+---------
 100 MB          | 100 MB    | 109 MB             | 9288 kB

    relname    | reltuples | relpages
---------------+-----------+----------
 idxprobe      |    200000 |    12816
 idxprobe_pkey |    200000 |     1161

  collection  | count  | jsonb_bytes
--------------+--------+-------------
 LedgerRecord | 150000 | 71 MB
 Submission   |  50000 | 15 MB
```

200,000 rows / 12,816 heap pages — comfortably above the ≥100k the question asks for, and well
past the point where the planner's seq-scan-vs-index choice is a real decision rather than a
formality.

**One caveat stated up front:** the `PRIMARY KEY (collection, key)` B-tree already exists and its
leading column is `collection`. Every dashboard widget scopes to exactly one noun type, so the
honest baseline is *not* a full-table seq scan — it is a PK-prefix scan of one collection. §4
measures that, because scoring pushdown against a strawman full-table scan would inflate the
result.

### 1.3 The predicates — where each one comes from

No expression in this document was invented to make a point. Each is either **verbatim** from
`tests/fixtures/expr_vectors.json`, or a fixture *shape* with the probe table's own key names
substituted. Parsing is always the real `core.dashboard.expr.parse()`; compilation is always
`compile.py:compile_ast()`; neither was modified.

| id | expression | provenance | collection |
| --- | --- | --- | --- |
| W1 | `$.status == "open"` | fixture shape `$.s == "FAIL"` | `Submission` |
| W2 | `$.score > 90` | fixture shape `$.n < 7` | `Submission` |
| W3 | `$.score * 2 > 180` | fixture shapes `$.a * 2` + `$.n < 7`, composed | `Submission` |
| W4 | `days_between(today(), $.due_date) < 7` | **verbatim fixture case**, and the exact widget in `sources.py:25-26` | `Submission` |
| W5 | `$.status == "done" or $.status == "blocked"` | fixture shape `$.result == "FAIL" or $.result == "ERROR"` | `Submission` |
| W6 | `$.actor == "goms"` | the ledger's **own** `_INDEXABLE_FIELDS` field, written as an `expr` predicate | `LedgerRecord` |
| W7 | `lower($.status) == "open"` | fixture shape `lower($.s)` used as a predicate | `Submission` |
| W8 | `contains($.summary, "hold")` | fixture shape `contains($.s, "ell")` | `LedgerRecord` |
| W9 | `$.actor == "goms" and $.risk_level == "high"` | fixture shape `$.n > 0 and $.n < 10`, over two whitelisted ledger fields | `LedgerRecord` |
| D1 | `days_between(today(), $.due_date)` | the **derive** column `days_left` (`sources.py:25`) | `Submission` |
| S1 | `$.score` | the **sort** key (`sources.py:26` → `_sort_key(_field_value(row, "score"))`) | `Submission` |

W6 and W9 are there on purpose: they are the *one* access pattern
`0002_instances_data_gin.sql` was built for, exact-match equality on a whitelisted ledger field.
If the existing GIN index can ever help a compiled dashboard predicate, it will be on those two.

`ctx` is pinned to `{"now": "2026-08-19T12:00:00Z"}` so W4/D1 are reproducible; `xpr.now_ms`
reads `ctx->'now'` when present (`expr.py:449`), so no wall clock enters any plan.

**11 of 11 predicates compiled. 0 `Uncompilable`.** Coverage is finding #2's question, not this
seat's; it is recorded only so the reader knows nothing below is selection bias.

---

## 2. What the generated SQL actually looks like

This is the whole of finding #3's first half, so it is quoted in full rather than characterised.
`compile.py` emits **a single Postgres scalar expression of SQL type `jsonb`**, plus named bind
parameters. `sources.py:162` decides row membership with `truthy(evaluate(...))`, so the WHERE
clause is that expression wrapped in `xpr.truthy(...)`:

```sql
SELECT data FROM idxprobe WHERE collection = %(coll)s AND xpr.truthy( <compiled expression> )
```

### 2.1 The atom every predicate is built from

Every single field read — `$.status`, `$.score`, `$.due_date`, `$.actor` — compiles to exactly
one thing:

```sql
nullif((data -> (%(p0)s)::text), 'null'::jsonb)
```

Three properties of this atom decide the entire index question, and they are worth naming
separately:

- **`->`, not `->>`.** The result stays `jsonb`. It is never text and never a number.
  (This is `compile.py`'s representation contract, `compile.py:12-23`: *"Every compiled
  subexpression has SQL type `jsonb`"*.)
- **The key is a bind parameter (`%(p0)s`), not a literal.** The compiler parameterises the
  JSON key, not just the value — because the key comes from tenant expression text.
- **`nullif(..., 'null'::jsonb)`** collapses JSON `null` and absent-key to SQL NULL, which is the
  faithful thing to do (`expr.py:562-575` cannot distinguish them either) but adds a second
  function layer above `->`.

### 2.2 The compiled predicates, verbatim

Each block is the exact string `compile_ast()` returned, followed by the bind parameters, then
the same expression with parameters substituted for readability (`compile.py:render_for_display`,
which is display-only — the parameterised form is what was executed).

**W1 — `$.status == "open"`** · AST `('cmp', '==', ('field', [('key', 'status')]), ('str', 'open'))`
```sql
to_jsonb(nullif((data -> (%(p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text))
-- params {'p0': 'status', 'p1': 'open'}
-- rendered: to_jsonb(nullif((data -> ('status')::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb(('open')::text))
```

**W2 — `$.score > 90`** · AST `('cmp', '>', ('field', [('key', 'score')]), ('num', 90.0))`
```sql
to_jsonb(xpr.ord((%(p2)s)::text, nullif((data -> (%(p0)s)::text), 'null'::jsonb), to_jsonb((%(p1)s)::float8)))
-- params {'p0': 'score', 'p1': 90.0, 'p2': '>'}
```
Note what happened to the comparison: `>` is **not a SQL operator here**. It is a *string bind
parameter* `'>'` passed to `xpr.ord(op text, a jsonb, b jsonb) RETURNS boolean`
(`runtime.sql:160`). The planner sees a function call, not a comparison.

**W3 — `$.score * 2 > 180`**
```sql
to_jsonb(xpr.ord((%(p3)s)::text,
                 to_jsonb(xpr.num(nullif((data -> (%(p0)s)::text), 'null'::jsonb)) * xpr.num(to_jsonb((%(p1)s)::float8))),
                 to_jsonb((%(p2)s)::float8)))
-- params {'p0': 'score', 'p1': 2.0, 'p2': 180.0, 'p3': '>'}
```

**W4 — `days_between(today(), $.due_date) < 7`** (verbatim fixture case; the docstring's widget)
```sql
to_jsonb(xpr.ord((%(p2)s)::text,
                 to_jsonb((xpr.pdate_ms(nullif((data -> (%(p0)s)::text), 'null'::jsonb))
                           - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true))))
                          / 86400000.0::float8),
                 to_jsonb((%(p1)s)::float8)))
-- params {'p0': 'due_date', 'p1': 7.0, 'p2': '<'}
```

**W5 — `$.status == "done" or $.status == "blocked"`**
```sql
to_jsonb(xpr.truthy(to_jsonb(nullif((data -> (%(p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text)))
      OR xpr.truthy(to_jsonb(nullif((data -> (%(p2)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p3)s)::text))))
-- params {'p0': 'status', 'p1': 'done', 'p2': 'status', 'p3': 'blocked'}
```

**W6 — `$.actor == "goms"`** (the ledger's own containment field)
```sql
to_jsonb(nullif((data -> (%(p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text))
-- params {'p0': 'actor', 'p1': 'goms'}
```
Compare with what `PgRecordStore.list_records_where` emits for the *same* filter
(`api/storage_aws.py:1029-1039`): `... WHERE collection = %s AND data @> %s` with
`Jsonb({"actor": "goms"})`. **Same intent, structurally unrelated SQL.** One is a containment
operator with a GIN operator class; the other is `IS NOT DISTINCT FROM` over `to_jsonb(...)`.
This single line is why the existing index cannot be reused, and §4 measures it.

**W7 — `lower($.status) == "open"`**
```sql
to_jsonb(to_jsonb(lower(xpr.str(nullif((data -> (%(p0)s)::text), 'null'::jsonb)))) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text))
```

**W8 — `contains($.summary, "hold")`**
```sql
to_jsonb(xpr.contains(nullif((data -> (%(p0)s)::text), 'null'::jsonb), to_jsonb((%(p1)s)::text)))
```

**W9 — `$.actor == "goms" and $.risk_level == "high"`**
```sql
to_jsonb(xpr.truthy(to_jsonb(nullif((data -> (%(p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text)))
     AND xpr.truthy(to_jsonb(nullif((data -> (%(p2)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p3)s)::text))))
-- params {'p0': 'actor', 'p1': 'goms', 'p2': 'risk_level', 'p3': 'high'}
```

**D1 — derive `days_left`**
```sql
to_jsonb((xpr.pdate_ms(nullif((data -> (%(p0)s)::text), 'null'::jsonb))
          - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8)
```

**S1 — sort key `$.score`**
```sql
nullif((data -> (%(p0)s)::text), 'null'::jsonb)
```

### 2.3 The shape, stated once

Read those eleven blocks as a class and there are exactly **four** top-level node types the
planner can ever see at the root of a compiled dashboard predicate:

| root node | predicates | is there an index strategy for it? |
| --- | --- | --- |
| `xpr.ord(text, jsonb, jsonb)` | W2, W3, W4 | No — user function, no operator class |
| `xpr.contains(jsonb, jsonb)` | W8 | No — user function, no operator class |
| `<jsonb> IS NOT DISTINCT FROM <jsonb>` | W1, W6, W7 | No — `IS NOT DISTINCT FROM` is not an indexable operator in PG 16 |
| `xpr.truthy(bool OR/AND bool)` | W5, W9 | No — user function over booleans |

and in every case the whole thing is then wrapped in `xpr.truthy(...)` to become the WHERE
clause, so the *actual* root the planner sees is always `xpr.truthy(...)` — a single opaque
boolean function of `data`.

That is the finding in one sentence: **the compiler's output is, to the planner, one boolean
function call per row.** Not a comparison, not a containment, not a cast — a function. Sections
4–6 confirm empirically that no index shape changes this, and §7 states what does.

---

## 3. Before any plan: what the catalog already says is impossible

Two catalog facts bound the whole search space. Both were re-derived this session rather than
taken from the recon docs.

### 3.1 The GIN operator classes carry three and six operators, and none of them is a comparison

```sql
SELECT opc.opcname, amop.amopopr::regoperator AS operator
FROM pg_opclass opc
JOIN pg_am am ON am.oid = opc.opcmethod
JOIN pg_amop amop ON amop.amopfamily = opc.opcfamily
WHERE opc.opcname IN ('jsonb_path_ops','jsonb_ops') AND am.amname='gin'
ORDER BY opc.opcname, amop.amopstrategy;
```
```
    opcname     |      operator
----------------+--------------------
 jsonb_ops      | @>(jsonb,jsonb)
 jsonb_ops      | ?(jsonb,text)
 jsonb_ops      | ?|(jsonb,text[])
 jsonb_ops      | ?&(jsonb,text[])
 jsonb_ops      | @?(jsonb,jsonpath)
 jsonb_ops      | @@(jsonb,jsonpath)
 jsonb_path_ops | @>(jsonb,jsonb)
 jsonb_path_ops | @?(jsonb,jsonpath)
 jsonb_path_ops | @@(jsonb,jsonpath)
(9 rows)
```

`jsonb_path_ops`: **`@>`, `@?`, `@@`** — three. `jsonb_ops`: those three plus `?`, `?|`, `?&` —
six. Neither family contains `<`, `<=`, `>`, `>=`, or any operator meaning "the number at path X
compares to a literal". Not "the planner declines to use it": **the strategy does not exist.**

### 3.2 `to_jsonb()` is STABLE, not IMMUTABLE — and `compile.py` emits it everywhere

```
          fn          | volatility
----------------------+------------
 lower(text)          | IMMUTABLE
 upper(text)          | IMMUTABLE
 jsonb_typeof(jsonb)  | IMMUTABLE
 to_jsonb(anyelement) | STABLE
```

This is the single most consequential line in this document, and it was not anticipated by the
framing. `compile.py`'s representation contract — *"Every compiled subexpression has SQL type
`jsonb`"* (`compile.py:12-23`) — is implemented with `to_jsonb(...)`, which appears in **every one
of the eleven compiled predicates in §2.2**. PostgreSQL 16 refuses to build an index whose
expression or predicate contains a non-`IMMUTABLE` function. Therefore:

> **No compiled dashboard predicate, exactly as `compile.py` emits it, can appear in any index
> expression or any index predicate — regardless of how good the `xpr` functions are.**

Proven in §6.3 by isolating the two halves.

---

## 4. The plans: 4 index configurations × 9 predicates = 36 measured plans

Each configuration was built from scratch (all non-PK indexes dropped, indexes created,
`VACUUM ANALYZE`), then every predicate run under `EXPLAIN (ANALYZE, BUFFERS)` and separately
under `EXPLAIN (COSTS OFF)` with `enable_seqscan = off`.

| config | DDL | build time | index size |
| --- | --- | --- | --- |
| **A** | none (the `PRIMARY KEY (collection,key)` B-tree only) | — | 9288 kB (PK) |
| **B** | `CREATE INDEX ... USING GIN (data jsonb_path_ops)` — **the production index, `0002_instances_data_gin.sql`** | 2 341 ms | **50 MB** |
| **C** | `CREATE INDEX ... USING GIN (data jsonb_ops)` | 4 785 ms | **90 MB** |
| **D** | four B-tree expression indexes: `((data->>'score')::float8)`, `(data->>'status')`, `(data->>'actor')`, `(data->>'due_date')` | 84 + 95 + 107 + 83 = **369 ms** | 4416 + 1368 + 1376 + 1408 kB = **8.4 MB** |

### 4.1 The result table

`est` is the planner's row estimate, `act` the actual; `buffers` is `shared hit`; `exec` is
`Execution Time` from the `ANALYZE` run.

| pred | config | top node | est | act | removed by filter | buffers | exec ms | **index actually used** |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| W1 | A / B / C / D | Bitmap Heap Scan | 25190 / 24883 / 24853 / 24937 | 9985 | 40015 | 5088 / 3538 / 64 / 5088 | 136.5 / 139.9 / 146.6 / 134.4 | `idxprobe_pkey` |
| W2 | A / B / C / D | Bitmap Heap Scan | 16793 / 16589 / 16569 / 16624 | 4807 | 45193 | 5088 | 371.5 / 371.3 / 362.5 / 370.0 | `idxprobe_pkey` |
| W3 | A / B / C / D | Bitmap Heap Scan | 16793 / 16589 / 16569 / 16624 | 5040 | 44960 | 5088 | 1158.8 / 1164.2 / 1149.2 / 1198.7 | `idxprobe_pkey` |
| W4 | A / B / C / D | Bitmap Heap Scan | 16793 / 16589 / 16569 / 16624 | 16071 | 33929 | 5155 / 5088 / 5096 / 5088 | 3301.9 / 3285.0 / 3414.3 / 3285.4 | `idxprobe_pkey` |
| W5 | A / B / C / D | Bitmap Heap Scan | 16793 / 16589 / 16569 / 16624 | 20028 | 29972 | 5088 | 421.9 / 417.2 / 435.3 / 418.2 | `idxprobe_pkey` |
| W6 | A / B / C / D | Bitmap Heap Scan | 74810 / 75117 / 75147 / 75063 | 21308 | 128692 | 11530 / 4069 / 2651 / 11530 | 406.2 / 419.1 / 436.7 / 406.9 | `idxprobe_pkey` |
| W7 | A / B / C / D | Bitmap Heap Scan | 16793 / 16589 / 16569 / 16624 | 9985 | 40015 | 5088 | 285.3 / 288.2 / 295.1 / 290.9 | `idxprobe_pkey` |
| W8 | A / B / C / D | Bitmap Heap Scan | 49873 / 50078 / 50098 / 50042 | 21423 | 128577 | 11530+ | 870.6 / 883.2 / 880.1 / 878.2 | `idxprobe_pkey` |
| W9 | A / B / C / D | Bitmap Heap Scan | 49873 / 50078 / 50098 / 50042 | 1967 | 148033 | 11530 | 989.3 / 969.4 / 987.0 / 992.4 | `idxprobe_pkey` |

**36 plans. 36 identical shapes. In every one, the only index used is `idxprobe_pkey`, and it is
used only for `collection = ...`.** Adding a 50 MB GIN index, a 90 MB GIN index, or four B-tree
expression indexes changed *no* plan and *no* execution time beyond run-to-run noise (the largest
spread on any single predicate across the four configurations is 3.9%, on W4: 3285.0 → 3414.3 ms).

### 4.2 One plan, verbatim, so the shape is not taken on trust

Configuration **B** — the production `GIN (data jsonb_path_ops)` present — predicate **W2**
(`$.score > 90`). This is the exact text `EXPLAIN (ANALYZE, BUFFERS)` returned:

```
Bitmap Heap Scan on idxprobe  (cost=1533.82..34503.45 rows=16589 width=453) (actual time=2.454..371.056 rows=4807 loops=1)
  Recheck Cond: (collection = 'Submission'::text)
  Filter: xpr.truthy(to_jsonb(CASE WHEN ((NULLIF((data -> 'score'::text), 'null'::jsonb) IS NULL) OR (to_jsonb('90'::double precision) IS NULL)) THEN NULL::boolean WHEN ((jsonb_typeof(NULLIF((data -> 'score'::text), 'null'::jsonb)) = 'number'::text) AND (jsonb_typeof(to_jsonb('90'::double precision)) = 'number'::text)) THEN (CASE WHEN (NULLIF((data -> 'score'::text), 'null'::jsonb) IS NULL) THEN NULL::double precision WHEN (jsonb_typeof(NULLIF((data -> 'score'::text), 'null'::jsonb)) <> 'number'::text) THEN NULL::double precision WHEN (abs(((NULLIF((data -> 'score'::text), 'null'::jsonb) #>> '{}'::text[]))::numeric) > '1797693134862315700000...000'::numeric) THEN NULL::double precision ELSE ((NULLIF((data -> 'score'::text), 'null'::jsonb) #>> '{}'::text[]))::double precision END > CASE WHEN (to_jsonb('90'::double precision) IS NULL) THEN NULL::double precision WHEN (jsonb_typeof(to_jsonb('90'::double precision)) <> 'number'::text) THEN NULL::double precision WHEN (abs(((to_jsonb('90'::double precision) #>> '{}'::text[]))::numeric) > '1797693134862315700000...000'::numeric) THEN NULL::double precision ELSE ((to_jsonb('90'::double precision) #>> '{}'::text[]))::double precision END) WHEN ((jsonb_typeof(NULLIF((data -> 'score'::text), 'null'::jsonb)) = 'string'::text) AND (jsonb_typeof(to_jsonb('90'::double precision)) = 'string'::text)) THEN (((NULLIF((data -> 'score'::text), 'null'::jsonb) #>> '{}'::text[]))::text > (to_jsonb('90'::double precision) #>> '{}'::text[])) ELSE NULL::boolean END))
  Rows Removed by Filter: 45193
  Heap Blocks: exact=4839
  Buffers: shared hit=5088
  ->  Bitmap Index Scan on idxprobe_pkey  (cost=0.00..1529.67 rows=49767 width=0) (actual time=1.938..1.938 rows=50000 loops=1)
        Index Cond: (collection = 'Submission'::text)
        Buffers: shared hit=249
Planning Time: 0.201 ms
Execution Time: 371.287 ms
```
*(the 309-digit `DBL_MAX` guard literal from `runtime.sql:32` is elided as `...` in three places
for width; nothing else is changed.)*

Two things are worth reading off this plan directly:

- **`xpr.ord` is gone from the plan text.** `runtime.sql` declares it `LANGUAGE sql IMMUTABLE`, so
  PostgreSQL *inlined* its body (and `xpr.f8`'s inside it) into the filter at planning time. This
  matters because it is the best case for index matching — the planner is looking at the real
  expression tree, not an opaque call — and it still finds nothing to match. `xpr.truthy` was
  **not** inlined; it remains the root of the filter.
- **`Rows Removed by Filter: 45193`.** 50,000 rows are read from the heap and 45,193 are thrown
  away by evaluating that CASE tree per row. That per-row evaluation is the entire 371 ms; the
  index scan that found the 50,000 rows took 1.9 ms.

### 4.3 `enable_seqscan = off` — absence of strategy, not a cost decision

Every predicate was re-planned with `SET enable_seqscan = off`, which forces the planner off a
sequential scan whenever *any* legal index path exists. **All nine plans were unchanged** — same
`Bitmap Heap Scan` on `idxprobe_pkey`, same `Filter`. (This is why the plan already looks
index-ish: the PK's leading `collection` column is doing that work, and no seq scan was on the
table for these queries in the first place.) A cheaper way to say the same thing: `EXPLAIN`
never once printed the name `idxprobe_data_gin_path`, `idxprobe_data_gin_default`,
`idxprobe_score_f8`, `idxprobe_status_txt`, `idxprobe_actor_txt` or `idxprobe_due_txt` for any
compiled predicate, under any setting.

### 4.4 A second, quieter cost: the planner has no idea how selective the predicate is

Look at the `est` column. Every `xpr.truthy(...)` predicate is estimated at exactly **0.3333 ×
the collection's row count** (16 589 / 49 767 for `Submission`, 50 078 / 150 235 for
`LedgerRecord`), and every `IS NOT DISTINCT FROM` predicate at exactly **0.5 ×** (24 883 /
49 767, W1). These are PostgreSQL's hard-coded fallbacks for a boolean function and a
non-estimatable clause; **no column statistic is consulted, because the expression is not one
that `ANALYZE` collects statistics for.** The actual selectivities range from 1967/150235 =
**1.3%** (W9) to 20028/49767 = **40%** (W5). W9 is over-estimated by **25×**.

On a single-table `SELECT` this costs nothing — the plan is a filter either way. It becomes real
the moment a widget's `limit` or `sort` is pushed down, or the source is joined: the planner is
choosing sort methods and join orders from a number that is a constant, not a measurement. Worth
naming now because it does not show up in a single-widget benchmark.

---

## 5. What the existing `GIN (data jsonb_path_ops)` index *does* do — the fair control

"That index does not help" is only an honest finding if the index is shown working at the job it
was built for, on the same table, in the same session. It is:

```
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT data FROM idxprobe WHERE collection='LedgerRecord' AND data @> '{"actor":"goms"}'::jsonb;

 Bitmap Heap Scan on idxprobe (actual time=2.203..26.108 rows=21308 loops=1)
   Recheck Cond: (data @> '{"actor": "goms"}'::jsonb)
   Filter: (collection = 'LedgerRecord'::text)
   Heap Blocks: exact=9393
   Buffers: shared hit=2982 read=6420 written=41
   ->  Bitmap Index Scan on idxprobe_data_gin_path (actual time=1.338..1.338 rows=21308 loops=1)
         Index Cond: (data @> '{"actor": "goms"}'::jsonb)
         Buffers: shared hit=9
 Execution Time: 26.701 ms
```

That is `PgRecordStore.list_records_where`'s exact SQL shape (`api/storage_aws.py:1032-1036`:
`sql += " AND data @> %s"`), and the index answers it in **1.3 ms of index scan / 26.7 ms total,
reading 9 index buffers** to identify 21,308 matching rows out of 200,000. The index is correct,
it is well-chosen, and it works.

**Now compare it with W6 — the *same filter*, `$.actor == "goms"`, written as an `expr`
predicate and compiled:** `Bitmap Heap Scan` on the PK, GIN untouched, **419.1 ms**. Identical
result set (21,308 rows). Same data, same index, same intent, **15.7× slower**, purely because
the compiler emits `nullif(data->'actor','null') IS NOT DISTINCT FROM to_jsonb('goms')` instead
of `data @> '{"actor":"goms"}'`.

And `jsonb_path_ops`' documented limitation reproduces exactly:

```
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe WHERE collection='LedgerRecord' AND data ? 'revision';
 Gather
   Workers Planned: 2
   ->  Parallel Bitmap Heap Scan on idxprobe
         Recheck Cond: (collection = 'LedgerRecord'::text)
         Filter: (data ? 'revision'::text)
         ->  Bitmap Index Scan on idxprobe_pkey
               Index Cond: (collection = 'LedgerRecord'::text)
```
versus the same query with `GIN (data jsonb_ops)` instead:
```
 Bitmap Heap Scan on idxprobe (actual time=0.026..0.571 rows=119 loops=1)
   Recheck Cond: (data ? 'revision'::text)
   Filter: (collection = 'LedgerRecord'::text)
   ->  Bitmap Index Scan on idxprobe_data_gin_default (actual time=0.013..0.013 rows=119 loops=1)
         Index Cond: (data ? 'revision'::text)
 Execution Time: 0.585 ms
```
`jsonb_ops` answers key-existence in **0.585 ms**; `jsonb_path_ops` cannot, exactly as
`0002_instances_data_gin.sql:11-12` says. **But key-existence is not a dashboard predicate.**
`expr` has no key-existence operator — `$.missing` returns null, and `not $.x` on `{}` is
`truthy(null)` = `False` (fixture cases `$.missing`, `not $.x`). Switching operator class buys
`?`/`?|`/`?&`, costs **90 MB instead of 50 MB** and **3.52× write amplification instead of
1.94×** (§8), and changed **zero** of the nine compiled plans (§4.1, configuration C). It is not
the answer.

---

## 6. Why nothing matched — three independent causes, each isolated

### 6.1 Cause 1 — the wrapper: `to_jsonb()` is STABLE, so the DDL is refused outright

An index whose expression *is* the compiled predicate cannot be created at all:

```sql
CREATE INDEX idxprobe_w2_bool ON idxprobe
  ((xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb),
                                to_jsonb((90.0)::float8))))));
ERROR:  functions in index expression must be marked IMMUTABLE
```

Same for a *partial* index using it as the predicate:
```sql
CREATE INDEX idxprobe_w2_partial ON idxprobe (collection, key)
  WHERE xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb),
                                    to_jsonb((90.0)::float8))));
ERROR:  functions in index predicate must be marked IMMUTABLE
```

**The blame is `to_jsonb`, not `xpr`** — isolated by building the same expression with and
without the wrapper:

| test | expression | result |
| --- | --- | --- |
| H2a | `((xpr.ord('>'::text, nullif(data->'score','null'::jsonb), '90'::jsonb)))` | **index CREATED** |
| H2b | `((to_jsonb(xpr.ord(...))))` | `ERROR: functions in index expression must be marked IMMUTABLE` |
| H2c | `((xpr.truthy(to_jsonb(xpr.ord(...)))))` | `ERROR: ... must be marked IMMUTABLE` |

and the index from H2a **is used** when the predicate is written without the wrapper:
```
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe WHERE collection='Submission'
  AND xpr.ord(('>')::text, nullif((data -> 'score'::text), 'null'::jsonb), '90'::jsonb);

 Bitmap Heap Scan on idxprobe
   Recheck Cond: (CASE WHEN (NULLIF((data -> 'score'::text), 'null'::jsonb) IS NULL) THEN NULL::boolean WHEN ...
   ->  BitmapAnd
         ->  Bitmap Index Scan on h2a
               Index Cond: (CASE WHEN (NULLIF((data -> 'score'::text), 'null'::jsonb) IS NULL) THEN ...
         ->  Bitmap Index Scan on idxprobe_pkey
               Index Cond: (collection = 'Submission'::text)
```

So the `xpr` runtime library is **not** the obstacle. `compile.py`'s "everything is jsonb"
representation contract is. That is a fixable prototype decision, not a law of Postgres — but it
is load-bearing, and no index work is possible until it changes.

### 6.2 Cause 2 — the operand: an index on the exact compiled field-read is still not matched

Even setting `to_jsonb` aside, an index built on the *precise* text of the compiled field read —

```sql
CREATE INDEX idxprobe_score_operand ON idxprobe ((nullif((data -> 'score'::text), 'null'::jsonb)));
```

— is **not** used for the compiled W2 predicate, even with `enable_seqscan = off`:

```
 Bitmap Heap Scan on idxprobe
   Recheck Cond: (collection = 'Submission'::text)
   Filter: xpr.truthy(to_jsonb(CASE WHEN ...
   ->  Bitmap Index Scan on idxprobe_pkey
         Index Cond: (collection = 'Submission'::text)
```

An expression index is usable only when the query contains an *indexable operator clause* whose
left side is the indexed expression. `xpr.truthy(to_jsonb(CASE ...))` has no operator at its root
at all — it is a bare boolean function — so there is nothing to match against
`idxprobe_score_operand`'s `jsonb_ops` B-tree strategies. The index exists, it contains exactly
the right values, and it is unreachable.

### 6.3 Cause 3 — the clock: `xpr.now_ms` is STABLE, so `derive` columns can never be indexed

| test | DDL attempted | result |
| --- | --- | --- |
| T7a | `((xpr.ecma_num(xpr.f8(data -> 'score'))))` | **created** — see §6.4, this is a hazard, not a win |
| T7b | `((xpr.now_ms('{}'::jsonb)))` | `ERROR: functions in index expression must be marked IMMUTABLE` |
| T7c | the compiled **D1** derive column (`days_left`) in full | `ERROR: functions in index expression must be marked IMMUTABLE` |
| T7d | `((xpr.pdate_ms(nullif(data -> 'due_date', 'null'::jsonb))))` — D1 with the clock term removed | **created** |

`today()`/`now()` reach `xpr.now_ms(ctx)`, declared `STABLE` (`runtime.sql:345-346`) — correctly,
since it falls back to `now()`. So **any** dashboard expression containing `today()` or `now()`
is permanently unindexable as written, which is the single most common dashboard predicate there
is: `sources.py`'s own docstring example is `days_between(today(), $.due_date)`.

T7d shows the shape that *would* work: hoist the clock to a query-time constant so the indexable
part is `xpr.pdate_ms(data->'due_date')` and the comparison is against a computed bound. That is a
compiler change (constant-folding the context clock out of the row-dependent expression), not an
index change.

### 6.4 The hazard the framing asked about: an index built on a lying `IMMUTABLE`

The question named `xpr.ecma_num` specifically — declared `IMMUTABLE`, but it reads
`float8`'s text output, which depends on the `extra_float_digits` GUC (`runtime.sql:15-18`
records this openly). **It is not immutable. Measured:**

```
SET extra_float_digits = 1;    -- the PG12+ default
SELECT xpr.ecma_num(0.1::float8 + 0.2::float8);   ->  0.30000000000000004

SET extra_float_digits = -3;
SELECT xpr.ecma_num(0.1::float8 + 0.2::float8);   ->  0.3
```

Postgres accepts an index on it anyway, because `IMMUTABLE` is a *promise the author makes*, not
a property the server verifies. The consequence is a **silently wrong answer**:

```sql
-- one row inserted with {"score": 0.30000000000000004}
SET extra_float_digits = 1;
CREATE INDEX idxprobe_ecma ON idxprobe ((xpr.ecma_num(xpr.f8(data -> 'score'))));
ANALYZE idxprobe;
SET extra_float_digits = -3;
```
Same query, twice, in the same session, differing only in whether the planner is allowed to use
the index:

```
-- planner free to use the index
 Aggregate
   ->  Index Scan using idxprobe_ecma on idxprobe
         Index Cond: (xpr.ecma_num(CASE WHEN ...) = '0.3'::text)

 answer_with_index
-------------------
                 0

-- SET enable_indexscan=off; enable_bitmapscan=off; enable_indexonlyscan=off;
 Aggregate
   ->  Seq Scan on idxprobe
         Filter: (xpr.ecma_num(CASE WHEN ...) = '0.3'::text)

 answer_without_index
----------------------
                    1
```

**0 rows with the index, 1 row without it, from the same query on the same data.** No error, no
warning. This is reachable through the real language: `string($.score)` compiles to
`xpr.ecma_num(xpr.f8(...))`, and `string($.n)` is a fixture case.

Measured against FRAMING §5 — *"Any compiler output that turns a null into a number, or a raise
into a value, is a defect of the highest severity"* — this is the same class of failure moved one
layer down: **an index that turns a matching row into a non-matching one, silently.** It is a
hazard of the *index*, not of the compiler as it stands today (§6.1 means no such index can be
built from `compile.py`'s current output). It becomes live the moment §6.1 is fixed.

For completeness, the two other `IMMUTABLE`-declared `xpr` functions that survived DDL creation
were probed for the same lie and **did not exhibit it** under the GUCs that could plausibly
affect them:

```
SET TimeZone='UTC';                 xpr.pdate_ms('"2026-07-02"') = 1782950400000  fmt_date_ms(...) = 2025-07-02
SET TimeZone='Pacific/Kiritimati';  xpr.pdate_ms('"2026-07-02"') = 1782950400000  fmt_date_ms(...) = 2025-07-02
SET lc_time='C';                    xpr.fmt_date_ms(1751414400000,false) = 2025-07-02T00:00:00Z
```
Stated honestly: those two are **not falsified**, which is not the same as proven. Both call
functions the catalog marks `STABLE` inside bodies declared `IMMUTABLE` —
`to_char(timestamp,text)` is `STABLE`, and `date_part(text,timestamptz)` (reached via
`extract(epoch from ... at time zone 'UTC')`) is `STABLE` — so both carry the same *structural*
risk as `ecma_num`; they simply use those functions in ways whose output happens not to vary.
`float8out` is `IMMUTABLE`; the `extra_float_digits` dependency in `ecma_num` comes from the
`float8 → text` cast path, not from `float8out`'s declaration.

---

## 7. What *does* work — and what it costs in correctness

### 7.1 The contrast, on the same index, in the same session

`idxprobe_score_f8` = `CREATE INDEX ... ON idxprobe (((data->>'score')::float8))`. Two queries
that a reader would call "the same predicate":

**7.1a — hand-written, index-shaped:**
```
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission' AND (data->>'score')::float8 > 90;

 Bitmap Heap Scan on idxprobe  (cost=1651.11..5417.41 rows=1275 width=451) (actual time=2.615..4.166 rows=5040 loops=1)
   Recheck Cond: ((((data ->> 'score'::text))::double precision > '90'::double precision) AND (collection = 'Submission'::text))
   Heap Blocks: exact=2245
   Buffers: shared hit=2494 read=17
   ->  BitmapAnd  (cost=1651.11..1651.11 rows=1275 width=0) (actual time=2.438..2.439 rows=0 loops=1)
         ->  Bitmap Index Scan on idxprobe_score_f8  (cost=0.00..94.20 rows=5038 width=0) (actual time=0.355..0.355 rows=5040 loops=1)
               Index Cond: (((data ->> 'score'::text))::double precision > '90'::double precision)
               Buffers: shared read=17
         ->  Bitmap Index Scan on idxprobe_pkey  (cost=0.00..1556.02 rows=50613 width=0) (actual time=2.035..2.035 rows=50000 loops=1)
               Index Cond: (collection = 'Submission'::text)
 Planning Time: 0.120 ms
 Execution Time: 4.294 ms
```

**7.1b — the compiled `$.score > 90`, same session, same index present:**
```
 Bitmap Heap Scan on idxprobe  (cost=1560.24..34872.50 rows=16871 width=451) (actual time=2.448..382.018 rows=4807 loops=1)
   Recheck Cond: (collection = 'Submission'::text)
   Filter: xpr.truthy(to_jsonb(CASE WHEN ...))
   Rows Removed by Filter: 45193
   Buffers: shared hit=5088
   ->  Bitmap Index Scan on idxprobe_pkey (actual time=1.932..1.932 rows=50000 loops=1)
         Index Cond: (collection = 'Submission'::text)
 Execution Time: 382.247 ms
```

**4.294 ms vs 382.247 ms — 89×.** Also `Buffers: 2494+17` vs `5088`, and `rows=1275` estimated
vs `rows=16871` estimated (the first is derived from statistics on the indexed expression; the
second is the 0.3333 constant).

*Reproduction, and the honest spread on that ratio:* re-run later in the session as client-side
`count(*)` rather than `EXPLAIN ANALYZE` of `SELECT data`, and with another seat's queries
running concurrently on the same PostgreSQL instance (§12.2), the same pair measured
**18.7 / 21.8 ms** against **378.3 / 395.8 ms** — the same two plans, the same 5040 / 4807 row
counts, a **19×** ratio rather than 89×. The ratio is cache- and contention-sensitive; the plan
shapes and the row counts are not. Quote the plans, not the ratio.

### 7.2 …but they are not the same predicate. 5040 ≠ 4807.

Read the row counts again: the hand-written form returns **5040** rows, the compiled form
**4807**. The "obvious" index-friendly rewrite is **not semantically equivalent to the language**:

```sql
SELECT (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND (data->>'score')::float8 > 90)                        AS handwritten_indexable,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND xpr.truthy(to_jsonb(xpr.ord('>'::text, nullif((data->'score'::text),'null'::jsonb),
                                          to_jsonb(90.0::float8))))) AS compiled_expr_gt,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND jsonb_typeof(data->'score') = 'string')               AS score_is_a_string;

 handwritten_indexable | compiled_expr_gt | score_is_a_string
-----------------------+------------------+-------------------
                  5040 |             4807 |              2409
```

The 233-row gap is exactly the numeric **strings**. `expr`'s `>` does not coerce across types —
`xpr.ord` compares number-to-number or string-to-string and yields NULL otherwise, mirroring
`expr.py`'s `_compare`; the fixture pins this with `$.n < "x"` on `{"n": 5}` → null. `::float8`
coerces. The compiler is right and the rewrite is wrong, and the difference is **a silently
different answer**, not an error. (Confirming that this is a coercion difference and not an
artefact: `$.score * 2 > 180`, W3, returns **5040** — arithmetic *does* coerce numeric strings in
`expr` via `xpr.num`, so the arithmetic predicate agrees with the cast and the comparison
predicate does not.)

### 7.3 …and the index rejects writes the language accepts

A record whose `score` is a non-numeric string is legal GIMS data — the real `LedgerRecord`
table stores `human_required` as the string `"false"`, and `noun_types.json` field types are
advisory. Measured sequence, each step a separate statement:

```
S1  CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8));      -- OK (clean data)
S2  INSERT INTO idxprobe VALUES ('Submission','SUB-NAN','{"score":"n/a","status":"open"}');
    ERROR:  invalid input syntax for type double precision: "n/a"
S3  SELECT count(*) FROM idxprobe WHERE key='SUB-NAN';   ->  0      -- the write did not happen
S4  DROP INDEX idxprobe_score_f8;
    INSERT INTO idxprobe VALUES ('Submission','SUB-NAN','{"score":"n/a","status":"open"}');   -- OK
    SELECT count(*) FROM idxprobe WHERE key='SUB-NAN';   ->  1      -- the index was the cause
S5  CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8));
    ERROR:  invalid input syntax for type double precision: "n/a"   -- and now it cannot be rebuilt
S6  -- the compiled predicate over that same row:
    SELECT count(*) FROM idxprobe WHERE collection='Submission'
      AND xpr.truthy(to_jsonb(xpr.ord('>'::text, nullif((data->'score'::text),'null'::jsonb),
                                      to_jsonb(90.0::float8))));   ->  4807   -- no error. expr is total.
```

A read-side optimisation turned **one heterogeneous value into a write failure** — and, once such
a row exists, into an index that cannot be built. This is FRAMING §6's "anything touching writes,
invariants" boundary being crossed by an index, and it is the strongest argument against the
naive cast-bearing expression index.

The fix is a `NULL`-on-failure wrapper, which is exactly what `xpr` already is. Measured:

```sql
CREATE FUNCTION safe_f8(t text) RETURNS float8 LANGUAGE plpgsql IMMUTABLE AS
$$ BEGIN RETURN t::float8; EXCEPTION WHEN others THEN RETURN NULL; END $$;
CREATE INDEX idxprobe_score_safe ON idxprobe ((safe_f8(data->>'score')));
INSERT INTO idxprobe VALUES ('Submission','SUB-NAN','{"score":"n/a","status":"open"}');  -- OK
SELECT count(*) FROM idxprobe WHERE collection='Submission' AND safe_f8(data->>'score') > 90;  -- 5040, no error
```
The write is accepted and the query does not raise. It still returns **5040**, not 4807 — §7.2's
coercion divergence is untouched by making the cast safe. Two separate defects; fixing one does
not fix the other.

### 7.4 Sorting: the one place an index *is* reachable from compiled output today

`S1` (the sort key) compiles to a bare `nullif((data -> 'score'), 'null'::jsonb)` with **no
`to_jsonb` wrapper**, so §6.1 does not apply and `idxprobe_score_operand` is usable. Measured,
`ORDER BY … LIMIT 50` over the 50,000-row `Submission` collection:

| ORDER BY | plan | exec ms |
| --- | --- | --- |
| `nullif(data->'score','null') ASC` | `Index Scan using idxprobe_score_operand` | **0.065** |
| `nullif(data->'score','null') DESC` | `Index Scan Backward using idxprobe_score_operand`, `Filter: collection='Submission'`, `Rows Removed by Filter: 150000` | **27.918** |
| `nullif(data->'score','null') DESC NULLS LAST` | `Gather Merge` → `Sort` (`top-N heapsort`) → `Parallel Bitmap Heap Scan` | **15.564** |

Three lessons in three rows: an index-backed sort is **429× faster** than the sorted scan when
everything lines up; it is **worse than sorting** when the index is not collection-scoped and the
scan has to walk 150,000 `LedgerRecord` entries to find 50 `Submission` ones; and it is not used
*at all* when the `NULLS` placement does not match the index's (`DESC` implies `NULLS FIRST`).
Any real DDL must therefore be `(collection, <expr>)`, not `(<expr>)`, and must match the
`NULLS` order the pushdown emits.

**But the ordering itself is wrong.** `sources.py:99-119`'s `_sort_key` gives
`bool < number < string < other < None-last`; `jsonb`'s B-tree ordering is
`Null < String < Number < Boolean < Array < Object`. Measured on one mixed column:

```
sources.py _sort_key ascending : [false, true, 2.5, 5, "Zebra", "apple", [1,2], {"a":1}, null]
jsonb btree ascending          : [null, "Zebra", "apple", 2.5, 5, false, true, [1,2], {"a":1}]
SAME ORDER? False
```

So the fastest available pushdown is also, on a mixed-type column, a **different answer**. On a
column that is uniformly numeric the two agree; nothing in GIMS enforces that (§1.2: `score` is a
string on 5% of rows by construction, modelled on `human_required`'s real behaviour).

---

## 8. The index shape autoSQL actually requires, as DDL

Stated as the question asks: DDL, with the conditions each line depends on.

### 8.1 Keep, unchanged — it is not autoSQL's index and it is doing its job

```sql
-- migrations/pg/0002_instances_data_gin.sql -- UNCHANGED. Serves list_records_where's
-- `data @> '{"actor":"goms"}'` at 1.3 ms index-scan / 26.7 ms total on 200k rows (S5).
-- Contributes nothing to dashboard pushdown; also costs it nothing.
CREATE INDEX IF NOT EXISTS idx_instances_data_gin ON instances USING GIN (data jsonb_path_ops);
```

### 8.2 The shape dashboard pushdown needs — per (collection, key, cast)

```sql
-- One per key a widget filters or sorts on. `collection` FIRST so the index is
-- scoped to the noun type (7.4 measured a 429x swing on exactly this point).
CREATE INDEX idx_instances_num_score
    ON instances (collection, (xpr_safe_num(data -> 'score')));

CREATE INDEX idx_instances_txt_status
    ON instances (collection, (xpr_safe_str(data -> 'status')));

CREATE INDEX idx_instances_ms_due_date
    ON instances (collection, (xpr_pdate_ms(data -> 'due_date')));
```

Four non-negotiable properties, each earned by a measurement above:

1. **`collection` is the leading column** (§7.4 — 0.065 ms vs 27.918 ms).
2. **The extractor is total** — a `NULL`-on-failure function, never a bare `::float8` cast
   (§7.3 — the bare cast rejects a legal `INSERT` and then cannot be rebuilt). `xpr.num`,
   `xpr.str` and `xpr.pdate_ms` already have this property; they are the right extractors.
3. **The extractor must be genuinely `IMMUTABLE`, not merely declared so** (§6.4 — an index over
   `xpr.ecma_num` returns 0 where a scan returns 1). Before any of this DDL ships, each `xpr`
   function used in an index expression needs its body audited for GUC and locale reads;
   `xpr.ecma_num` **fails that audit today** and must not appear in an index.
4. **The compiler must emit the indexed expression verbatim** — which today it does not, because
   of the `to_jsonb` wrapper (§6.1) and because the *key* is a bind parameter rather than a
   literal. Both are `compile.py` changes; no DDL fixes them.

### 8.3 What has to change in the compiler before 8.2 is reachable at all

Not DDL, but it belongs in this finding because the DDL is inert without it:

- **Drop the `to_jsonb` wrapper from indexable leaf positions.** `to_jsonb` is `STABLE` (§3.2);
  while it wraps every subexpression, no index expression and no index predicate containing
  compiled output can even be created (§6.1). H2a proves the `xpr` layer underneath is fine.
- **Emit an indexable operator at the root of a comparison.** `xpr.ord('>', a, b)` must become
  `xpr_safe_num(a) > <bound>` — a real `>` on a real type — or no B-tree strategy can ever match
  (§6.2, where an index on the exact operand was still unusable).
- **Constant-fold the context clock.** `today()`/`now()` reach `STABLE xpr.now_ms`, which makes
  the whole expression unindexable (§6.3, T7b/T7c) — and it is the most common dashboard
  predicate there is. T7d shows the row-dependent remainder *is* indexable once the clock is a
  query-time constant.
- **Emit the JSON key as a literal, not a bind parameter,** in any position that is meant to
  match an index expression.

Every one of those is a change to a throwaway prototype, so none is a cost estimate for the real
system — but together they are the difference between "the index doesn't help" and "an index
could help", and they are the honest content of finding #3.

---

## 9. The cost of that shape

### 9.1 Size and build time, measured on this 200,000-row / 100 MB table

| index | build | size | bytes/row |
| --- | ---: | ---: | ---: |
| `PRIMARY KEY (collection,key)` (already present) | — | 9 288 kB | 47.6 |
| `GIN (data jsonb_path_ops)` | 2 341 ms | **50 MB** | 263 |
| `GIN (data jsonb_ops)` | 4 785 ms | **90 MB** | 471 |
| B-tree `((data->>'score')::float8)` | 84 ms | 4 416 kB | 22.6 |
| B-tree `((data->>'status'))` | 95 ms | 1 368 kB | 7.0 |
| B-tree `((data->>'actor'))` | 107 ms | 1 376 kB | 7.1 |
| B-tree `((data->>'due_date'))` | 83 ms | 1 408 kB | 7.2 |
| BRIN `((data->>'score')::float8)` | — | **24 kB** | 0.12 |

### 9.2 Write amplification, measured

One `COPY` of the same 20,000 records under each configuration (a single round trip, so client
latency is not in the number; `VACUUM ANALYZE` between runs):

| configuration | index MB | COPY 20k | µs/row | **vs. no index** |
| --- | ---: | ---: | ---: | ---: |
| none (PK only) | 0.0 | 225 ms | 11.2 | 1.00× |
| `GIN (data jsonb_path_ops)` (default `fastupdate=on`) | 58.0 | 436 ms | 21.8 | **1.94×** |
| `GIN (data jsonb_path_ops) WITH (fastupdate=off)` | 62.6 | 1 189 ms | 59.4 | **5.29×** |
| `GIN (data jsonb_ops)` | 93.7 | 792 ms | 39.6 | **3.52×** |
| 1 B-tree expression index | 6.5 | 266 ms | 13.3 | 1.18× |
| 4 B-tree expression indexes | 13.3 | 302 ms | 15.1 | 1.34× |
| 12 B-tree expression indexes | 31.7 | 402 ms | 20.1 | **1.79×** |

Read those two GIN rows together: `fastupdate=on` (the default) does not make GIN cheap to
write, it **defers** the cost to the pending-list flush — the honest steady-state figure for the
production index is closer to 5.29× than 1.94×.

The per-key B-tree shape is **cheap per index and sub-linear over the range measured**. Marginal
cost, computed from the three B-tree rows against the 11.2 µs/row baseline:

| indexes | µs/row | marginal µs/row **per index** | MB | MB per index |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.3 | 2.10 | 6.5 | 6.50 |
| 4 | 15.1 | 0.98 | 13.3 | 3.33 |
| 12 | 20.1 | 0.74 | 31.7 | 2.64 |

**0.74–2.10 µs/row and 2.6–6.5 MB per index**, both improving with count (the first index pays
fixed per-row overhead the later ones share). Twelve of them cost less to write than one
`jsonb_path_ops` GIN with `fastupdate=off` (20.1 vs 59.4 µs/row). The problem with the per-key
shape is not the cost of one index. It is how many you need.

### 9.3 Per-key explosion — the real number, from the real projects on this machine

| project (`gims-ledger/projects/*/noun_types.json`) | noun types | distinct declared field names |
| --- | ---: | ---: |
| LIMS-System | 36 | **98** |
| guts | 7 | 48 |
| guts-ledger | 2 | 22 |
| guts-code | 2 | 21 |
| DurationDemo | 1 | 4 |
| RunlogTest | 2 | 1 |
| Sterility | 1 | 0 |
| **union across all seven** | 51 | **150** |

LIMS-System alone has **111 `(noun type, field)` pairs**. Since §8.2's DDL is per
`(collection, key)` — and a key may need more than one extractor if widgets both compare it
numerically and sort it as text — LIMS-System's ceiling is **111 to ~222 indexes on one table**.
At the 12-index marginal rate measured in §9.2 (2.64 MB and 0.74 µs/row per index) that
extrapolates to **≈290–580 MB of index on a 100 MB table** and **≈8× to ≈15× write
amplification** — but the extrapolation is stated as an extrapolation: **nothing above 12 indexes
was measured**, and the marginal rate was still falling at 12, so the size figure is likelier to
hold than the write figure.

And that is still the *optimistic* count, because it only covers declared noun fields.
`derive` columns are arbitrary expressions authored by a tenant at dashboard-edit time
(`sources.py:25` — `{"days_left": "days_between(today(), $.due_date)"}`), and are not in
`noun_types.json` at all. There is no finite enumeration of them, and §6.3 shows the most common
one cannot be indexed regardless.

---

## 10. Is there a shape that serves arbitrary keys without knowing them in advance?

**Yes — exactly one, and it is already installed.** `jsonb_path_ops`' operator family carries
`@?` and `@@` (§3.1), and PostgreSQL 16's GIN jsonpath support extracts index conditions from
*some* jsonpath expressions. Measured on the production index, `Submission` collection, 50,000
rows:

| predicate | plan | exec ms |
| --- | --- | ---: |
| `data @@ '$."status" == "open"'` | `BitmapAnd` → **`Bitmap Index Scan on idxprobe_data_gin_path`** + pkey | **7.640** |
| `data @@ 'strict $."status" == "open"'` | `BitmapAnd` → **`Bitmap Index Scan on idxprobe_data_gin_path`** + pkey | **12.504** |
| `data @? '$."score" ? (@ > 90)'` | pkey bitmap + `Filter: (data @? ...)` — **index not used** | 21.773 |
| compiled `$.status == "open"` (W1) | pkey bitmap + `xpr.truthy` filter | 139.9 |
| compiled `$.score > 90` (W2) | pkey bitmap + `xpr.truthy` filter | 371.3 |

Verbatim, the one that matters:
```
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT data FROM idxprobe WHERE collection='Submission' AND data @@ 'strict $."status" == "open"';

 Bitmap Heap Scan on idxprobe (actual time=4.490..12.121 rows=9985 loops=1)
   Recheck Cond: ((data @@ 'strict ($."status" == "open")'::jsonpath) AND (collection = 'Submission'::text))
   Heap Blocks: exact=2687
   Buffers: shared hit=2943
   ->  BitmapAnd (actual time=4.213..4.214 rows=0 loops=1)
         ->  Bitmap Index Scan on idxprobe_data_gin_path (actual time=0.908..0.909 rows=9985 loops=1)
               Index Cond: (data @@ 'strict ($."status" == "open")'::jsonpath)
               Buffers: shared hit=7
         ->  Bitmap Index Scan on idxprobe_pkey (actual time=3.232..3.232 rows=50002 loops=1)
               Index Cond: (collection = 'Submission'::text)
 Execution Time: 12.504 ms
```

This is the answer to "a shape that serves arbitrary keys without knowing them in advance":
**one table-wide index, any key, no DDL per key, and it already exists in production.** For
equality it is **11× faster** than the compiled form (12.5 ms vs 139.9 ms) and reads **7 index
buffers**.

### 10.1 What it gives up — three things, all measured, none negotiable

**(a) Range predicates get nothing.** `@?` with a filter (`? (@ > 90)`) is in the operator family
but the planner extracts no index condition from it — the plan above shows it as a plain
`Filter`. It is still *fast* (21.8 ms vs the compiled 371.3 ms, because it is native C rather
than a per-row CASE tree over `xpr`), but it is a **full scan of the collection**, not an index
lookup. Swapping to `jsonb_ops` did not change this (24.9 ms, still `Filter`).

**(b) `lax` mode — the default — disagrees with `expr` on arrays.** Eleven adversarial records
run through the real `expr.evaluate()` and through Postgres jsonpath side by side:

| expression | record | `expr` | jsonpath **lax** | jsonpath **strict** |
| --- | --- | --- | --- | --- |
| `$.tags == "a"` | `{"tags":["a","b"]}` | `False` | **`True`** ✗ | `False` ✓ |
| `$.arr > 1` | `{"arr":[0,5]}` | `False` | **`True`** ✗ | `False` ✓ |
| `$.score > 90` | `{"score":"95.0"}` | `False` | `False` ✓ | `False` ✓ |
| `$.score > 90` | `{"score":95.0}` | `True` | `True` ✓ | `True` ✓ |
| `$.score > 90` | `{}` | `False` | `False` ✓ | `False` ✓ |
| `$.b == 1` | `{"b":true}` | `False` | `False` ✓ | `False` ✓ |
| `$.n == "2"` | `{"n":2}` | `False` | `False` ✓ | `False` ✓ |
| `$.n < "x"` | `{"n":5}` | `False` | `False` ✓ | `False` ✓ |
| `$.payload.machine == "goms"` | `{"payload":{"machine":"goms"}}` | `True` | `True` ✓ | `True` ✓ |
| `$.status == "open"` | `{"status":null}` | `False` | `False` ✓ | `False` ✓ |
| `$.score >= 90` | `{"score":90}` | `True` | `True` ✓ | `True` ✓ |
| | | | **9/11** | **11/11** |

Lax mode auto-unwraps arrays and matches any element; `expr` compares the list as one value.
`strict` fixes both, keeps the index (12.504 ms above), and must be paired with `IS TRUE` because
`strict` returns SQL NULL rather than false on a structural error
(`'{"tags":["a","b"]}'::jsonb @@ 'strict $."tags" == "a"'` → NULL, not `f`).

**Honesty bound on that table:** these are **11 cases this seat chose to be adversarial**, not
the 130-case fixture. 11/11 is a *hypothesis worth testing properly*, not a proven equivalence,
and testing it properly is the conformance harness's job, not this seat's.

**(c) It covers 7.7% of the language.** The only shape Postgres jsonpath can express as an
index-accelerable predicate is `cmp(literal-path, literal)`. Classifying every AST in
`expr_vectors.json` by that criterion:

```
 114   87.7%  OTHER (no jsonpath equivalent)
  10    7.7%  cmp(path, literal)
   6    4.6%  bare path
 130   total
```

Ten of 130. No arithmetic, no `days_between`/`date_add`/`today`, no `coalesce`, no `if`, no
`concat`/`lower`/`upper`, no `sum`/`avg`/`count`, no boolean composition of two different keys.
That is the price of "serves arbitrary keys without knowing them in advance": **you stop using
the compiler for those predicates and use a second, much smaller language instead.**

### 10.2 The shape that follows from all of the above

A hybrid, and it is the only shape the measurements support:

```
For each widget predicate:
  1. If the AST is cmp(literal-path, literal) with an equality operator
        -> emit  data @@ 'strict $."k" == <lit>'  IS TRUE   -- index-accelerated, no DDL, any key
  2. Else if a (collection, key, extractor) index exists for the key
        -> emit  the operator form of 8.2                    -- index-accelerated, DDL per key
  3. Else
        -> emit the compiled xpr predicate as a filter        -- correct, collection-scan speed
  4. Else (today(), now(), or Uncompilable)
        -> fall back to in-memory, REPORTED (FRAMING section 5)
```

Note what rule 3 is: **a correct answer at scan speed.** §4 measured that honestly — 136 ms to
3.3 s for one widget over a 50,000-row collection, which is not a disaster and not a win.
Whether it beats the in-memory path is finding #4's question, not this one; it is named here only
so rule 3 is not mistaken for a failure mode.

### 10.3 Two shapes that do not work, tested rather than assumed

- **BRIN over the extracted key.** 24 kB — 200× smaller than any B-tree — but not used, even with
  `enable_seqscan = off`: `Bitmap Heap Scan on idxprobe / Bitmap Index Scan on idxprobe_pkey /
  Filter: (((data ->> 'score'::text))::double precision > '99.9')`, 27.067 ms, `Rows Removed by
  Filter: 49937`. BRIN prunes only when the indexed value correlates with physical row order;
  records arriving by `(collection, key)` have no such correlation with an arbitrary JSON field.
- **`GIN (data jsonb_ops)` instead of `jsonb_path_ops`.** Buys `?`/`?|`/`?&` (0.585 ms
  key-existence, §5) — which `expr` cannot express — at 90 MB vs 50 MB and 3.52× vs 1.94× write
  amplification, and changed **zero** of the nine compiled plans (§4.1, configuration C).

---

## 11. The verdict on `migrations/pg/0002_instances_data_gin.sql`

Stated plainly, as the question requires.

**The existing `GIN (data jsonb_path_ops)` index does not help dashboard pushdown. It is the
right index, correctly chosen, for a different access pattern.**

The evidence, in the order it was collected:

1. **Catalog:** `jsonb_path_ops` carries exactly three operators — `@>`, `@?`, `@@` — and no
   comparison operator exists for "the number at path X > literal" in either jsonb GIN operator
   class (§3.1).
2. **Plans:** across **36 measured plans** (9 compiled dashboard predicates × 4 index
   configurations), the index name `idxprobe_data_gin_path` **never once appeared** in a plan for
   a compiled predicate — including under `enable_seqscan = off`, which forces the planner off a
   sequential scan wherever any legal index path exists (§4.1, §4.3).
3. **No cost either:** its presence changed no plan and no execution time beyond noise
   (largest spread across configurations on any predicate: 3.9%). It is not in the way.
4. **It works at its own job:** `data @> '{"actor":"goms"}'` — `list_records_where`'s exact SQL —
   is a **1.3 ms index scan reading 9 index buffers** to find 21,308 of 200,000 rows (§5).
5. **The same filter through the compiler is 15.7× slower** and does not touch the index, purely
   because the compiler emits `IS NOT DISTINCT FROM` over `to_jsonb(...)` rather than `@>` (§5).

So finding #3's restated question — *"does the existing index serve dashboard pushdown at all,
and if not, what index does autoSQL actually require?"* — answers:

> **No, and the reason is not the index.** The reason is that `compile.py`'s output contains no
> indexable operator at any level: every field read is `nullif(data -> $key, 'null')`, every
> comparison is a function call, and the whole thing is wrapped in `to_jsonb()`, which is
> `STABLE` and therefore cannot appear in an index expression or predicate at all. Changing the
> operator class, adding key-existence support, or pre-building B-tree expression indexes on the
> right keys changes **nothing**, because there is nothing in the query for any of them to match.
> **The index shape is not the blocker. The emitted SQL shape is.** §8.3 lists the four compiler
> changes that would make an index reachable, and §8.2 the DDL that would then be worth building.

And the framing's own prediction — *"jsonb_path_ops deliberately does NOT support key-existence
(`?`/`?|`/`?&`)… Dashboard pushdown is range, comparison, arithmetic and computed predicates over
arbitrary keys — a different access pattern"* — is **correct in its conclusion and incomplete in
its reasoning**. Key-existence is a red herring: `expr` has no key-existence operator, `jsonb_ops`
supplies it at 90 MB and 3.52× write amplification, and it changed zero plans (§4.1 config C,
§5). The operative limitation is the absence of a comparison operator in *both* GIN classes
(§3.1), compounded by `to_jsonb`'s volatility (§3.2). Recording that distinction because it
changes what a fix would look like.

---

## 12. Limits of this finding — what it does not establish

### 12.1 Scope

- **This is one seat's question.** Whether pushdown beats the in-memory path end-to-end is
  finding #4's measurement, not this document's. §4's absolute timings (136 ms – 3.3 s per widget
  over a 50,000-row collection) are reported so the plans are readable, **not** as a comparison
  against `MAX_SCAN`-bounded in-memory evaluation.
- **11 predicates, not 130.** The predicates in §1.3 are fixture-derived but hand-picked to span
  the access patterns an index could plausibly serve. A predicate whose plan differs from these
  36 would be a surprise, but it was not searched for exhaustively.
- **§10.1(b)'s 11 adversarial cases are not the fixture.** 11/11 `strict`-mode agreement is a
  hypothesis, not an equivalence proof.
- **One table shape, one Postgres.** `PostgreSQL 16.14`, `C.UTF-8` cluster locale, `shared_buffers`
  128 MB, `work_mem` 4 MB, `jit=on`. A cloud RDS with different memory or a different collation
  could change absolute costs; it cannot change §3.1's catalog facts or §6.1's DDL refusal.

### 12.2 Measurement contamination, disclosed

Another seat's work (the measurement finding, `measure_instances_*` tables) was **running
concurrently on the same PostgreSQL container** during part of this seat's timing runs —
confirmed via `pg_stat_activity` (an active query `SELECT d.data FROM (SELECT (data ||
jsonb_build_object('days…` at the time of writing) and `pg_stat_user_tables` (those tables loaded
17:50–17:51 UTC, this seat's sweeps ran after). **Absolute millisecond figures in this document
therefore carry unknown contention.** What is *not* affected: every plan shape, every row count,
every buffer count, every catalog result, every DDL success/failure, and every correctness
divergence (5040 vs 4807, 0 vs 1, the sort ordering). Those are the load-bearing claims. Where a
timing ratio is quoted it is given with its spread (§7.1).

### 12.3 Not tested

- `CREATE INDEX CONCURRENTLY` cost, and the `indisvalid` failure mode
  `0002_instances_data_gin.sql:29-33` warns about — operational, not access-pattern.
- Partitioning `instances` by `collection`, which would make the leading-column argument in §8.2
  moot. Out of this seat's scope; worth a line in `sp_synth`.
- `jsonb_to_record` / generated columns / a materialised sidecar table per widget — all require
  the key set to be known in advance, so they land in §9.3's explosion, but none was measured.
- Multi-key composite expression indexes (e.g. `(collection, (data->>'status'), ((data->>'score')::float8))`)
  for a conjunctive predicate — §6.1 makes them unreachable from current compiler output, so they
  were not built.
- Whether `xpr.contains` / `xpr.length` / the aggregate functions have their own indexable
  rewrites. `contains` maps to `LIKE '%…%'`, which is `pg_trgm` GIN territory — a real option,
  entirely untested here.

### 12.4 Reproducibility and read-only compliance

- **Deterministic inputs.** Row generator seeded `random.Random(20260819)`; predicates compiled
  from the real `expr.parse()`; `ctx.now` pinned to `2026-08-19T12:00:00Z`, so no wall clock
  enters any compiled SQL.
- **Artifacts** (throwaway, per FRAMING §3) — every number in this document is reproducible from
  these, all under `spikes/T-1/proto/`, all prefixed `idxshape_` so they cannot be mistaken for
  the compiler:

  | file | produces |
  | --- | --- |
  | `idxshape_gen_rows.py` | the 200,000 GIMS-shaped rows (§1.2) |
  | `idxshape_mkpreds.py` → `idxshape_preds.json` | the compiled predicates of §2.2 |
  | `idxshape_explain.py` → `idxshape_plans.json` | the 36 plans of §4 |
  | `idxshape_exprindex.sql` | §6.1–6.3, §7.1, §7.4 (T1–T7) |
  | `idxshape_hazard.sql` | §3.2, §6.1 isolation, §7.2 (H1–H5) |
  | `idxshape_immutable.sql` | §6.4 (I1–I4) |
  | `idxshape_jsonpath.sql` | §5, §10 (J0–J5) |
  | `idxshape_jsonpath_agree.py` | §10.1(b) |
  | `idxshape_fixture_subset.py` | §10.1(c) |
  | `idxshape_sort_semantics.py` | §7.4's ordering divergence |
  | `idxshape_writecost.py` | §9.2 |

  None of them is imported by anything; per FRAMING §3 they are throwaway by contract.
- **Nothing in `spikes/T-1/proto/` was modified.** `compile.py` mtime `2026-08-19 11:23:10`,
  `runtime.sql` mtime `2026-08-19 11:20:29` — both predate this seat's work (which began ~11:55).
  The `xpr` schema was used exactly as installed.
- **Both GIMS trees are unchanged.** `GIMS-Project` HEAD `995cc59`, `gims-ledger` HEAD `7b7a049`
  — identical to the values FRAMING §7 recorded. `core/dashboard/expr.py` mtime `2026-07-02
  14:15:55` and `tests/fixtures/expr_vectors.json` mtime `2026-07-02 14:03:21`, i.e. untouched.
  `gims-ledger`'s SQLite record databases were opened **read-only and immutable**
  (`sqlite3.connect('file:…?mode=ro&immutable=1', uri=True)`) purely to measure real key
  frequencies (§1.2); nothing was written.
- **Database hygiene.** All work was in the spike's own `autosql_spike` scratch database, in a
  table named `idxprobe` created by this seat. `glp_strong` was never opened. The `instances`
  table (another seat's) and the `measure_instances_*` tables (another seat's) were **read for
  `pg_stat` accounting only and never written, altered or dropped.** `idxprobe` was left at
  **200,000 rows with only `idxprobe_pkey`** — every experimental index created during this work
  was dropped, and the temporary `SUB-NAN` / `SUB-EFD` / `WRITETEST` rows were deleted (verified:
  `SELECT count(*) FROM idxprobe` → 200000; `SELECT indexname FROM pg_indexes WHERE
  tablename='idxprobe'` → `idxprobe_pkey` only).
