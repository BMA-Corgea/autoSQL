# T-1 recon — can the `query` DataSource push down?

**Question owned by this document:** can the `query` DataSource push down, and if not,
what exactly bounds it? Bound the blast radius (1-of-3 source types, or more) and state
the honest fallback rule from the code, not intuition. Also check whether `noun`/`verb`
sources even reach a `RecordStore` — if they don't, pushdown has no seam to attach to.

Both GIMS trees are read-only. All three files this document is built from —
`api/dashboard/sources.py`, `core/deep_search.py`, `api/iostore/nouns.py`,
`api/iostore/verb_logs.py` — are byte-identical between `GIMS-Project` (995cc59) and
`gims-ledger` (7b7a049), confirmed by `diff -q` on this machine (see §5 for the one file
that differs and why it doesn't matter here). Citations below use `GIMS-Project` paths;
they apply to both trees unless noted.

---

## 1. What `cascade_deep_search` actually does

Entry point: `core/deep_search.py:381` (`GIMS-Project/core/deep_search.py:381`, identical
in `gims-ledger`). It is a **pure function** — its own docstring says so
(`core/deep_search.py:389-390`: "This function does NO I/O... Inputs must already be
loaded into memory") — that runs three independent match stages and concatenates them:

1. **Schema-definition match** — `match_schema_definitions` (`core/deep_search.py:97`),
   called at `core/deep_search.py:407`. Iterates `schemas = {"noun": {...}, "verb": {...},
   "adjective": [...], "adverb": [...]}` (all **four** word types, not just noun/verb —
   `core/deep_search.py:110-121`) and matches the search term against each schema's
   *name* (dict key, or an `adjective`/`adverb` entry's own id field), via substring and
   normalized-substring comparison (`core/deep_search.py:129-133`). This searches
   **schema metadata**, not row data — it has no data-row shape at all
   (`match_context` is the schema definition object, `core/deep_search.py:136`).

2. **Noun-instance match** — `match_instances` (`core/deep_search.py:154`), called at
   `core/deep_search.py:410-416` over the full `noun_instances` list, using
   `primary_id_lookup` (`noun_type -> primary_id_field`, from the noun schema).

3. **Verb-run match** — the same `match_instances` function, called again at
   `core/deep_search.py:419-425` over the full `verb_runs` list, this time using
   `verb_primary_id_by_group` (`verb_group -> primary_id_field`, from each verb-group log
   config) instead of `primary_id_lookup`.

Stages 2 and 3 share `match_instances` (`core/deep_search.py:154-341`), and its matching
logic per row is a **scored cascade with early exit**, not a predicate:

- For each row, it first resolves *which key counts as the primary id* — dynamically,
  per row, via `find_actual_key` (`core/deep_search.py:29-39`, tolerant to
  case/space/underscore/hyphen) against either the schema-declared field
  (`primary_id_lookup`/`primary_id_map_by_group`) or, failing that, a **hardcoded
  fallback list of ~13 candidate id-field names** (`"id", "run_id", "runID", "RunID",
  "Run ID", "sample_id", "Sample ID", "sampleID", "batch_id", "Batch ID", "batchID",
  "submission_id", "Submission ID", "submissionID"` — `core/deep_search.py:249-252`).
- It then compares the term against those id-field candidates first
  (`core/deep_search.py:255-268`), scoring `exact_id=100 > normalized_exact_id=90 >
  substring_id=80 > normalized_substring_id=70`, and **breaks early** on an exact id hit
  (`core/deep_search.py:259-262`).
- If no id-field hit scores ≥80, it falls through to scanning **every other field on the
  row** (`for field, v in item.items(): ... core/deep_search.py:290-306`), comparing
  string-coerced values with the same normalize/substring logic at lower scores
  (`exact_field=60 > normalized_exact_field=50 > substring_field=40 >
  normalized_substring_field=30`).
- `normalize_string` (`core/deep_search.py:9-13`) is `str.lower()` **with all whitespace
  removed**, not a plain `LOWER()` — a distinct normalization, not case-folding.
- Matched rows are annotated in place — `match_context`, `match_score`, `match_type`,
  plus `_primary_id_field`/`_primary_id_field_resolved`/`_resolved_group` — via
  `item.copy()` (`core/deep_search.py:227-230, 314-317`), then all results are sorted by
  `match_score` descending (`core/deep_search.py:339`).

Finally, `deduplicate_matches` (`core/deep_search.py:342-380`) drops repeat
`noun_instance` matches, keyed by `(noun_type, primary_id_value)` where the primary-id
field is again resolved per-`noun_type` via `find_actual_key` — **schema matches and verb
matches pass through undeduplicated** (`core/deep_search.py:349-351, 375-379`).

---

## 2. What inputs it needs that SQL does not have

`cascade_deep_search`'s signature (`core/deep_search.py:381-387`) takes six arguments,
none of which is a table or a connection:

- `schemas: dict` — noun/verb/adjective/adverb **schema definitions**, loaded from JSON
  files by `load_schema` (`api/dashboard/sources.py:246-253`, one call per word type).
  These are project configuration artifacts, not instance rows, and have no row-shaped
  representation in the instances table at all.
- `noun_instances: list[dict]` — **every** noun instance for **every** noun type in the
  project's schema, assembled by looping `get_noun_items` over all noun types
  (`api/dashboard/sources.py:256-267`) — no `noun_type` filter, no cap.
- `verb_runs: list[dict]` — **every** run for **every** verb group, assembled by looping
  `load_verb_group_log` over `list_verb_groups(project_path)`
  (`api/dashboard/sources.py:272-293`) — again no cap.
- `primary_id_lookup: dict` — `noun_type -> primary_id_field`, read out of the noun
  schema (`api/dashboard/sources.py:295-298`).
- `verb_primary_id_by_group: dict` — `verb_group -> primary_id_field`, read per group
  from `get_verb_group_log_config` (`api/dashboard/sources.py:276-281`).

So the row-acquisition step for `query` is not "select matching rows from one table" —
it is "load a config-driven closure of everything (all noun types, all verb groups, all
four schema kinds) into Python, then run a Python string-matching algorithm over it."

## 3. Precisely why it cannot be one SQL query

1. **Three heterogeneous inputs, not one table.** Schema definitions
   (`schemas`) are project JSON config, not instance rows; noun instances and verb runs
   are two structurally different data sources (verb runs are never even attempted
   against the noun collection — see §4). A single `SELECT ... FROM instances` cannot
   also search schema JSON that lives outside any table.
2. **Dynamic, per-row column set.** The fallback field scan
   (`core/deep_search.py:290`) iterates `item.items()` — *whatever keys the dict
   happens to have* — there is no fixed column list to write `WHERE col ILIKE ...`
   against. In JSONB terms this needs a per-row `jsonb_each` unnest of arbitrary width,
   which is expressible in SQL in principle, but only for a schema known in advance —
   and the id-field candidate list here is resolved by trying a hardcoded list of
   13 alternate names PLUS a case/space/underscore-tolerant match
   (`find_actual_key`, `core/deep_search.py:29-39`) against config loaded at request
   time. That resolution is imperative branching (try config field → try
   `_primary_id_field_from_config` tag → try `_verb_group` lookup → try the fallback
   resolver → try the hardcoded alt-name list — `core/deep_search.py:184-249`), not a
   value comparison a `WHERE` clause expresses.
3. **A scored cascade with early exit, not a boolean predicate.** The matcher assigns
   one of eight distinct scores per row (100/90/80/70/60/50/40/30) by trying id-field
   candidates in priority order and `break`ing on the first exact hit
   (`core/deep_search.py:259-262`), then only falls through to the full-field scan if no
   high-confidence id match was found. `WHERE`/`ORDER BY` express predicates and sort
   keys, not "stop scanning this row once a strong-enough match is found and skip the
   weaker checks."
4. **The match mutates the row it returns.** `item_with_context = item.copy();
   item_with_context["match_context"] = ...` (`core/deep_search.py:227-230`) attaches
   `match_context`/`match_score`/`match_type` — a per-row computed annotation whose
   *shape* (which field matched, at what score) is only knowable after running the same
   procedural cascade above. This could in principle be a computed column, but only once
   the cascade itself is expressed in SQL — which requires solving points 1-3 first.
5. **Post-hoc, config-keyed deduplication.** `deduplicate_matches`
   (`core/deep_search.py:342-380`) drops repeat noun matches by `(noun_type,
   primary_id_value)` where `primary_id_value` is extracted via yet another
   `find_actual_key` lookup per row (`core/deep_search.py:365-368`) — a `GROUP BY` whose
   key column is itself dynamically resolved per row, not a fixed field.

None of this is "hard to compile, in principle" so much as "the row-acquisition
algorithm is a small imperative program over dict shapes GIMS never declares to SQL" —
schema-tolerant field-name resolution, priority/early-exit scoring, and a metadata (not
data) source folded into the same result set. This is qualitatively different from the
`derive`/`where`/`sort`/`limit` pipeline the rest of the T-1 spike is investigating,
which evaluates one `expr` AST (`core/dashboard/expr.py`) against one row shape.

---

## 4. Do `noun` and `verb` sources even reach a `RecordStore`?

**`noun`: yes, conditionally — but with no filter attached even where it does.**

`api/dashboard/sources.py:199` (`_noun_records`) calls `get_noun_items(project_path,
noun_type)` (`api/iostore/nouns.py:29`). Its first read attempt (`api/iostore/nouns.py:
53-61`, labelled "0) Unified instances store (the SQL-only target)") is:

```python
from core.storage.factory import collection_for_noun, get_record_store
_rows = get_record_store(project_path).list_records(collection_for_noun(noun_type))
if _rows:
    ...
    return out
```

`get_record_store` (`core/storage/factory.py`) resolves to `SqlRecordStore`
(`core/storage/sql.py:37`, local SQLite) or the RDS/Postgres adapter, selected by
`rds_enabled()` (`core/storage/factory.py:33-45`). So **yes**, noun records go through
the `RecordStore` port — *when that collection has already been migrated/populated*; the
comment at `api/iostore/nouns.py:52` is explicit that an empty collection falls through
to legacy per-noun-table / JSONL reads (steps 1-3 below it, not examined further here —
out of scope for this question).

But the abstract `RecordStore.list_records(collection)` (`core/storage/ports.py:33-36` in
`GIMS-Project`, unchanged in `gims-ledger` per the diff in §5) takes **only a collection
name — no filter argument at all**. `SqlRecordStore.list_records`
(`GIMS-Project/core/storage/sql.py:58-62`) is literally `SELECT data FROM instances WHERE
collection = ?` — the *entire* collection, every time. And `get_noun_items` calls it with
no filter (`api/iostore/nouns.py:55-61`) — no `where`, no field predicate. **The seam
exists, but nothing today asks it to filter**, so even the noun source's row-acquisition
is a full-collection scan before `sources.py`'s in-memory pipeline runs.

A capability check specifically for pushdown: `list_records_where(collection, equals)`
does exist — but only as an *extra* method (not on the `RecordStore` ABC) on the more
capable stores: `gims-ledger/core/storage/sql.py:518` (SQLite) and
`gims-ledger/api/storage_aws.py:1010` (Postgres/RDS). Both restrict to a **fixed field
whitelist**, `_INDEXABLE_FIELDS` (`gims-ledger/core/storage/sql.py:252-266`) —
`proposal_slug, ticket_id, sprint_id, actor, kind, correlation_id, run_id, repo_id,
destination, proposal, status, ...` — which are **gims-ledger's own ticket/proposal
domain fields**, not arbitrary GIMS dashboard noun fields like "due_date" or a
tenant-defined "status". Even where this method exists, `get_noun_items` never calls
it (confirmed: `api/iostore/nouns.py` is byte-identical across both trees, and its only
`RecordStore` call is the unfiltered `list_records` above). And `GIMS-Project`'s own
`core/storage/sql.py` (163 lines) has **no** `list_records_where` at all — grepped
methods are `list_records, get_record, put_record, delete_record, transaction, count,
collections` only (`GIMS-Project/core/storage/sql.py:58,65,73,83,92,112,120`).

**`verb`: no — it never touches `RecordStore` at all.**

`api/dashboard/sources.py:226` (`_verb_records`) calls `load_verb_group_log(project_path,
grp)` (`api/iostore/verb_logs.py:72`). That function does its own direct SQL, entirely
bypassing `core.storage`:

```python
cur.execute(f'SELECT data FROM public."{table}" WHERE verb_group=%s ORDER BY ts DESC;', ...)
```
(`api/iostore/verb_logs.py:81`, Postgres path; the SQLite path at `:87-88` is the same
shape) — against a hand-built table name `_table_name(project_path.name)`
(`api/iostore/verb_logs.py:44-46`, `<project>_verb_log`), with a JSONL fallback on
failure (`api/iostore/verb_logs.py:95-100`). There is no `RecordStore`, no `ports.py`
interface, no `factory.get_record_store()` call anywhere in this path — grepped: `core.storage`
does not appear in `api/iostore/verb_logs.py` at all. **This is a bigger structural fact
than the query source's non-pushdown-ness**: verb has one existing filter (`verb_group=`,
a column that already exists on the hand-rolled table) but no seam through which a
compiled `expr` predicate could be injected today — a pushdown compiler targeting
`RecordStore` would need a *second*, separate integration for verb runs, not just an
extension of the noun path.

---

## 5. The one file that differs, and why it's not load-bearing here

`core/storage/ports.py` differs between the two trees (`diff` run on this machine).
The `gims-ledger` version adds ~260 lines of ledger-specific compare-and-set revision
machinery (`put_record_if_newer`, `ledger_prune_transaction`, `REVISION_MAX`, etc.) that
belongs to the ticket-ledger's own write-ordering contract — nothing this question
depends on. The methods this document cites — `list_records`, `get_record`,
`put_record`, `delete_record`, `transaction` — are **unchanged** between the two
versions (the diff is a pure insertion after `transaction()`, confirmed by the `47a253`
diff hunk marker placing all new content after line 47). So "`RecordStore.list_records`
takes no filter" holds in both trees.

---

## 6. Bounding: how many of the 3 source types does this affect?

`RECORD_SOURCE_TYPES = (SOURCE_NOUN, SOURCE_VERB, SOURCE_QUERY)` —
`api/dashboard/sources.py:53-56`. Answering precisely, per type, for "can this source's
row-acquisition step be compiled to a single SQL predicate over a fixed table/columns":

| type | row-acquisition call | goes through `RecordStore`? | can row-acquisition become one `WHERE` clause? |
|---|---|---|---|
| `noun` | `get_noun_items` (`api/dashboard/sources.py:199`) | Yes, conditionally (§4) — one collection, one table, one primary key | **In principle yes** — a single, homogeneous source (this is exactly what the rest of T-1 is testing for `derive`/`where`/`sort`/`limit`) |
| `verb` | `load_verb_group_log` (`api/dashboard/sources.py:226`) | **No** — raw SQL against a hand-built table, bypasses `core.storage` entirely (§4) | In principle yes (it's one table, one `verb_group=` filter today) — but there is no `RecordStore` seam to attach a compiled predicate to; a pushdown compiler needs a second integration point here, not the same one as `noun` |
| `query` | `cascade_deep_search` via `_query_records` (`api/dashboard/sources.py:237-317`) | Only insofar as its *inputs* (`noun_instances`) partially reach it — the search algorithm itself never touches SQL | **No** — §3 (heterogeneous inputs, dynamic field scan, scored cascade with early exit, mutate-and-annotate, config-keyed dedup) |

So, precisely: it is **1-of-3 source types (`query`) whose row-acquisition step is
categorically non-SQL-expressible** for algorithmic reasons (§3). It is **also true**,
though for a different reason, that `verb`'s row-acquisition has no seam to push into
today even though the SQL itself would be simple (§4) — so the honest count for "does
this affect only `query`, or more" is: **`query` is the only source that cannot be
compiled even in principle; `verb` could be compiled in principle but has no attachment
point yet; only `noun` has both** (a possible SQL shape *and* an existing `RecordStore`
seam, unfiltered today).

---

## 7. The fallback rule: does the whole widget fall back, or only row-acquisition?

Read from `resolve()` (`api/dashboard/sources.py:330-357`):

```python
raw = loader(project_path, source)                      # source-specific, always in-memory today
truncated = len(raw) > MAX_SCAN
rows = raw[:MAX_SCAN] if truncated else raw

rows = _apply_derive(rows, source.get("derive"), ctx)   # source-agnostic
rows = _filter_rows(rows, source.get("filters"), source.get("where"), ctx)  # source-agnostic
rows = _apply_sort(rows, source.get("sort"))             # source-agnostic
rows = _apply_limit(rows, source.get("limit"))           # source-agnostic
```

`_LOADERS = {SOURCE_NOUN: _noun_records, SOURCE_VERB: _verb_records, SOURCE_QUERY:
_query_records}` (`api/dashboard/sources.py:320-324`) is the only place source type
selects behavior. Once `loader(...)` returns `raw` (a plain `List[dict]`), every
downstream step — `_apply_derive` (`:133-148`), `_filter_rows` (`:151-165`),
`_apply_sort` (`:168-177`), `_apply_limit` (`:180-187`) — is a pure function of
`List[dict]` that **does not know or care which loader produced the rows**. They take no
source-type argument at all.

**So the fallback rule the code implements is: only the row-acquisition step is
source-specific; `derive`/`where`/`sort`/`limit` are structurally source-agnostic
already, today, in-memory.** That is a necessary precondition for "partial pushdown" to
even be a coherent idea, but it is not itself pushdown: right now *all three* sources'
`derive`/`where`/`sort`/`limit` run in Python over `rows`, whatever produced them.

The honest answer to "does the whole widget fall back, or only row-acquisition" for a
**future SQL-compiling `derive`/`where`/`sort`/`limit` layer** specifically, reasoned
from this same code shape:

- For `noun` (and, with a second integration, `verb`): yes, a **partial** pushdown is
  structurally coherent — row-acquisition (`get_noun_items`/`load_verb_group_log`) is
  already a plain `SELECT`-shaped read against one table, so a compiler could in
  principle extend that same `SELECT` with compiled `WHERE`/`ORDER BY`/`LIMIT` clauses,
  leaving only genuinely non-compiling `derive`/`where` expressions (if any — the other
  panel seats are answering that) to fall back to the existing in-memory functions
  applied to *whatever the SQL layer already narrowed down*.
- For `query`: **no partial win is available**, but not because `derive`/`where`/`sort`/
  `limit` are themselves incapable — they are the same source-agnostic functions as
  above and would run unmodified over `cascade_deep_search`'s output exactly as they do
  today. The reason is architectural, not expressive: pushing `derive`/`where`/`sort`/
  `limit` into Postgres means compiling them into the **same SQL statement** that
  performs row-acquisition, so they can run inside the database in one round trip.
  `query`'s row-acquisition is not a SQL statement — `cascade_deep_search` is a pure
  Python function (`core/deep_search.py:389`) over already-in-memory lists, with no
  query object to append clauses to. There is no `SELECT` upstream of it to extend. The
  only way to get `derive`/`where`/`sort`/`limit` running inside Postgres for the
  `query` source would be to materialize `cascade_deep_search`'s output into a scratch
  table first and then run a second, compiled query against *that* — which is exactly
  today's in-memory behavior with an extra round trip bolted on, not a pushdown win, and
  is out of scope per the framing doc's stop rule ("bound and confirm it does not push
  down, do not attempt to make it" — `spikes/T-1/FRAMING.md`, §3).

**Conclusion: for `query`, the whole widget's pipeline stays in-memory in practice** —
not because the code hardwires that (it doesn't; `_apply_derive` et al. are already
loader-agnostic), but because there is no SQL statement upstream for a compiled
`derive`/`where`/`sort`/`limit` layer to attach to once `cascade_deep_search` has already
produced its final, deduplicated, ranked result set.

---

## 8. A scale finding the safety cap does not actually cover

`MAX_SCAN = 20_000` (`api/dashboard/sources.py:61`) is applied in `resolve()` at
`api/dashboard/sources.py:348` to `len(raw)` — i.e., to **`_query_records`'s output**
(the post-cascade, post-dedup, post-scope-filter list returned at
`api/dashboard/sources.py:312-317`). It is **not** applied anywhere inside
`_query_records` to the *candidate pool* `cascade_deep_search` actually scans: the loops
building `noun_instances` (`api/dashboard/sources.py:256-267`, every noun type, no
limit) and `verb_runs` (`api/dashboard/sources.py:269-293`, every verb group, no limit)
are unbounded before `cascade_deep_search` is even called
(`api/dashboard/sources.py:301-308`). So the module's own stated purpose for the cap —
"bounds how many raw rows a single widget will scan" (`api/dashboard/sources.py:58-60`)
— does not hold for the `query` source: a project with more than 20,000 total
noun-instances-plus-verb-runs pays the full `match_instances` cost
(`core/deep_search.py:154`, an O(rows × fields) string-comparison scan) on every `query`
widget resolution, and the cap only ever truncates the *matches*, after the expensive
work is already done. This is a genuine scaling exposure specific to `query` that a
"1-of-3, and here's the fallback" framing alone would understate.

---

## 9. Summary answer

- **Can `query` push down? No.** `cascade_deep_search`'s row-acquisition is a pure,
  procedural, scored cascade over three heterogeneous in-memory inputs (schema
  definitions, all noun instances, all verb runs), with dynamic per-row field-name
  resolution and early-exit scoring — not a value predicate over a fixed table/columns
  (§1-3).
- **Is it 1-of-3, or more?** It is the only source type that is **categorically**
  non-compilable. `verb` is compilable in principle but has **no `RecordStore` seam at
  all today** (§4, §6) — a different, structural blocker worth flagging alongside
  `query`'s. Only `noun` has both a plausible SQL shape and an existing (if unfiltered)
  `RecordStore` attachment point.
- **Whole-widget fallback, or just row-acquisition?** For `query`, the whole pipeline
  stays in-memory in practice, but the code's `derive`/`where`/`sort`/`limit` functions
  are already source-agnostic (§7) — the blocker is that there is no SQL statement
  upstream of `cascade_deep_search`'s Python-only row-acquisition for a compiler to
  extend, not that those four functions can't compile.
- **Bonus finding:** `MAX_SCAN` does not bound `query`'s actual scan cost — only its
  output size (§8).

## Gaps / not established here

- Whether `noun`'s unfiltered `list_records` behavior is what actually runs in a
  production deployment (RDS-enabled vs. local) was not traced end-to-end for a live
  project — `get_record_store`'s selection (`core/storage/factory.py:33-45`) depends on
  `rds_enabled()`/`storage_provider()` config not inspected here.
  This does not change the finding (`list_records` takes no filter on either backend),
  only which concrete class serves it.
- The legacy fallback paths inside `get_noun_items` (RDS per-noun table, SQLite,
  JSONL — `api/iostore/nouns.py:63-`, not fully read past line ~100) were not traced in
  full; irrelevant to this question since the *unfiltered-scan* property holds at the
  first (unified store) branch already and none of those fallbacks introduce filtering
  either (none is invoked with a predicate argument from `_noun_records`).
- Whether `expr` AST compilation (the rest of T-1) could ever be extended to express
  `cascade_deep_search`'s specific scoring cascade as a generated SQL query (rather than
  concluding it flatly cannot) was not attempted — the framing doc's stop rule
  explicitly says bound and confirm, not attempt (`FRAMING.md` §3).
