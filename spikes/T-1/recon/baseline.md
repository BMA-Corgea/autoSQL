# T-1 Recon — Measurement & Baseline

Researcher question: *define the measurement the spike must make, and the baseline it
measures against.* Scope is this question only — conformance, coverage, and index-shape
findings belong to other seats on this panel.

All paths below are in `gims-ledger` (`/home/corgea/Desktop/Coding Projects/GUTS/spine/L1-memory/gims-ledger`
@ `7b7a049`) unless marked otherwise. Per `FRAMING.md` §2 (C1), this is the correct tree for
the storage/measurement artifacts; the expression stack itself is byte-identical in both
trees (`FRAMING.md` table, §2) so citations to `api/dashboard/sources.py` apply equally to
`GIMS-Project` @ `995cc59`.

---

## 1. The current in-memory path, end to end

### 1.1 Entry point and call chain

A widget's data request enters through the dashboard router:

- `api/routers/dashboards/routes.py:237-245` — `POST /{project}/resolve` (`resolve_widget_data`).
  View-gated (`Depends(_VIEW)`, `:238`), resolves the project path, then calls straight
  through: `sources.resolve(body.source, project_path, {"now": _server_now()})` (`:245`).
  The docstring at `:239-240` states the contract precisely: *"Resolve a widget's record
  DataSource → `{records, count, truncated}` (view-gated)."*

That one call is the entire surface. `sources.resolve` (`api/dashboard/sources.py:330-357`)
is the orchestrator; everything else in the module is a helper it calls in sequence.

### 1.2 `resolve()` — the pipeline, in call order

`api/dashboard/sources.py:330-357`:

1. **Validate spec shape.** `source` must be a `Mapping` (`:337-338`); `type` must be one
   of `RECORD_SOURCE_TYPES = ("noun", "verb", "query")` (`:56`, dispatched via the
   `_LOADERS` dict at `:320-324`) or `AppError("DASHBOARD_SOURCE_TYPE_UNKNOWN")` (`:341-344`).
2. **Acquire raw rows** — `raw = loader(project_path, source)` (`:347`), one of:
   - `_noun_records` (`:193-211`) → `get_noun_items(project_path, noun_type)` (`:199`), the
     existing noun read seam; tags each row `_noun_type` (`:209-211`).
   - `_verb_records` (`:213-234`) → `list_verb_groups` + `load_verb_group_log` per group
     (`:218-233`); tags each row `_verb_group`.
   - `_query_records` (`:237-317`) → assembles noun/verb records and schemas, then calls
     `cascade_deep_search(term, schemas=..., noun_instances=..., verb_runs=..., ...)`
     (`:301-308`) and returns the matched rows. This is `core.deep_search.cascade_deep_search`
     (imported `:47`) — the same function `api/routers/deep_search.py` uses.
   All three loaders degrade to `[]` on read/format failure rather than raising
   (`:203-207` and `:200-201`, `:220-222`, `:225-227`, `:309-311`) — a policy the `resolve()`
   docstring itself states: *"data problems degrade to empty/None, never crash"* (`:335-336`,
   echoed in `tests/test_dashboard_sources.py:1-3`).
3. **Truncate to `MAX_SCAN`** — `api/dashboard/sources.py:348-351`:
   ```
   truncated = len(raw) > MAX_SCAN
   if truncated:
       log.warning("dashboard source hit MAX_SCAN cap", {"type": stype, "scanned": len(raw)})
   rows = raw[:MAX_SCAN] if truncated else raw
   ```
   `MAX_SCAN = 20_000` (`:61`), with the rationale written directly above it (`:57-60`):
   *"v1 materialises every candidate row in memory before filtering. This bounds how many
   raw rows a single widget will scan so a pathological collection can't exhaust memory;
   `truncated` is surfaced so the UI can warn. (Pushdown filtering removes this.)"* This is
   the exact sentence T‑1 exists to make true.
