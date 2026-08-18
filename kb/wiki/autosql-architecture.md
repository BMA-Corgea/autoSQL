# autoSQL — architecture

The durable record of the design worked out with the operator on 2026-08-18, during
onboarding. Present tense; supersede rather than delete.

## What autoSQL is

An **in-database query plane** for GIMS: an interactive UI where a user picks *what* data
and *how* to view, window and transform it, and autoSQL compiles that choice into SQL that
executes **inside the database**. Data viewing, window creation and transformation all stop
being Python post-passes.

It lives in its own repo (granularity), and integrates into GIMS.

## The problem, stated precisely

GIMS reshapes data by **materializing it out of the store and transforming it in Python**.
Two modules do this, independently, and both are bottlenecked by the same boundary:

| Module | Where the round-trip happens | Its own words |
| --- | --- | --- |
| Prepositional phrases | `IoSpec.extra.db_inputs` → endpoint resolve → sandboxed script → files | `core/run_custom/pphrase_executor.py` is pure/no-I/O; execution materializes |
| Dashboards | `api/dashboard/sources.py` — in-memory `derive → filter → sort → limit` | *"v1 filters entirely in memory … pushing field predicates into the store via JSON1/JSONB `WHERE` is a noted follow-on (proposal §1.2)"* |

Dashboards carries `MAX_SCAN = 20_000` and a `truncated` flag, commented
*"(Pushdown filtering removes this.)"* — the fix is already named in the source.

**The bottleneck is the materialization boundary, not Python.** An infinitely fast script
still pays extraction. autoSQL moves the boundary rather than optimizing what sits behind it.

## Shape: one spec, one compiler, two renderers

```
            ┌──────────────── autoSQL ────────────────┐
  UI  ───▶  │  DataSource spec  +  window/aggregate   │
 (pick)     │              ↓ compiler                 │
            │         generated SQL                   │
            └────────────────┬────────────────────────┘
                             │ runs in the DB
                 ┌───────────┴───────────┐
                 ▼                       ▼
        dashboards resolve()      pphrase db_inputs
         (live widgets)                  │
                                         ▼
                                 post_doc + template
                                    (artifacts)
```

**Artifacts are unaffected by design.** Artifact generation is already a stage separate from
data acquisition — `core/run_custom/post_doc.py` runs `module:function` with `output_root`,
`phrase_root` (where the template lives) and `context`, and never touches a database. It
keeps making artifacts from templates; it simply receives an exact result set instead of a
scanned-and-filtered pile. A widget renders the spec to screen; a template renders it to an
artifact. Same spec, two renderers.

## Why the expression language is the seam

`core/dashboard/expr.py` is a real tokeniser + parser producing a tagged-tuple AST — not
`eval`. Three properties make it the integration point:

1. **It already has two runtimes** — `core/dashboard/expr.py` and `frontend/lib/expr.js` —
   held identical by `tests/fixtures/expr_vectors.json`. A SQL compiler is a **third runtime
   for the same AST**, with a ready-made equivalence oracle.
2. **It stops exactly where autoSQL starts.** Its docstring: *"Aggregation across records is
   a renderer concern, not part of this language."* Per-record scalars only; windowing and
   aggregation are the missing tier.
3. **Field types are declared, not guessed.** `GET /{project}/catalog` publishes
   `noun_fields` with types, *"driven by the schema, never guessed from data"* — which is
   what makes typed compilation feasible.

Grammar reference: `design/dashboard_expr_grammar.md`.

## Backend: Postgres query plane (operator decision, 2026-08-18)

Postgres is primary. SQLite does not get primacy.

**Why it lowers risk rather than raising it:**
- SQLite's `CAST('abc' AS REAL)` yields `0.0` **silently** — the exact silent-wrong-number
  failure mode this project must avoid. Postgres raises, so `jsonb_typeof` + guarded casts
  can honour expr's *total / returns-null* contract faithfully.
- expr is strict-ISO **UTC-only**; that maps onto `timestamptz`. SQLite's date functions are
  string manipulation.
- JSONB + GIN beats JSON1 for pushdown. `migrations/pg/0002_instances_data_gin.sql` exists.
- Full window frames (`RANGE`/`GROUPS`/`EXCLUDE`), `FILTER (WHERE …)`, `DISTINCT ON`,
  ordered-set aggregates. The proposal's **"collapse, never sample"** rule for heartbeats
  becomes one window pass:
  `LAG(value) OVER (PARTITION BY key ORDER BY ts) IS DISTINCT FROM value`.
- Cloud is half-built already: `get_db_uri()` is RDS-aware; `api/routers/dashboards/store.py`
  documents *"the RDS DSN in cloud mode"*.

**Scope boundary — this is D12b, not a migration.** `guts_enterprise.md` already decided:
*"D12b — GIMS as the QUERY PLANE, by projection rather than migration. Organs mirror state
into GIMS as a read model and keep local stores for writes, locks and invariants."* D12c adds
**"Locks never move."** autoSQL owns the **read/query plane** and owns no writes, no locks and
no invariants. Postgres-as-single-datastore is a different, larger claim the proposal argues
against; it is out of scope here.

## The pgvector reframe

`core/storage/sql.py` records a measured profile (2026-08-03, `guts-code`, 6333 vectors,
384-dim, 65.3 MB JSON):

```
load 826 ms + cosine 26 ms = 852 ms   (6333 loaded, 1509 used)
with pushdown:             = 210 ms   (1509 loaded)  → 4.1x, identical top-8
```

Its conclusion: *"pgvector is NOT the answer here: 97% of that time is JSON deserialization
and 3% is the cosine math… pgvector was gated on profiling proving the scan is the
bottleneck, and it is not."*

That measurement was taken against an architecture that ships rows into Python. **The 97% is
the round-trip autoSQL removes.** pgvector as a math accelerator buys 3%; pgvector *plus*
in-database filtering deletes the 97%. autoSQL is therefore the precondition that re-opens
the D4 gate on its own measured terms — not a reason to ignore it.

## Known risks

1. **Semantic equivalence is the real engineering.** expr is total (never throws, returns
   `null`); SQL's NULL propagation, coercion and date handling differ. Tractable only because
   `expr_vectors.json` makes equivalence *provable* rather than hoped-for.
2. **Generated SQL is JSON-path SQL, not columnar.** Records are arbitrary-key dicts, so
   pushdown means JSONB operators. Index strategy is a real design question.
3. **Not everything compiles.** The `query` source runs `cascade_deep_search` across nouns
   and verbs and will not push down cleanly. A hybrid is required: compile what compiles,
   fall back in-memory otherwise, and **report which happened**. A silent fallback would
   recreate the very problem being solved.

## Not this project (noted, deliberately out of scope)

`guts_enterprise.md` flags a larger exposure than any of the above: backups cover 2 of 4
store families, `~/.geds/geds.db` (172 MB) has zero coverage, no cron, a 27-day gap, no
cross-store consistency point, and nothing outside GIMS prunes anything. Recorded here so it
is not rediscovered as a surprise; it is not autoSQL's work.