4. **Derive** — `rows = _apply_derive(rows, source.get("derive"), ctx)` (`:353`). Each
   `derive` entry is compiled once via `_compile`/`parse` (`:121-131`, wrapping
   `core.dashboard.expr.parse`, imported `:46`) then evaluated per row with
   `evaluate(ast, row, context)` (`:146`), writing the result back onto the row
   (`row[name] = ...`, `:146`). Total function — "Missing/bad data yields None (evaluator
   is total)" (`:136`).
5. **Filter** — `rows = _filter_rows(rows, source.get("filters"), source.get("where"), ctx)`
   (`:354`). Two predicate layers, both in-memory: exact-equality `filters` via
   `_pass_filters` (`:88-96`, one `_field_value` lookup per key, called per row at `:159`) and
   the expression `where` via `truthy(evaluate(where_ast, row, context))` (`:161-163`), where
   `where_ast` is compiled once outside the row loop (`:156`).
6. **Sort** — `rows = _apply_sort(rows, source.get("sort"))` (`:355`) → Python's `sorted()`
   over `_sort_key(_field_value(...))` (`:177-178`), a total order (`:99-116`) that ranks by
   type first so mixed-type columns never raise `TypeError` (`:100-104`, regression-pinned by
   `tests/test_dashboard_sources.py:182-187`, `test_sort_never_crashes_on_mixed_bool_and_container`).
7. **Limit** — `rows = _apply_limit(rows, source.get("limit"))` (`:356`) → Python slice
   `rows[:n]` (`:187`).
8. **Return** — `{"records": rows, "count": len(rows), "truncated": truncated}` (`:357`).

So the full chain for a noun widget is:

```
POST /{project}/resolve                          api/routers/dashboards/routes.py:237
  → resolve_widget_data                           routes.py:245
    → sources.resolve                             api/dashboard/sources.py:330
      → _noun_records → get_noun_items             sources.py:347 → :199
      → [truncate at MAX_SCAN]                     sources.py:348-351
      → _apply_derive → parse/evaluate (expr.py)   sources.py:353 → :133-148
      → _filter_rows → _pass_filters, evaluate     sources.py:354 → :151-165
      → _apply_sort → sorted(_sort_key(...))       sources.py:355 → :168-177
      → _apply_limit → list slice                  sources.py:356 → :180-187
    ← {records, count, truncated}                  sources.py:357
```

### 1.3 What `truncated` means to the caller

`truncated` is not cosmetic — it is the one signal that a widget's answer may be wrong
because rows were dropped **before** filter/sort/limit ran (raw scan capped at 20,000, not
the filtered result). It propagates unmodified through the API response
(`api/routers/dashboards/routes.py:245`, no re-derivation) into the frontend widget state:

- `frontend/lib/dashboard/widgets.jsx:45` — `records` widgets forward `truncated: r.truncated`.
- `frontend/lib/dashboard/widgets.jsx:30` — `trend` widgets do the same.
- `frontend/lib/dashboard/widgets.jsx:277` — rendered as a literal badge:
  `{state.data?.truncated && <span className="w-trunc" title="Result capped for
  performance">capped</span>}`.

So today, hitting `MAX_SCAN` degrades silently-but-labeled: the widget still returns a
result, just a "capped" one, with no distinction between "capped, but your filter still
found everything relevant" and "capped, and you lost rows your filter would have kept."
That distinction is exactly what pushdown removes (`sources.py:60`, *"Pushdown filtering
removes this"*) — which is why the measurement in §2 below has to be stated end-to-end
(acquire → derive → filter → sort → limit), not just as a scan-cost number: pushdown's
payoff is correctness headroom (no more silent 20,000-row ceiling) as well as latency.

---

## 2. The house style for a pushdown measurement

Two artifacts define it: the profile comment at `core/storage/sql.py:242-250` and its
formal pin, `tests/test_rag_search_pushdown.py`. Read together they are one measurement,
stated twice — once as narrative (why the number was taken), once as an executable claim
(what stays true going forward).

### 2.1 What it measures

Not a microbenchmark of the fast operation in isolation. It measures the **whole
user-visible action**, split into its two real phases, so the comparison is
apples-to-apples before/after the optimisation:

- `core/storage/sql.py:246` — `store.list_records("Vector")` **826 ms** (6333 records) — the
  "load everything" phase, i.e. deserializing JSON off disk for every candidate row,
  scoped or not.
- `core/storage/sql.py:246` — `cosine_topk(..., repo_id="goms")` **26 ms** (1509 of 6333
  used) — the actual math, run over whatever was loaded.
- `core/storage/sql.py:247` — end-to-end **852 ms**, and the number that actually matters,
  the pushed-down version of the *same* end-to-end action: **210 ms** (1509 loaded instead
  of 6333) → **4.1x**.

The test file's docstring states the same numbers with the percentage split named
explicitly: `tests/test_rag_search_pushdown.py:6-9`:
```
store.list_records("Vector")                826 ms      (6333 records)
cosine_topk(..., repo_id="goms")             26 ms      (1509 of them used)
                                          -------
end-to-end, repo-scoped search              852 ms      -> 97% load, 3% cosine math
```
and the delta: `tests/test_rag_search_pushdown.py:13` — *"Pushing the partition into SQL:
**852 ms -> 210 ms, 4.1x, byte-identical top-8.**"*

### 2.2 How it states the numbers

Every number carries: (a) the operation, (b) wall-clock time, (c) the row count that
produced that time, (d) what fraction of the *candidate set* was actually used downstream.
Never a bare "faster" — always `<phase>: <Nms> (<row-count> loaded/used)`. The provenance of
the measurement is stated inline, not left implicit: *"Measured 2026-08-03 against the live
`guts-code` project — 6333 `Vector` records, 384-dim, 65.3 MB of JSON in a 68 MB
`objects.db`"* (`tests/test_rag_search_pushdown.py:3-4`; identical figures at
`core/storage/sql.py:241-242`). A real, named, dated dataset — not "a large collection."

### 2.3 What it compares

Two arms of the *same* end-to-end call, differing only in whether the partition predicate
is pushed into the store or applied after full deserialization:

- **baseline arm**: `store.list_records("Vector")` then filter in the caller
  (`core/storage/sql.py:246`, "6333 loaded, 1509 used" — the *load* is unscoped, the
  *use* is scoped, and the delta between those two numbers **is** the waste being
  measured).
- **pushdown arm**: `store.list_records_where("Vector", {"repo_id": ...})`
  (`core/storage/sql.py:247`, "1509 loaded" — load and use now coincide).

And a **correctness arm**, not just a speed arm — `test_the_pushdown_returns_the_identical_top_k`
(`tests/test_rag_search_pushdown.py:82-93`) asserts the two arms return the *same*
`vector_id` ordering and the *same* scores, byte-for-byte identical, not just "similar." The
style treats "is it faster" and "is it still correct" as two separate, both-mandatory
questions — never inferring correctness from speed.

A third check verifies the pushdown is *real*, not decorative — that the store issued an
indexed search rather than a table scan that merely returns fewer rows:
`test_the_partition_filter_is_a_real_index_search_not_a_scan`
(`tests/test_rag_search_pushdown.py:65-77`) reads `EXPLAIN QUERY PLAN` and asserts
`"SEARCH" in plan and "SCAN" not in plan` (`:75`), and a fourth
(`test_the_route_asks_the_store_for_ONE_repo`, `:124-153`) proves the pushdown reaches all
the way to the HTTP route by spying on the actual call the route makes to the store, not
just unit-testing the store function in isolation — *"a route that still called
`list_records()` and filtered afterwards would pass every correctness test above while
buying nothing — the optimisation would be decorative"* (`:125-127`).

### 2.4 The conclusion form

The style draws a **lever-attribution conclusion**, not a bare speed claim — it names which
piece of the pipeline the time is actually going to, then evaluates a proposed fix against
*that* piece specifically:

`core/storage/sql.py:249-250` — *"The same profile is why pgvector is NOT the answer here:
97% of that time is JSON deserialization and 3% is the cosine math, so making the math free
would remove 3%. See D4 — pgvector was gated on profiling proving the scan is the
bottleneck, and it is not."* Restated in the test docstring,
`tests/test_rag_search_pushdown.py:15-18`: *"the cosine math is 3% of the time. Making it
free ... would remove 3%, against 75% for one line of pushdown. So pgvector is not being
deferred for lack of appetite; it was measured and it is the wrong lever."*

**The exact template**, abstracted from those two passages:

> `<baseline end-to-end time>` = `<phase A time>` (`<share A>%`, doing `<what A does>`) +
> `<phase B time>` (`<share B>%`, doing `<what B does>`).
> `<share A>%` of the time is `<bottleneck>`, `<share B>%` is `<the thing the proposed fix
> would speed up>`. Therefore fixing `<the thing the proposed fix would speed up>` removes
> at most `<share B>%`; the lever that matters is `<the actual bottleneck>`. Applying that
> lever: `<new end-to-end time>`, `<speedup factor>`, `<identical-output check, stated as a
> concrete equality, not "looked the same">`.

For T‑1, this template forces the measurement to isolate **which stage of §1.2 dominates
the in-memory path's cost** (acquisition/deserialization vs. the derive/filter/sort/limit
CPU work) before crediting the SQL compiler with removing it — mirroring the RAG case where
the naive assumption (pgvector — i.e. "make the math faster") targeted the wrong 3%, and the
real lever was cutting what got loaded/deserialized at all. T‑1's equivalent question:
is the current 20,000-row in-memory pipeline dominated by row acquisition
(`get_noun_items`/`load_verb_group_log`/`cascade_deep_search`, §1.2 step 2) or by the
Python-side derive/filter/sort work (§1.2 steps 4-7)? Pushdown only pays off against
whichever one it actually removes, and the measurement must say which, by percentage, the
way `core/storage/sql.py:249-250` does — not merely report an aggregate "N ms → M ms."

---

## 3. The representative widget

Real usage exists in the tree — this is not constructed from the docstring alone. Both the
module's own docstring and its test suite converge on the same concrete widget shape: a
"near-due samples" list, built from `derive` + `where` over a computed `days_left` field.

### 3.1 Evidence of real usage

- `api/dashboard/sources.py:6-7` (module docstring): *"'days_left', 'near-due', 'status' are
  all *composed* by the tenant through the derive/where expressions... never built in."*
  `near-due` is the named example use case for this exact mechanism, in the module's own
  description of what it's for.
- `api/dashboard/sources.py:15-28` (the `DataSource` spec block, confirmed at those line
  numbers): the worked example in the docstring itself is
  ```
  "derive": {"days_left": "days_between(today(), $.due_date)"},
  "filters": {"status": "open"},
  "where":   "$.days_left < 7",
  "sort":    {"field": "days_left", "dir": "asc"},
  "limit":   50
  ```
  i.e. the canonical example *is* the near-due widget — every clause of the pipeline
  populated at once.
- `tests/test_dashboard_sources.py:45-57` (`test_derive_and_where_compose_days_left`) pins
  this exact behavior against real fixture data (`SAMPLES`, `:14-18`), with the comment
  *"'near due' = a tenant-composed concept: derive days_left, keep < 7"* (`:46`).
- `tests/test_dashboard_sources.py:85-95` (`test_full_pipeline_order_derive_then_where_then_sort_then_limit`)
  is the one test in the suite that exercises **every** pipeline stage in one spec —
  `filters` + `derive` + `where` + `sort` + `limit` together — confirming this is the
  intended full-pipeline shape, not a corner case:
  ```python
  src = {
      **noun_source,
      "filters": {"status": "open"},
      "derive": {"days_left": "days_between(today(), $.due_date)"},
      "where": "$.days_left != null",
      "sort": {"field": "days_left", "dir": "asc"},
      "limit": 1,
  }
  ```

### 3.2 The benchmark spec

Combining the docstring's canonical example (§3.1, `sources.py:15-28`) with the full-pipeline
test's shape (`tests/test_dashboard_sources.py:85-95`), the representative widget for the
T‑1 benchmark is:

```json
{
  "type": "noun",
  "noun_type": "Sample",
  "filters": { "status": "open" },
  "derive": { "days_left": "days_between(today(), $.due_date)" },
  "where": "$.days_left != null and $.days_left < 7",
  "sort": { "field": "days_left", "dir": "asc" },
  "limit": 50
}
```

This is labelled **real, not constructed**: every clause (`type`/`noun_type`, `filters`,
`derive`, `where`, `sort`, `limit`) is drawn verbatim or near-verbatim from either the
module docstring's own worked example (`sources.py:15-28`) or a passing test in
`tests/test_dashboard_sources.py`. The only assembly step is combining the docstring's
`where` clause (`"$.days_left < 7"`, `sources.py:25`) with the null-guard the tests use when
`where` and a possibly-missing field are combined (`"$.days_left != null and ...`",
`tests/test_dashboard_sources.py:50`) — both are attested independently, not invented.

This spec exercises, in the terms of §1.2: acquisition (`_noun_records` →
`get_noun_items`), an equality filter (`_pass_filters` on `status`), a derive that calls a
two-argument built-in function with a context-dependent argument
(`days_between(today(), ...)`, both registered in the builtin function table at
`core/dashboard/expr.py:531` (`"today"`) and `:533` (`"days_between"`) — confirmed live by
importing the real evaluator: `cd GIMS-Project && .venv/bin/python -c "from
core.dashboard.expr import parse, evaluate; parse('days_between(today(), \$.due_date)')"`
returns a parsed AST tuple with no error, run against `GIMS-Project/.venv` per the
environment note), an expression `where` predicate with a null-guard and a comparison, a
sort on the derived (not raw) field, and a limit — i.e. every stage of the pipeline in
§1.2, which is
what makes it representative rather than a single-clause toy.

---

## 4. The synthetic dataset (specification only — not built)

### 4.1 Row counts

Two sizes, chosen to bracket the one number that actually governs the current path's
behavior, `MAX_SCAN = 20_000` (`api/dashboard/sources.py:61`):

- **N = 20,000 — the at-cap size.** The largest dataset the current pipeline will process
  *without* truncating (`len(raw) > MAX_SCAN` is `False` at exactly `MAX_SCAN`,
  `sources.py:348`). This is the size that stresses the full in-memory pipeline
  (acquisition + derive + filter + sort + limit, §1.2 steps 2 and 4-7) at its maximum
  *complete* scan — i.e. the hardest number the pushdown compiler has to beat honestly,
  with no rows silently dropped on either side to flatter the comparison.
- **N = 25,000 — the over-cap size.** `MAX_SCAN + 5,000`, generalizing the exact pattern
  the existing regression test already uses to pin truncation behavior:
  `tests/test_dashboard_sources.py:153-158` (`test_truncation_flag`) builds
  `big = [{"id": i} for i in range(sources.MAX_SCAN + 5)]` and asserts `out["truncated"] is
  True` and `out["count"] == sources.MAX_SCAN`. Scaling that `+5` to `+5,000` keeps the same
  proven pattern (round-number offset over the cap) while giving a wide enough margin that
  timing noise can't obscure whether truncation triggered. This size demonstrates the
  correctness gap identified in §1.3: 5,000 rows the in-memory path never even looks at,
  which the SQL path is not bound by `MAX_SCAN` at all and so has no equivalent loss.

Both sizes are needed together, not one or the other, because the measurement template in
§2.4 requires attributing time to a *named* phase — comparing 20,000 (fully processed) against
25,000 (partially processed, capped) isolates whether cost scales with rows *scanned* or rows
*acquired-before-truncation*, which is exactly the acquisition-vs-processing split the RAG
profile drew (`core/storage/sql.py:246`, "6333 loaded, 1509 used" as two distinct numbers,
not one).

### 4.2 Record shape and the generator rule

Records must look like what the store actually holds: arbitrary-key JSON documents, per the
`instances` table's shape — `data JSONB NOT NULL` with no fixed columns beyond
`(collection, key)` (`migrations/pg/0001_instances.sql:13-16`) — and per the resolver's own
description of what it returns: *"returns arbitrary-key dicts. It privileges **no**
field"* (`api/dashboard/sources.py:7`).

The generator rule, stated so it can be implemented later without ambiguity but **not**
implemented here:

1. **Fixed keys the benchmark widget needs** (§3.2), generated with distributions that make
   the widget's `filters`/`where` selective rather than vacuous — mirroring the real fixture's
   proportions (`tests/test_dashboard_sources.py:14-18`, `SAMPLES`: 3 of 4 rows `status:
   "open"`, one row missing `due_date` entirely):
   - `id`: a unique string per row (`f"S-{i}"`), so sort/limit results are checkable
     deterministically.
   - `status`: categorical, weighted so a plurality but not all rows are `"open"` (e.g.
     ~60% `"open"`, ~40% other values) — the fixture is 75% open (`3/4` in `SAMPLES`); any
     ratio that keeps the `filters: {"status": "open"}` clause from passing everything or
     nothing is faithful to it.
   - `due_date`: an ISO date spread across a wide window relative to the injected `now`
     (the widget's `derive` is `days_between(today(), $.due_date)`, §3.2) so that the
     `where: "$.days_left < 7"` clause keeps a real minority of rows, not all or none —
     and a small fraction of rows (matching `SAMPLES`' `S-4`, `tests/test_dashboard_sources.py:17`)
     omit `due_date` entirely, to exercise the total-evaluator's None-propagation path
     (`_apply_derive`'s "Missing/bad data yields None", `sources.py:136`) at scale.
   - `priority`: a small integer, present on every row (as in `SAMPLES`), to give the
     alternate `sort` field a cheap secondary check.
2. **Arbitrary extra keys**, present on every row, to make the JSON genuinely
   heterogeneous/wide rather than a clean four-column table — because the phase §2.4
   identifies as the likely dominant cost (deserialization, per the RAG profile's own 97%
   finding, `core/storage/sql.py:249`) scales with document *size and key count*, not with
   how many of those keys the widget's `derive`/`where`/`sort` actually touch. Rule: each
   row additionally carries a variable number (e.g. 5-15, varied per row so the corpus is
   non-uniform) of extra key/value pairs with generated names (`f"field_{n}"`) and mixed
   value types (string / number / bool / null / short nested object), reflecting that
   dashboards bind to tenant-defined nouns whose schemas are open-ended
   (`api/dashboard/sources.py:6-7`, *"'days_left', 'near-due', 'status' are all composed by
   the tenant"* — implying the underlying noun record itself is not a fixed schema either).
3. **Determinism.** The generator must be seeded (fixed RNG seed) so a run is reproducible
   and the "N=20,000 vs N=25,000" comparison in §4.1 is comparing the *same* per-row shape
   at two truncation points, not two different corpora — otherwise a timing delta could be
   an artifact of different average document size rather than of `MAX_SCAN`.

This is a specification, not an implementation: no generator script exists yet under
`spikes/T-1/proto/`, per the framing's throwaway-prototype boundary
(`FRAMING.md` §3, *"The prototype is throwaway by contract"*) and this researcher's scope
(defining the measurement and its baseline, not building the harness).

---

## 5. The measurement, stated in the house style (§2.4 template applied)

Putting §1-§4 together, what T‑1's finding-#4 (`FRAMING.md` §4 table, row 4, "Measurement")
must produce, in the same shape as `core/storage/sql.py:249-250`:

> Run the widget in §3.2 against the dataset in §4.1 (N=20,000, then N=25,000) through the
> current path (`api/dashboard/sources.py:330-357`, chain in §1.2) and record, separately:
> **acquisition** time (`raw = loader(...)`, `sources.py:347`), **derive+filter+sort+limit**
> time (`sources.py:353-356`), and the **end-to-end** total — the same load/use split the RAG
> profile drew (`core/storage/sql.py:246`). Then run the same widget compiled to SQL against
> the same dataset loaded into the spike's scratch Postgres database (per the environment
> note: create `autosql_spike`, never touch `glp_strong`'s existing contents) and record its
> single end-to-end time. State: `<in-memory end-to-end>` = `<acquisition ms>`
> (`<X>%`, deserializing/reading rows) + `<processing ms>` (`<Y>%`, derive/filter/sort/limit
> in Python) — therefore compiling `<the larger of X/Y>` into SQL is the lever that matters,
> and the pushdown result is `<SQL end-to-end ms>`, `<speedup factor>`, with output identity
> checked row-for-row against the in-memory result (matching
> `tests/test_rag_search_pushdown.py:82-93`'s "identical top-k" check, not a spot check) —
> and separately, for N=25,000, note that the in-memory arm's `truncated: true` means its
> 20,000-row answer is missing rows the SQL arm's answer is not, per §1.3.

That is the whole shape: a measurement this spike has not yet run (no timing numbers exist
in this repo for the in-memory dashboard path — see §6, Gaps), stated in the exact form the
codebase already uses elsewhere for exactly this kind of claim.

---

## 6. Gaps — what this researcher did not, and could not, establish

- **No timing numbers.** This document defines the measurement; it does not run it. There
  is no existing benchmark of `api/dashboard/sources.py`'s in-memory pipeline anywhere in
  either GIMS tree (searched for it while locating `tests/test_dashboard_sources.py`; that
  suite is functional/correctness-only — every test asserts on record identity/order, none
  times anything). The "826 ms / 210 ms / 4.1x"-shaped numbers in §5's template are
  placeholders (`<...>`) precisely because inventing plausible-looking figures here would
  violate rule 6 (no fabricated numbers) — running the actual harness is downstream work,
  presumably this spike's `sp-investigate` proto phase.
- **No confirmed dashboard-widget usage frequency.** §3 justifies the representative widget
  from the module's own docstring example and the test suite's one full-pipeline test
  (`tests/test_dashboard_sources.py:85-95`) — the strongest real evidence found in the tree.
  I did not find (and did not exhaustively search for, being out of this question's scope)
  any telemetry or a corpus of real, tenant-authored `DataSource` JSON to prove this is the
  *most common* widget shape in production, only that it is the canonical one the codebase
  itself uses to document and to fully test the feature.
- **The `_INDEXABLE_FIELDS` / GIN-index style (`core/storage/sql.py:200-262`) was read for
  context** (it explains *why* `repo_id` specifically was whitelisted) but is a different
  researcher's question (index shape, `FRAMING.md` §4 row 3) — I did not analyze whether
  dashboard `derive`/`where` fields could be added to that whitelist; that mechanism (exact
  JSONB containment, `jsonb_path_ops`) is explicitly the wrong shape for dashboard pushdown
  per `FRAMING.md` §2's own restated finding #3, so I did not lean on it further here.
- **No live Postgres numbers were taken.** The environment note names `glp-strong-db` /
  `autosql_spike` as available; this question did not require touching it (no code was run
  against Postgres), only `GIMS-Project/.venv` for the one live `parse()` call in §3.2 to
  confirm the widget's expression is valid syntax — not to measure anything.



