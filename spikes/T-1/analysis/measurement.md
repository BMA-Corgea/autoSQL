# T-1 Spike — Finding #4: Measurement

**Seat scope.** `FRAMING.md` §4, finding #4 only: *end-to-end numbers vs. the current
in-memory path on a representative widget, in the manner of the existing RAG pushdown
profile.* Conformance (#1), coverage (#2) and index shape (#3) belong to other seats; where
this document touches them it says so and defers.

**Everything below is a measured number with the command that produced it.** Where a claim
is an opinion or an inference rather than a measurement, it is labelled **OPINION** or
**INFERENCE** in place.

---

## Headline

Six table sizes, 1 000 → 1 000 000 rows, one widget, both paths, medians over 3–9 repetitions.

| | 1 k | 10 k | 20 k | 25 k | 100 k | 1 M |
|---|---:|---:|---:|---:|---:|---:|
| **Path A** — in-memory today (ms) | 13.8 | 142.3 | 300.1 | 331.7 | 899.3 | 8 331.4 |
| **Path B** — compiled, `xpr` runtime (ms) | 57.5 | 554.0 | 1 138.6 | 1 447.2 | 6 036.4 | 59 590.0 |
| **Path B** — same query, native operators *(unsafe ceiling)* (ms) | 1.1 | 6.7 | 13.2 | 16.4 | 34.0 | 230.0 |
| rows Path A pulls into Python | 1 000 | 10 000 | 20 000 | 25 000 | 100 000 | 1 000 000 |
| Path A peak RSS | 72 MB | 98 MB | 125 MB | 137 MB | 338 MB | **2 765 MB** |
| payload over the wire, A ÷ B | 19× | 192× | 381× | 467× | 1 960× | **19 668×** |
| **Path A top-50 recall vs. ground truth** | 100% | 100% | 100% | **88%** | **38%** | **4%** |

Three results, and they do not point the same way:

1. **Pushdown is the right lever.** At 1 M rows, **98% of Path A's time is deserializing
   980 000 records it then discards unexamined**, and it holds 2.8 GB of Python heap to answer
   a 50-row question. Pushdown removes that entirely: 16 kB instead of 317 MB.
2. **The prototype's SQL runtime destroys the win, by ~99.6%.** Path B is **3.8×–7.2× slower
   than Path A at every size**, because one `xpr` plpgsql call costs **11–12 µs/row** against
   a native equivalent at or below the noise floor (0.07–0.22 µs/row) — **85× at 1 M rows,
   52×–156× across sizes** — and the 11–12 µs is constant over three orders of magnitude. The same
   query with native operators is **36× faster than Path A** and returns a **row-for-row
   identical** answer.
3. **`MAX_SCAN` is not a performance cap, it is a wrong-answer cap.** Past 20 000 rows the
   in-memory widget silently answers a different question: at 1 M rows **98% of qualifying
   records are never examined, 2 of its 50 rows are right, and even its top row is wrong** —
   under a UI badge that reads *"Result capped for performance."*

---

## 0. Provenance — what was measured, on what, when

| | |
|---|---|
| Date | 2026-08-19 |
| Postgres | 16.14 (Debian 16.14-1.pgdg12+1), docker container `glp-strong-db`, image `pgvector/pgvector:pg16` |
| Database | `autosql_spike` (the spike's own scratch db — `glp_strong` untouched) |
| Cluster locale | `C.UTF-8` |
| `shared_buffers` | 128 MB (`16384` × 8 kB) |
| `work_mem` | 4 MB |
| `max_parallel_workers_per_gather` | 2 |
| `extra_float_digits` | pinned to `1` for every run (as the conformance run did) |
| Host | 20 cores, 46 GB RAM, NVMe (`/dev/nvme0n1p2`) |
| Python | 3.12.3 — `/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python`, psycopg2 2.9.12 |
| Expression stack | `GIMS-Project` @ `995cc59` — the **real** `core/dashboard/expr.py` and the **real** `api/dashboard/sources.py`, imported, not reimplemented |
| Compiler under test | `spikes/T-1/proto/compile.py` (unmodified; mtime 11:23, predates this seat) |
| SQL runtime | `spikes/T-1/proto/runtime.sql`, schema `xpr`, 21 functions (unmodified; mtime 11:20) |

Harness: `/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/bench.py`
(+ `gen_data.py`, `load_data.py`). Raw output:
`/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/measurements.json`.
All three are throwaway per `FRAMING.md` §3.

```bash
# the whole sweep, verbatim
PY="/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python"
G="/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto"
SP=<scratchpad>/data
for N in 1000 10000 20000 25000 100000 1000000; do
  "$PY" "$G/gen_data.py"  $N "$SP/n$N.csv"          # deterministic corpus, SEED=1729
  "$PY" "$G/load_data.py" $N "$SP/n$N.csv" gin      # COPY into measure_instances_$N
done
"$PY" "$G/bench.py" 1000,10000,20000,25000
"$PY" "$G/bench.py" 100000,1000000
```

---

## 1. The house style being matched

The ticket says *"in the manner of the existing RAG pushdown profile"*. That profile is
`gims-ledger/core/storage/sql.py:241-250`, quoted here in full so the reader can see the
form:

```
# ``repo_id`` is the RAG's partition key, and it is here because a profile said so rather than
# because it looked tidy (Enterprise P2-GIMS / checklist L42, measured 2026-08-03 on the live
# `guts-code` project: 6333 vectors, 384-dim, 65.3 MB of JSON). A repo-scoped semantic search —
# which is EVERY search the retriever makes — used to load all 6333 records and discard 76% of them
# inside `cosine_topk`, because the partition filter was applied after deserialization.
#
#     load 826 ms + cosine 26 ms = 852 ms      (6333 loaded, 1509 used)
#     with this pushdown:         = 210 ms      (1509 loaded)  -> 4.1x, identical top-8
#
# The same profile is why pgvector is NOT the answer here: 97% of that time is JSON deserialization
# and 3% is the cosine math, so making the math free would remove 3%. See D4 — pgvector was gated on
# profiling proving the scan is the bottleneck, and it is not.
```

Three properties of that style, which §4–§7 below reproduce
(the analysis of the style itself is `recon/baseline.md` §2 — not redone here):

1. **Split the end-to-end time into named phases** and give each one its row count
   (`6333 loaded, 1509 used`), never a bare aggregate.
2. **Attribute the time to a lever**, then evaluate the proposed fix *against that lever*
   — the profile's conclusion is that pgvector would remove 3%, so pgvector is the wrong
   lever. Speed and correctness are two separate mandatory questions, never inferred from
   one another (`tests/test_rag_search_pushdown.py:82-93` asserts *identical* top-8).
3. **Name the dataset, dated** — "6333 `Vector` records, 384-dim, 65.3 MB of JSON in a
   68 MB `objects.db`", not "a large collection".

---

## 2. The representative widget, and why it is representative

```json
{
  "type": "noun", "noun_type": "Sample",
  "filters": { "status": "open" },
  "derive":  { "days_left": "days_between(today(), $.due_date)" },
  "where":   "$.days_left != null and $.days_left < 7",
  "sort":    { "field": "days_left", "dir": "asc" },
  "limit":   50
}
```

Taken unchanged from `recon/baseline.md` §3.2. Its warrant, restated with the citations
this seat re-verified in `GIMS-Project` @ `995cc59`:

- `api/dashboard/sources.py:6-7` — the module's own docstring names this use case:
  *"'days_left', 'near-due', 'status' are all **composed** by the tenant through the
  derive/where expressions … never built in."*
- `api/dashboard/sources.py:15-28` — the docstring's **worked example of a DataSource is
  this widget**, clause for clause: `"derive": {"days_left": "days_between(today(),
  $.due_date)"}`, `"filters": {"status": "open"}`, `"where": "$.days_left < 7"`,
  `"sort": {"field": "days_left", "dir": "asc"}`, `"limit": 50`.
- `tests/test_dashboard_sources.py:85-95`
  (`test_full_pipeline_order_derive_then_where_then_sort_then_limit`) is the single test in
  that suite that populates **every** pipeline stage at once, and it populates them with
  these clauses.

So it is representative in the only sense the tree can support: it is the shape the module
documents itself with and the shape its one full-pipeline test uses. **INFERENCE, and a
gap:** there is no telemetry or corpus of tenant-authored `DataSource` JSON in either tree,
so nobody can show this is the *most common* widget in production — only that it is the
canonical one. `recon/baseline.md` §6 records the same gap; this seat did not close it.

Critically, it exercises **all four** pipeline stages (`sources.py:353-356`), including the
two that make pushdown hard: a `where` that reads a **derived** column (which does not
exist in the stored JSON), and a `sort` on that same derived column.

---

## 3. The corpus

Generated by `spikes/T-1/proto/gen_data.py`, implementing the generator rule specified in
`recon/baseline.md` §4.2 (which deliberately did not implement it). Seeded `SEED = 1729`,
so every size is the same per-row shape.

| | |
|---|---|
| Record shape | `{id, status, due_date?, priority}` + 5–15 arbitrary `field_N` keys of mixed type (string / float / bool / null / small nested object) |
| `status` | ~60% `"open"`, else `closed`/`hold`/`void` |
| `due_date` | ISO date, uniform over −30…+370 days from `2026-08-19`; **5% of rows omit it entirely** (the `SAMPLES` `S-4` case, `tests/test_dashboard_sources.py:17`) |
| Mean JSON size | 283 bytes/row (`gen_data.py` prints `avg_json_bytes`; 282.3–284.1 across sizes) |
| Selectivity | `filters` alone keeps ~60%; `filters` **and** `where` keep **~5.1%** (measured, §5 table) |
| Storage | one table per size, `measure_instances_<N>`, DDL byte-identical to `gims-ledger/migrations/pg/0001_instances.sql:13-18`; each carries the GIN `jsonb_path_ops` index of `migrations/pg/0002_instances_data_gin.sql:36-37` |
| `now` | pinned to `2026-08-19T12:00:00Z` in the evaluation context, matching the shape `api/routers/dashboards/routes.py:177` `_server_now()` produces — so no run reads the wall clock |

**One table per size, not one shared table with a `collection` per size**, because a single
1.156 M-row table would make the 1 M arm sequentially scan 156 k rows belonging to the other
sizes and charge that to the 1 M number. Each table therefore holds exactly N rows, all in
collection `noun:Sample`.

Loaded sizes and on-disk cost (`load_data.py` output, verbatim):

| rows | COPY (s) | GIN build (s) | heap+index |
|---:|---:|---:|---:|
| 1 000 | 0.01 | 0.01 | 968 kB |
| 10 000 | 0.08 | 0.09 | 8 256 kB |
| 20 000 | 0.17 | 0.18 | 16 MB |
| 25 000 | 0.21 | 0.23 | 20 MB |
| 100 000 | 0.89 | 1.11 | 78 MB |
| 1 000 000 | *not captured* | *not captured* | **700 MB** (419 MB heap + 281 MB GIN) |

*Not captured, honestly:* the 1 M loader aborted **after** COPY and the GIN build had both
succeeded, at its `VACUUM ANALYZE` step — `psycopg2.errors.DiskFull: could not resize shared
memory segment to 67128640 bytes`, because this container's `/dev/shm` is the docker default
64 MB (`docker exec glp-strong-db df -h /dev/shm` → `64M`). The timing print was lost with it.
The table was completed by hand and its size measured:
```bash
docker exec glp-strong-db psql -U glp_owner -d autosql_spike \
  -c "ALTER SYSTEM SET max_parallel_maintenance_workers=0" -c "SELECT pg_reload_conf()"
docker exec glp-strong-db psql -U glp_owner -d autosql_spike -c "VACUUM ANALYZE measure_instances_1000000"
# -> 700 MB|734101504|419 MB
```
That `ALTER SYSTEM` is cluster-wide and is **reverted in §11**.

**Where the sweep stopped: 1 000 000 rows.** Reason, stated rather than implied: the host
had 20 GB of free disk at the start and the 1 M corpus consumed 700 MB of database plus a
359 MB CSV; a 10 M arm would have needed ~7 GB of database and ~15 minutes of Path-A wall
clock per repetition. 1 M is already 50× `MAX_SCAN`, which is the regime the finding needs.

---

## 4. What each arm actually is

### Path A — today's in-memory pipeline

Run through the **real** `api/dashboard/sources.py`, imported from `GIMS-Project` and
called function by function so each stage can be timed separately (`bench.py:path_a`).
The sequence is `sources.resolve`'s own, `sources.py:347-356`:

| phase | what runs | citation |
|---|---|---|
| `fetch_wire` | `SELECT data::text FROM <t> WHERE collection = %s`, `fetchall()` | acquisition seam of `PgRecordStore.list_records`, `gims-ledger/api/storage_aws.py:728-731` |
| `deserialize` | `[json.loads(s) for s in texts]` | the `_as_dict` the same store applies, `api/storage_aws.py:693-694` |
| `truncate` | `raw[:MAX_SCAN]` when `len(raw) > MAX_SCAN` | `sources.py:348-351`, `MAX_SCAN = 20_000` at `sources.py:61` |
| `derive` | `SRC._apply_derive(rows, derive, ctx)` | `sources.py:353` → `:133-148` |
| `filter` | `SRC._filter_rows(rows, filters, where, ctx)` | `sources.py:354` → `:151-165` |
| `sort` | `SRC._apply_sort(rows, sort)` | `sources.py:355` → `:168-177` |
| `limit` | `SRC._apply_limit(rows, 50)` | `sources.py:356` → `:180-187` |

The `::text` cast splits the driver's single opaque number into wire-transfer and
JSON-decoding, which is the split the RAG profile needs. **Caveat, measured not assumed:**
`path_a_driver()` re-runs the acquisition exactly as `list_records` does it (`SELECT data`,
psycopg2's own jsonb loader) as a control. The two do **not** agree exactly — the control is
between 2% faster and 39% *slower* than the split (§5.2), because psycopg2's own jsonb
decoding is slower than `::text` + stdlib `json.loads`. The direction matters and is stated
rather than smoothed over: **the split under-reports Path A's real acquisition cost by up to
~24–39%**, so every Path A number below is a lower bound on the production call.

`_noun_records`/`get_noun_items` (`sources.py:193-211`) is **not** in the loop: in
`GIMS-Project` that seam reads a project's own store and would drag in manifest resolution
and S3 shims. **This is a deviation and it flatters Path A**: the measured acquisition is a
single local-TCP Postgres `SELECT` against a warm table, which is the *fastest* acquisition
that seam has (`api/iostore/nouns.py:52-62` prefers exactly this unified-instances read).
Any real deployment's acquisition is ≥ this. §7's conclusion is therefore conservative in
Path A's favour.

### Path B — the compiled pushdown

`compile.py` is called on the AST from the real `expr.parse()`, unmodified. Four variants,
because the naive one and the shippable one are not the same query, and the difference is
itself a result:

- **B1 — faithful.** Materialise `data || jsonb_build_object('days_left', <derive_sql>)` in
  a subquery, then filter and sort over the augmented document. This mirrors what
  `_apply_derive` literally does (`row[name] = evaluate(...)`, `sources.py:146`).
- **B2 — inlined.** The derive AST is substituted into the `where` and `sort` ASTs
  (`bench.py:subst`), so no per-row jsonb concatenation happens; the augmented document is
  built only for the 50 surviving rows. Semantics-preserving: `_apply_derive` writes the
  value and later clauses read it back, so replacing the read with the producing AST is the
  same computation.
- **B3 — inlined + containment.** B2 with the `filters` clause written `data @> '{"status":
  "open"}'` instead of `data->'status' = '"open"'::jsonb`, so the `jsonb_path_ops` GIN index
  of migration 0002 is usable. *(Whether that is the right index shape is finding #3's
  question, not this seat's — the number is reported and the design conclusion deferred.)*
- **B4 — ceiling, UNSAFE, not a candidate.** The same widget with `days_left` computed as
  `((data->>'due_date')::date - DATE '2026-08-19')::float8` — native Postgres date
  arithmetic instead of the `xpr` runtime. **`::date` RAISES on a malformed date**, which is
  the exact totality violation `xpr.pdate_ms` exists to prevent (`compile.py:28-31`,
  `expr.py:409-431`). It is measured only to bound how much of Path B's time is the `xpr`
  runtime rather than the scan — the lever-attribution the RAG profile draws at
  `core/storage/sql.py:249-250`. **It must never be read as a proposal.**

### The sort, and one deliberate deviation

`_apply_sort` orders by `_sort_key` (`sources.py:99-116`), a 3-tuple
`(type-rank, number-or-bool, string)` with ranks `bool 0 < number 1 < string 2 < other 3 <
None 4`. `bench.py:sort_sql` emits that tuple verbatim as three `ORDER BY` keys. Rank 3
(`str(value)` of a list/dict — a Python `repr`) is **not compilable**; the harness does not
pretend otherwise — the corpus never produces it for `days_left`, and that is asserted by
the row-for-row identity check rather than assumed.

**Python's `sorted()` is stable; Postgres' sort is not.** `days_left` is whole-day-valued,
so ties are guaranteed and a tie spanning the `LIMIT 50` boundary makes the two arms'
answers legitimately different. The **timing** runs use the widget's own `ORDER BY`,
untouched. The **identity and quality** runs add a deterministic tiebreak on `$.id` to
*both* arms (`bench.py:TIE`, `path_a_tiebreak`). That is a real finding for the gate, not
just harness plumbing — see §9.

### Timing method

- **Median of N repetitions**, with min / max / stdev reported for every cell — never a
  single sample. N = 9 at 1 k–25 k, 7 at 100 k, 3 at 1 M (the 1 M arm costs minutes per
  repetition; the reduction is stated, not hidden).
- Each arm is **warmed once** (result discarded) before the repetitions, so every number is
  a warm-cache number. See §10 for what that hides.
- The connection is opened once and reused; `psycopg2.connect()` took **7.6 ms** and is
  **excluded from both arms** — it is a constant that would be paid by either.
- Path A re-fetches on every repetition (it must: `_apply_derive` mutates the rows in
  place, `sources.py:146`), so its acquisition is genuinely re-measured each time.
- `extra_float_digits = 1`, matching the conformance run.

---

## 5. Results

Every cell is a **median** over the repetition count in §4, from
`analysis/measurements.json` / `analysis/probes.json`.
### 5.1 End-to-end wall clock, median of N repetitions (ms)

| rows | reps | **Path A** (in-memory) | **B1** faithful | **B2** inlined | **B3** inlined+GIN | **B4** ceiling *(unsafe)* | A ÷ B2 | A ÷ B4 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 9 | **13.8** | 88.0 | 57.5 | 58.0 | 1.1 | **0.24×** | **12.1×** |
| 10,000 | 9 | **142.3** | 854.1 | 554.0 | 547.5 | 6.7 | **0.26×** | **21.2×** |
| 20,000 | 9 | **300.1** | 1,754.2 | 1,138.6 | 1,128.9 | 13.2 | **0.26×** | **22.8×** |
| 25,000 | 9 | **331.7** | 2,231.9 | 1,447.2 | 1,461.5 | 16.4 | **0.23×** | **20.3×** |
| 100,000 | 7 | **899.3** | 9,188.5 | 6,036.4 | 5,950.6 | 34.0 | **0.15×** | **26.5×** |
| 1,000,000 | 3 | **8,331.4** | 95,384.2 | 59,590.0 | 59,609.8 | 230.0 | **0.14×** | **36.2×** |

Spread (min–max over the repetitions):

| rows | Path A | B1 | B2 | B3 | B4 |
|---:|---|---|---|---|---|
| 1,000 | 13.4–14.3 | 86.3–89.9 | 57.3–62.5 | 56.7–61.1 | 1.1–1.3 |
| 10,000 | 138.5–162.2 | 848.7–863.4 | 545.3–564.5 | 545.9–551.3 | 6.6–6.9 |
| 20,000 | 277.1–313.2 | 1,715.3–1,860.2 | 1,117.2–1,155.2 | 1,114.2–1,144.0 | 12.6–13.7 |
| 25,000 | 309.2–359.0 | 2,208.6–2,262.6 | 1,432.0–1,454.1 | 1,452.7–1,545.8 | 16.0–21.0 |
| 100,000 | 879.2–921.4 | 9,108.5–9,394.7 | 5,951.9–6,184.4 | 5,900.8–5,965.8 | 33.3–34.4 |
| 1,000,000 | 8,109.9–8,389.6 | 93,350.6–97,088.0 | 59,269.9–60,409.8 | 58,478.2–60,589.6 | 228.5–236.1 |

### 5.2 Where Path A's time goes

| rows | fetch (wire) | deserialize | **acquire** | derive | filter | sort | limit | **process** | **total** | acquire % | process % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 2.2 | 3.1 | **5.5** | 7.2 | 1.1 | 0.03 | 0.00 | **8.3** | **13.8** | 40% | 60% |
| 10,000 | 20.3 | 33.7 | **54.4** | 74.8 | 12.2 | 0.34 | 0.00 | **87.8** | **142.3** | 38% | 62% |
| 20,000 | 40.6 | 89.0 | **129.4** | 145.3 | 24.5 | 0.73 | 0.00 | **171.1** | **300.1** | 43% | 57% |
| 25,000 | 57.8 | 99.2 | **159.2** | 145.9 | 24.5 | 0.80 | 0.00 | **171.7** | **331.7** | 48% | 52% |
| 100,000 | 210.0 | 519.5 | **728.0** | 146.4 | 24.8 | 0.86 | 0.00 | **172.3** | **899.3** | 81% | 19% |
| 1,000,000 | 2,237.4 | 5,938.9 | **8,161.4** | 143.9 | 25.0 | 0.77 | 0.00 | **170.0** | **8,331.4** | 98% | 2% |

Control — acquisition run exactly as `PgRecordStore.list_records` does it (`SELECT data`, psycopg2's own jsonb decoding) vs. the harness's `::text` + `json.loads` split. **The control column is a SINGLE sample (n=1), not a median** — it is a sanity check on the split, not a headline number:

| rows | split (fetch+deserialize), median | `list_records` form, **n=1** | delta |
|---:|---:|---:|---:|
| 1,000 | 5.5 | 5.4 | -2% |
| 10,000 | 54.4 | 75.8 | +39% |
| 20,000 | 129.4 | 133.8 | +3% |
| 25,000 | 159.2 | 165.4 | +4% |
| 100,000 | 728.0 | 900.0 | +24% |
| 1,000,000 | 8,161.4 | 36,256.5 | +344% |

### 5.3 Rows and bytes

| rows in table | Path A rows materialised in Python | Path A peak RSS | Path A payload over the wire | Path B rows | Path B payload | payload ratio |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 1,000 | 72 MB | 0.32 MB | 50 | 17.0 kB | **19×** |
| 10,000 | 10,000 | 98 MB | 3.16 MB | 50 | 16.5 kB | **192×** |
| 20,000 | 20,000 | 125 MB | 6.30 MB | 50 | 16.6 kB | **381×** |
| 25,000 | 25,000 | 137 MB | 7.88 MB | 50 | 16.9 kB | **467×** |
| 100,000 | 100,000 | 338 MB | 31.59 MB | 50 | 16.1 kB | **1,960×** |
| 1,000,000 | 1,000,000 | 2,765 MB | 317.02 MB | 50 | 16.1 kB | **19,668×** |

### 5.4 The `xpr` runtime's per-row cost, isolated

| rows | `count(*)` (scan floor) | `+ data->'due_date'` | `+ xpr.pdate_ms(...)` | `+ (data->>'due_date')::date` | xpr µs/row | native µs/row | ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.32 | 0.33 | 11.8 | 0.55 | **11.52** | 0.220 | **52×** |
| 10,000 | 0.88 | 2.45 | 113.0 | 3.16 | **11.06** | 0.071 | **156×** |
| 20,000 | 1.71 | 5.09 | 224.5 | 6.95 | **10.97** | 0.093 | **118×** |
| 25,000 | 2.00 | 6.52 | 287.3 | 8.47 | **11.23** | 0.078 | **144×** |
| 100,000 | 7.51 | 25.74 | 1,253.5 | 23.55 | **12.28** | ≈0 *(within noise)* | *n/a* |
| 1,000,000 | 42.92 | 106.23 | 12,059.4 | 247.42 | **11.95** | 0.141 | **85×** |

### 5.5 Answer quality at and beyond MAX_SCAN = 20,000

| rows | `truncated` | rows Python examined | qualifying rows in table | qualifying rows **never examined** | top-50 recall | rank-1 right? | row-for-row identity |
|---:|:--:|---:|---:|---:|---:|:--:|---|
| 1,000 | no | 1,000 | 50 | 0 (0%) | **100%** (50/50) | yes | IDENTICAL |
| 10,000 | no | 10,000 | 510 | 0 (0%) | **100%** (50/50) | yes | IDENTICAL |
| 20,000 | no | 20,000 | 1,055 | 0 (0%) | **100%** (50/50) | yes | IDENTICAL |
| 25,000 | **yes** | 20,000 | 1,338 | 284 (21%) | **88%** (44/50) | yes | NOT COMPARABLE (Path A truncated at MAX_SCAN) |
| 100,000 | **yes** | 20,000 | 5,202 | 4,146 (80%) | **38%** (19/50) | yes | NOT COMPARABLE (Path A truncated at MAX_SCAN) |
| 1,000,000 | **yes** | 20,000 | 52,327 | 51,271 (98%) | **4%** (2/50) | NO | NOT COMPARABLE (Path A truncated at MAX_SCAN) |

Two notes on the tables above, so nothing is over-read:

- **§5.2's control column is one sample.** `path_a_driver_acquire_ms` is measured once per
  size, not repeated. The 1 M figure (+344%) is therefore a single observation and could be
  garbage collection under a 2.8 GB heap as easily as driver cost. What it is *not* is
  evidence that the split over-states Path A — every observation points the other way.
- **`EXPLAIN (ANALYZE)` timings are inflated and are used only for plan shape.** At 1 M the
  instrumented B2 reports 81.5 s against a measured 59.6 s (+37% for per-node timing). The
  plans themselves are the point: **neither arm went parallel** (no `Gather` node at any
  size), so this is a single-thread-vs-single-thread comparison; the 1 M table does not fit
  in `shared_buffers` (`Buffers: shared hit=8820 read=44772`).

---

## 6. The profile, in the RAG profile's own form

### 6.1 Where Path A's time actually goes — and it changes regime at `MAX_SCAN`

The ticket's warning is exactly right: *"a pushdown that only removes evaluation but keeps
the fetch buys much less."* The measurement says which one it is, and the answer is **both,
in different regimes**:

```
BELOW the cap (N = 10,000):
    fetch 20.3 ms + deserialize 33.7 ms = acquire  54.4 ms   (38%,  10,000 rows loaded)
    derive 74.8 ms + filter 12.2 ms + sort 0.3 ms = process  87.8 ms   (62%,  10,000 rows evaluated, 510 kept)
                                                  ---------
    end-to-end                                     142.3 ms      -> 38% load, 62% Python expression evaluation

AT 100,000 (5x the cap):
    fetch 210.0 ms + deserialize 519.5 ms = acquire 728.0 ms   (81%, 100,000 rows loaded)
    derive 146.4 ms + filter 24.8 ms + sort 0.9 ms = process  172.3 ms   (19%,  20,000 rows evaluated — the cap — 1,056 kept)
                                                  ---------
    end-to-end                                     899.3 ms      -> 81% load, 19% evaluation

AT 1,000,000 (50x the cap):
    fetch 2,237 ms + deserialize 5,939 ms = acquire 8,161 ms   (98%, 1,000,000 rows loaded)
    derive 143.9 ms + filter 25.0 ms + sort 0.8 ms = process   170.0 ms   ( 2%,  20,000 rows evaluated — the cap — 1,056 kept)
                                                  ---------
    end-to-end                                   8,331 ms      -> 98% load, 2% evaluation
```

The `process` column is **flat at ~171 ms from 20,000 rows upward** — that is `MAX_SCAN`
visible in the timings, and it is why the regime flips. Below the cap the dominant cost is
Python expression evaluation; above it, acquisition of rows that are then discarded
unexamined. In the RAG profile's language: **at 1 M rows, 98% of the time is JSON
deserialization of 980,000 records that are thrown away without being looked at.**

`derive` alone is 44–53% of the sub-cap total (7.2–7.5 µs/row) — `days_between(today(),
$.due_date)` calls `_parse_date_ms` twice per row (`expr.py:469-475`). `sort` is never more
than 0.3% and `limit` is unmeasurably small: **the pipeline's back half is free**; all the
cost is in the front half, acquisition + derive.

### 6.2 The lever, and what applying it actually bought

Pushdown attacks **both** phases at once — it returns 50 rows instead of N (§5.3: **19,668×
less payload at 1 M**, 317 MB → 16 kB) and it moves the evaluation off the Python heap. On
the lever-attribution alone the case is overwhelming.

**And the prototype still loses.** Path B as it stands is **3.8× to 7.2× slower than Path A
at every size measured** (§5.1: `A ÷ B2` between 0.14× and 0.26×). At 1 M rows, the widget
that takes 8.3 s in Python takes **59.6 s** in Postgres.

Where that time goes is not the scan and not the plan — §5.4 isolates it:

```
scan 1,000,000 rows, evaluate nothing            count(*)                        42.9 ms
scan + read the field                            + data->'due_date'             106.2 ms
scan + read + ONE xpr plpgsql call               + xpr.pdate_ms(...)         12,059.4 ms
scan + read + the equivalent native cast         + (data->>'due_date')::date    247.4 ms
                                                                            -----------
                        one xpr.pdate_ms call costs  11.95 us/row   vs  0.14 us/row native  -> 85x
```

That number is stable across three orders of magnitude of table size (**10.97, 11.06, 11.23,
11.52, 11.95, 12.28 µs/row** at N = 20 k, 10 k, 25 k, 1 k, 1 M, 100 k respectively), so it is
a per-call constant, not a scaling artifact — and B2's own per-row cost at 1 M is
59,590 ms ÷ 1,000,000 = **59.6 µs/row**, i.e. the same order as a handful of such calls. The
compiled filter contains two `xpr.pdate_ms` calls per row plus `xpr.truthy`/`xpr.ord`
(visible in the `EXPLAIN` filter text, `measurements.json → explain_B2`).

*A per-function decomposition of that 59.6 µs was attempted and is **discarded**, not
reported: it ran while another process on this host was consuming ~774% CPU and returned
self-contradictory results (adding a function made the query faster). It is preserved in
`probes.json → xpr_decomposition_100k_ms` marked contended. See §10.11 — host contention is a
real weakness of this whole document, quantified there.*

The ceiling arm proves it from the other side. **B4 — the same widget, same plan shape, same
50 rows, with the `xpr` calls replaced by native date arithmetic — runs in 230 ms at 1 M
rows, 36× faster than Path A**, and returns an answer that is **row-for-row identical** to
the compiled arm's at every size (`b4_ceiling_matches_compiled_answer: {"ok": true,
"detail": "identical"}`, all six sizes).

So, in the template `core/storage/sql.py:249-250` uses:

> At 1 M rows the in-memory widget costs **8,331 ms** = **8,161 ms (98%, deserializing
> 1,000,000 JSON records of which 980,000 are discarded unexamined)** + **170 ms (2%,
> evaluating expressions over the 20,000 that survived `MAX_SCAN`)**. Compiling the
> expressions into SQL removes **both** — 50 rows returned instead of 1,000,000, 16 kB
> instead of 317 MB. Applying that lever with the prototype's `xpr` runtime gives
> **59,590 ms — 7.2× slower**. Applying it with native operators gives **230 ms — 36.2×
> faster, with a row-for-row identical answer.** The lever is right; the runtime is wrong.
> **~99.6% of Path B's time is plpgsql function-call overhead** (59,590 → 230 ms), so
> optimising the plan, the index, or the scan would remove ~0.4%.

**This is the same mistake the RAG profile caught, pointed the other way.** There it was
"make the math faster" (pgvector) against a 3% math cost. Here it is "push the predicate into
the index" against a runtime that costs 85× the operator it replaces. §5.1 shows it directly:
**B3 (GIN-indexed containment) and B2 (plain seq scan) are within noise of each other at
every size** — 59,610 ms vs 59,590 ms at 1 M — because the index changes how many rows reach
the `xpr` calls (`Rows Removed by Filter` 546,670 with the index vs 947,673 without) and the
`xpr` calls are the entire cost. *Index shape is finding #3's question; this seat reports only
that on this widget the index is not the binding constraint while the runtime is.*

**OPINION, labelled as such:** nothing measured here tells you whether a fast runtime is
*achievable* while keeping `expr`'s totality. `xpr.pdate_ms` is plpgsql precisely because
`::date` raises and `expr` must not (`compile.py:28-31`). B4 buys its 36× by giving up
exactly that. Whether the same guarantees can be had from a `LANGUAGE sql IMMUTABLE`
rewrite, a C extension, or a narrower guard is a design question this seat did not test.

---

## 7. `MAX_SCAN` — where Path A stops being *correct*, not merely slow

`sources.py:348-351` truncates the **raw** scan, *before* `filters`, `where`, `sort` and
`limit` run:

```python
truncated = len(raw) > MAX_SCAN
if truncated:
    log.warning("dashboard source hit MAX_SCAN cap", {"type": stype, "scanned": len(raw)})
rows = raw[:MAX_SCAN] if truncated else raw
```

Three consequences, all measured rather than argued.

**(a) The cap does not save the expensive part.** `raw` is fully materialised *before* the
slice: `raw = loader(...)` at `:347`, `raw[:MAX_SCAN]` at `:351`. Path A therefore fetches,
deserializes and holds **every** row in Python and then throws most of them away. §5.2 shows
the shape directly — from 100 000 rows on, the Python evaluation cost is **frozen** (172 ms,
because it only ever sees 20 000 rows) while acquisition keeps growing without bound. At 1 M
rows the cap saves nothing at all and Path A still pays 8.3 seconds and multi-GB of RSS to
answer a 50-row question.

**(b) The 20 000 rows it keeps are an arbitrary 20 000.** `list_records` issues
`SELECT data FROM <t> WHERE collection = %s` with **no `ORDER BY`**
(`gims-ledger/api/storage_aws.py:730`) — so which rows survive the cap is whatever order the
store happened to return, here Postgres' physical scan order. It is not "the 20 000 most
relevant", not "the 20 000 newest": it is an implementation detail of the plan.

**(c) The widget still renders, labelled but not corrected.** `truncated` propagates
untouched to the UI and becomes a badge — `frontend/lib/dashboard/widgets.jsx:277`,
`title="Result capped for performance"`. "For performance" is the part the numbers contradict:
the answer is not merely late, it is different.

### How different — the measurement

Ground truth is Path B run without the `LIMIT`, over the whole table, with the deterministic
tiebreak of §9.2 (`bench.py:ground_truth`, `answer_quality`).
| rows | `truncated` | qualifying rows in table | rows Python examined | qualifying rows **never examined** | **top-50 recall** | is rank 1 right? |
|---:|:--:|---:|---:|---:|---:|:--:|
| 1 000 | no | 50 | 1 000 | 0 (0%) | **100%** (50/50) | yes |
| 10 000 | no | 510 | 10 000 | 0 (0%) | **100%** (50/50) | yes |
| 20 000 | no | 1 055 | 20 000 | 0 (0%) | **100%** (50/50) | yes |
| 25 000 | **yes** | 1 338 | 20 000 | 284 (21%) | **88%** (44/50) | yes |
| 100 000 | **yes** | 5 202 | 20 000 | 4 146 (80%) | **38%** (19/50) | yes |
| 1 000 000 | **yes** | 52 327 | 20 000 | 51 271 (98%) | **4%** (2/50) | **NO** |

Read that as answer quality, not latency:

- **At 25 000 rows** — 25% over the cap — the widget already shows **6 rows that do not
  belong in its top 50**, and hides 6 that do.
- **At 100 000 rows**, 62% of the answer is wrong: 31 of the 50 rows displayed are not in the
  true top 50. The badge still says "capped for performance".
- **At 1 000 000 rows the answer is essentially unrelated to the question.** 2 of 50 rows are
  right, 98% of qualifying records were never examined, and **the top row itself is wrong** —
  the single number a "value" widget would render (`api/routers/dashboards/routes.py`'s
  catalog lists `value` as a renderer) is not the correct one.
- The degradation is **monotonic and starts immediately at 20 001 rows**. There is no safe
  margin above the cap.

Path B has no equivalent loss at any size: it evaluates every row and returns the true top 50
by construction, which is why `qualifying_rows_never_examined` is the ground truth column and
Path B is the thing computing it.

**One caveat on the recall numbers, stated because it cuts against my own result:** which 20 000
rows Path A sees is the scan order (point (b)), and in this corpus that order correlates with
`$.id`, which is also the tiebreak. That makes Path A's answer *more* self-consistent than a
randomly ordered store would, so **these recall figures are, if anything, optimistic for Path A.**
The tiebreak-independent columns — `qualifying rows never examined` — carry no such caveat.

---

## 8. The cost of the fallback machinery

`FRAMING.md` §5: *a fallback to in-memory evaluation must be REPORTED, never silent.* That
machinery is not free, and it has **two** costs with three orders of magnitude between them.

### 8.1 Compile-time refusal — effectively free

`compile.py` is pure Python and runs before any statement is sent, so an `Uncompilable`
costs no database work at all. Measured over 2 000 iterations each
(`bench.py:fallback_costs`), per widget request, **not** per row:

| step | ms |
|---|---:|
| `expr.parse("days_between(today(), $.due_date)")` | 0.0085 |
| `expr.parse("$.days_left != null and $.days_left < 7")` | 0.0102 |
| `compile_ast(derive)` | 0.0028 |
| `compile_ast(where)` | 0.0050 |
| **total planning cost per request** | **0.0264** |
| detect an `Uncompilable` (`… < 1e400`) and give up | **0.0040** |

So the *decision* costs 26 µs against a Path A that costs **13.8 ms at 1 000 rows and
8 331 ms at 1 M** — between 0.19% and 0.0003% overhead. Trying to compile and failing is
cheaper than one row of Path A's `derive` (7.2 µs/row).

**The real cost of a fallback is not CPU — it is that you are back on Path A**, with Path A's
`MAX_SCAN` truncation and therefore Path A's wrong answers (§7). That is the number the gate
should look at: a fallback at 100 000 rows does not cost 0.004 ms, it costs a **38% top-50
recall**.

### 8.2 Run-time refusal — the expensive one, and `compile.py` cannot see it coming

Only **two** things make `compile.py` raise `Uncompilable`: a numeric literal that overflows
to inf, and the 200 000-character SQL cap (`compile.py:51`, `:204-210`). Verified by
compiling fourteen constructs; twelve compiled:

```
UNCOMP   1e400                    -> numeric literal overflows to inf/nan; jsonb has no representation
UNCOMP   $.a + 1e400              -> (same)
OK       round($.x, $.y)   date_add($.d, 3)   contains($.tags, 'x')   sum($.vals)
OK       string($.a) + 1   $.a.b.c[0].d       if($.a, $.b, $.c)       count($.list)
OK       avg($.a, $.b)     -$.a               not $.a
```

That is good news for coverage (finding #2's question) and **bad news for the fallback
model**, because the conformance seat confirmed a divergence that compile-time refusal cannot
catch: `KNOWN_DIVERGENCES/float8_overflow_raises` (`compile.py:73-84`, `guarded: false`) —
arithmetic that overflows a double makes **Postgres abort the whole query**, where
`expr.evaluate` returns `inf` and never raises (`expr.py:640`). The compiler emits that SQL
happily; the failure arrives mid-scan.

Probe (`proto/probe_extra.py`, table `measure_instances_poison` = the 100 000-row corpus plus
**one** record carrying `"big": 1e200`; widget `where` extended with `($.big * $.big) != 0`):

| | |
|---|---|
| `compile_ast(...)` | **succeeded** — no `Uncompilable`, no warning |
| Python (`expr.evaluate`) | `inf` — total, as documented (`expr.py:640`) |
| Postgres | **RAISED**, SQLSTATE `22003`, `value out of range: overflow` |
| rows returned | none — the whole widget fails, not one row |

The cost of that raise is **not** bounded by anything the compiler knows, and it is wildly
variable — measured on the *same query and the same table*, varying only Postgres'
`synchronize_seqscans`:

| scan start | time to the raise | what was wasted |
|---|---:|---|
| `synchronize_seqscans = on` (the **default**) | **40.8 ms** | the scan happened to start 7 pages before the poison row |
| `synchronize_seqscans = off` | **6 917 ms** | a full scan of 100 001 rows, thrown away |

A **170× spread**, decided by where another session's scan happened to leave the cursor. (This
also caught a live measurement bug in this seat's own first attempt: the initial figure of
33 ms was a synchronized-scan artifact, not a real early exit. It is corrected here rather
than reported.)

The fallback that must follow costs a **whole extra Path A**:

| | ms |
|---|---:|
| worst-case time to the raise (full scan wasted) | 6 917 |
| + Path A on the same table, afterwards | 1 494 |
| = **total for one widget refresh** | **8 411** |
| Path A alone, had pushdown never been attempted | 1 494 |
| **overhead of the failed pushdown attempt** | **+463%** |

*(Path A on `measure_instances_poison` measures 1 494 ms against 899 ms for the same 100 000
rows in the main sweep — the poison table is a fresh copy and was measured under different
cache and host-load conditions. Both numbers are reported; §10.11 covers why they differ.)*

**The conclusion for the gate is a design one, and it is cheap:** compile-time refusal is
free and can be made to cover more (refuse arithmetic whose operands are not provably in
range, or guard `+ - * /` the way `xpr.div` already guards division). Run-time refusal is
not free, is unbounded, and — per `FRAMING.md` §5 — is the *reported* half of a problem whose
*silent* half the conformance seat already found. A pushdown that ships with
`float8_overflow_raises` unguarded pays up to a full extra scan every time a tenant's data
crosses `1e154`.

---

## 9. Correctness findings this seat is obliged to report

Speed and correctness are two separate mandatory questions in the house style
(`tests/test_rag_search_pushdown.py:82-93` asserts an *identical* top-8, not a similar one).
Three correctness results came out of the measurement rig. None of them is a speed claim.

### 9.1 Where both arms answer the same question, they agree exactly

At the three sizes where Path A is not truncated (1 k, 10 k, 20 k) the two arms were compared
**row for row, field for field**, under the comparison rule mirrored from
`GIMS-Project/tests/test_dashboard_expr.py:20-25` (absolute epsilon 1e-9, booleans never
equal 0/1) — `bench.py:matches`, `rows_match`, `identity_check`:

| N | verdict | rows compared |
|---:|---|---:|
| 1 000 | **IDENTICAL** | 50 |
| 10 000 | **IDENTICAL** | 50 |
| 20 000 | **IDENTICAL** | 50 |
| 25 000 | *not comparable* — Path A truncated; the two arms are answering different questions |
| 100 000 | *not comparable* — same |
| 1 000 000 | *not comparable* — same |

That "not comparable" is the honest verdict, not a skipped test: once `truncated` is true the
arms are not computing the same function, so an identity check on them would be meaningless.
What replaces it at those sizes is §7's answer-quality measurement.

### 9.2 A stable sort and an unstable sort do not agree — a real gate item

`_apply_sort` is Python's `sorted()` (`sources.py:177`), which is **stable**: rows with equal
sort keys keep their input order. Postgres' sort is **not**. `days_left` is whole-day-valued,
so ties are dense — at N = 20 000, 1 055 rows qualify and they carry far fewer than 1 055
distinct `days_left` values, so a tie **always** straddles the `LIMIT 50` boundary.

Consequence, stated plainly: **a compiled widget with a non-unique sort key returns a
legitimately different set of rows from the in-memory widget, and neither is wrong.** The
identity results in §9.1 are only obtainable because the harness adds a deterministic
tiebreak on `$.id` to **both** arms (`bench.py:TIE`, `path_a_tiebreak`). Without it the
comparison is not well posed.

**This is not a harness artifact — it is a requirement any shipped pushdown inherits.** A
compiled `sort` needs a total order (append the record key), or the widget's page-50 answer
becomes nondeterministic across query plans. `compile.py` does not address it because `sort`
is not an expression and therefore not its job; nothing else addresses it either.

### 9.3 A silent row loss the fixture cannot reach: tolerant key resolution

`filters` and `sort.field` are **not** resolved with `expr`'s exact-key `_resolve_field`
(`expr.py:562-575`). They go through `sources._field_value` (`sources.py:67-85`), which tries
**three** strategies in order: exact key, then `core.deep_search.find_actual_key` (tolerant on
case / spaces / underscores), then a dotted path walk. `compile.py` models *expressions*, so
it has nothing to say about this — but any pushdown of `filters`/`sort` must reproduce it, and
the obvious jsonb equality does not.

Probe (`bench.py:tolerant_key_probe`, table `measure_instances_tolerant`, three records):

| record | key spelled | Path A (`_pass_filters`) | Path B (`data->'status' = '"open"'`) |
|---|---|---|---|
| `T-1` | `"status"` | kept | kept |
| `T-2` | `"Status"` | **kept** | **DROPPED** |
| `T-3` | `"status "` | **kept** | **DROPPED** |

```
"path_a_ids": ["T-1", "T-2", "T-3"],
"path_b_ids": ["T-1"],
"rows_only_python_finds": ["T-2", "T-3"],
"rows_only_sql_finds": []
```

Two of three rows vanish, **silently** — no error, no flag, just a shorter list. Under
`FRAMING.md` §5 the disqualifying direction is a null turned into a number or a raise turned
into a value; this is not that. It is the neighbouring failure: a correct answer turned into a
quietly incomplete one. It is **not** a defect in `compile.py` (filters are outside its
contract); it is a hole in the *pushdown as a whole* that a compiler-only spike does not see,
and it is the reason the SQL arm in this document must not be read as a drop-in replacement.

**Attribution, so this is not mis-cited:** the exact-key jsonb equality is *this harness's*
choice for the `filters` clause. The finding is that the obvious choice is wrong, and that the
correct one (`find_actual_key` over the row's own key set) is a per-row Python function with no
jsonb operator equivalent.

---

## 10. What is wrong with this methodology

Stated by the seat that ran it, because a number without its caveat gets misread at a gate.

1. **Every number is a warm-cache number.** Each arm is warmed once before the repetitions,
   and the host has 8 GB of page cache against a 419 MB heap for the largest table, so
   Postgres is reading from RAM throughout. `EXPLAIN (ANALYZE, BUFFERS)` shows
   `shared hit` with no `read` at every size. **A cold cache moves Path A and Path B in the
   same direction** (both must fetch the same heap pages), so the *ratios* survive; the
   *absolute* numbers are a floor, not a typical case. Untested claim, labelled as such:
   nothing here measures a cold buffer pool.
2. **Single client, no concurrency.** One connection, one query at a time, on an otherwise
   idle 20-core host. This is the regime that flatters Path A least and Path B most in one
   respect (Path B gets the whole machine and up to 2 parallel workers) and flatters Path A
   most in another (Path A's Python process never competes for CPU). A dashboard with ten
   concurrent widgets is not measured here at all, and the two paths do not degrade the same
   way: Path A's cost is per-request Python heap, Path B's is per-request database CPU.
3. **Connection setup is excluded** (7.6 ms, measured, §4). Both arms would pay it; a
   per-request-connection deployment pays it twice on a fallback.
4. **The acquisition seam is a stand-in.** `_noun_records`/`get_noun_items`
   (`sources.py:193-211`) is not in the loop — the harness issues the `SELECT` that
   `PgRecordStore.list_records` issues (`api/storage_aws.py:728-731`), skipping manifest
   resolution, the S3 shims and the legacy fallbacks in `api/iostore/nouns.py:52-120`. This
   **flatters Path A**: the measured acquisition is the fastest one that seam has.
5. **`::text` vs the driver's own jsonb decoding.** The fetch/deserialize split is obtained by
   casting to `text` and calling `json.loads` in the harness. Control measured (§5.2): the
   acquisition done exactly as `list_records` does it (`SELECT data`, psycopg2's own jsonb
   decoding) is **2% faster to 39% slower** than the split, i.e. the split systematically
   *under*-reports Path A's acquisition. The direction is stated because it matters: it makes
   every Path A number a lower bound, which is the conservative direction for §7's conclusion.
   It is still a reconstruction, not the production call.
6. **One widget, one corpus, one selectivity.** ~5.1% of rows survive `filters` + `where`.
   Selectivity is the single biggest lever on both arms and it was not varied. A widget whose
   `where` keeps 90% of rows would change Path B's sort cost and Path A's filter cost in
   opposite directions. **Untested.**
7. **Synthetic data.** 283-byte records with 5–15 arbitrary keys, seeded, uniform date spread.
   Real tenant records are not uniform; `recon/baseline.md` §6 records that no corpus of real
   tenant `DataSource` JSON exists in either tree to sample from.
8. **`ANALYZE` was run on every table.** The planner has fresh statistics, which real
   deployments do not always have. Untested: what the plan does with stale stats.
9. **Medians hide the tail.** min/max/stdev are reported for every cell, but 3–9 repetitions
   cannot describe a p99. The 1 M arm has only 3 repetitions, stated in §4.
10. **The 1 M table's GIN index was built non-concurrently and the cluster-level
    `max_parallel_maintenance_workers` was set to 0** to get past a 64 MB `/dev/shm`
    (§3). That setting affects index builds and `VACUUM`, not the query plans measured here
    (`max_parallel_workers_per_gather` was left at its default 2 and is reported in §0), but it
    is a change to a shared container and it is reverted in §11.
11. **The host was busy, and I did not record how busy during the sweep.** This is the most
    serious weakness here, found by this seat while cross-checking its own numbers. The host
    runs other work (another process was measured at 774% CPU mid-session); `uptime` right
    after the sweep read `load average: 13.64, 18.04, 15.17` on 20 cores, and the 15-minute
    figure covers the sweep window — so the sweep was **not** run on an idle machine, and no
    load figure was captured alongside each measurement. A deliberate re-run under an
    explicitly recorded load of ~14 (`probes.json → recheck`) quantifies the sensitivity:

    | | Path A | B2 | B4 | A ÷ B2 | A ÷ B4 |
    |---|---:|---:|---:|---:|---:|
    | N = 1 000, sweep | 13.8 | 57.5 | 1.1 | 0.24× | 12.1× |
    | N = 1 000, re-run at load 13.8 | 24.2 (+76%) | 87.8 (+53%) | 1.7 (+55%) | 0.28× | 14.3× |
    | N = 20 000, sweep | 300.1 | 1 138.6 | 13.2 | 0.26× | 22.8× |
    | N = 20 000, re-run at load 13.8 | 492.6 (+64%) | 1 257.0 (+10%) | 22.3 (+69%) | 0.39× | 22.1× |

    **Absolute milliseconds in this document should be treated as ±50–75%, not ±5%.** The
    *ratios* moved much less (`A ÷ B4` 22.8× → 22.1×; `A ÷ B2` 0.26× → 0.39×, the largest
    single shift), and every conclusion in §6 and §12 is a ratio or an order-of-magnitude
    claim, not a millisecond claim. **§5.5 and §7 — the answer-quality results — are counts,
    not timings, and are completely unaffected by host load.** A quiet-machine re-run is the
    single cheapest improvement anyone could make to this document.

---

## 11. Housekeeping — what this seat changed, and what it put back

**Read-only trees.** Both GIMS trees were imported/read, never written.
`GIMS-Project` @ `995cc59` and `gims-ledger` @ `7b7a049` are unchanged (verified below).
Nothing in `gims-ledger` was executed.

**Postgres.** Everything created lives in `autosql_spike` and is owned by this seat:
`measure_instances_1000`, `_10000`, `_20000`, `_25000`, `_100000`, `_1000000`,
`measure_instances_tolerant`, `measure_instances_poison`. No table belonging to another seat
was touched, and the `glp_strong` database was never opened.

**One cluster-level setting was changed and has been reverted** (verified — `SHOW` reads `2`
again and the entry is gone from `postgresql.auto.conf`):
```bash
# set during the 1 M load (64 MB /dev/shm could not host a parallel VACUUM)
docker exec glp-strong-db psql -U glp_owner -d autosql_spike \
  -c "ALTER SYSTEM SET max_parallel_maintenance_workers=0" -c "SELECT pg_reload_conf()"
# reverted at the end of this seat's work
docker exec glp-strong-db psql -U glp_owner -d autosql_spike \
  -c "ALTER SYSTEM RESET max_parallel_maintenance_workers" -c "SELECT pg_reload_conf()"
```

**`compile.py` and `runtime.sql` were not modified** — the numbers above are the prototype as
the compiler seat left it. The `xpr` runtime cost in §6 is a finding about that prototype, not
a change to it.

---

## 12. What this seat hands the `sp_decide` gate

Finding #4's job is numbers, not a verdict. These are the numbers, with the conclusions that
follow from them and nothing further.

**1. The measurement the ticket asked for, in one line.**
At 1 M rows the in-memory widget costs **8,331 ms = 8,161 ms (98%, deserializing 1,000,000
JSON records of which 980,000 are discarded unexamined) + 170 ms (2%, evaluating expressions
over the 20,000 that survived `MAX_SCAN`)**. Compiling it to SQL returns **50 rows / 16 kB
instead of 1,000,000 rows / 317 MB — 19,668× less payload**. With the prototype's `xpr`
runtime that costs **59,590 ms (7.2× slower)**; with native operators it costs **230 ms
(36.2× faster) and returns a row-for-row identical answer**.

**2. Pushdown is the right lever. This runtime is the wrong one.**
Path B as prototyped is **slower than Path A at every size measured** — 3.8× to 7.2×. The
cause is isolated and stable: one `xpr` plpgsql call costs **11.0–12.3 µs/row** against a
native equivalent at or below the measurement noise floor (0.07–0.22 µs/row) — **85× at 1 M
rows, 52×–156× across the six sizes**, with the `xpr` side constant over three orders of
magnitude of table size. **~99.6% of Path B's time is that overhead** (59,590 → 230 ms), so
plan, index and scan tuning would remove ~0.4%. B3 vs B2 demonstrates it: the GIN index cuts
`Rows Removed by Filter` from 947,673 to 546,670 and changes wall clock by **0.03%**.

**3. `MAX_SCAN` is a correctness bug that got a performance label.**
`truncated` renders as `title="Result capped for performance"`
(`frontend/lib/dashboard/widgets.jsx:277`). Measured, on the canonical widget:

| rows | qualifying rows never examined | top-50 recall | rank-1 correct |
|---:|---:|---:|:--:|
| 25 000 | 21% | 88% | yes |
| 100 000 | 80% | 38% | yes |
| 1 000 000 | 98% | **4%** | **no** |

Degradation begins at row 20 001 and is monotonic. **These are counts, not timings — they are
the only numbers here that are immune to §10.11's host-load caveat.**

**4. The cap does not even buy the memory it exists for.** `sources.py:347-351` materialises
`raw` in full *before* slicing, so Path A's peak RSS is **2 765 MB at 1 M rows** and its
Python-side work is frozen at 171 ms. The cap bounds evaluation, not allocation — which is the
opposite of the memory-exhaustion rationale written at `sources.py:57-60`.

**5. The fallback machinery is free in the direction that works and unbounded in the one that
does not.** Compile-time refusal costs **0.004 ms** (0.0003%–0.19% of Path A). Run-time
refusal — the confirmed, unguarded `float8_overflow_raises` — costs up to **a full wasted scan
plus a full Path A: +463%**, and *how much* is decided by where Postgres started its
sequential scan (**40.8 ms vs 6 917 ms on the identical query**, a 170× spread).

**6. Two correctness items that no fixture case can reach, both outside `compile.py`'s
contract and both fatal to a naive rollout:** a compiled `sort` on a non-unique key is
nondeterministic where Python's stable `sorted()` is not (§9.2), and a compiled `filters`
clause using jsonb equality **silently drops rows** that `_field_value`'s tolerant key
matching keeps — 2 of 3 in the probe (§9.3).

**7. Confidence, stated plainly.** Every ratio above is robust to the host-load problem in
§10.11 (re-measured under a recorded load of 13.8: `A ÷ B4` 22.8× → 22.1×). Every absolute
millisecond should be read as ±50–75%. The answer-quality table is exact. The single cheapest
improvement to this document is a re-run on a quiet machine; the second cheapest is varying
selectivity, which was held constant at ~5.1% throughout.


---

## Appendix A — the SQL that was actually executed

Parameterised form, verbatim from `bench.py:build_b` / `build_b4` on the 1 000-row table
(`%(name)s` are psycopg2 bind parameters; nothing is interpolated into the text).

**B1**

```sql
SELECT d.data FROM (SELECT (data || jsonb_build_object('days_left', to_jsonb((xpr.pdate_ms(nullif((data -> (%(d_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))) AS data FROM measure_instances_1000 WHERE collection = %(coll)s) d WHERE (d.data -> 'status') = %(fstatus)s::jsonb AND xpr.truthy(to_jsonb(xpr.truthy(to_jsonb(nullif((d.data -> (%(w_p0)s)::text), 'null'::jsonb) IS DISTINCT FROM NULL::jsonb)) AND xpr.truthy(to_jsonb(xpr.ord((%(w_p3)s)::text, nullif((d.data -> (%(w_p1)s)::text), 'null'::jsonb), to_jsonb((%(w_p2)s)::float8)))))) ORDER BY (CASE WHEN nullif(d.data -> 'days_left', 'null'::jsonb) IS NULL OR jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='null' THEN 4 WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='boolean' THEN 0 WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='number' THEN 1 WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='string' THEN 2 ELSE 3 END), (CASE WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='boolean' THEN (CASE WHEN nullif(d.data -> 'days_left', 'null'::jsonb)='true'::jsonb THEN 1.0 ELSE 0.0 END) WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='number' THEN xpr.f8(nullif(d.data -> 'days_left', 'null'::jsonb)) ELSE 0.0 END), (CASE WHEN jsonb_typeof(nullif(d.data -> 'days_left', 'null'::jsonb))='string' THEN (nullif(d.data -> 'days_left', 'null'::jsonb) #>> '{}') ELSE '' END) COLLATE "C" LIMIT 50
```

**B2**

```sql
SELECT (data || jsonb_build_object('days_left', to_jsonb((xpr.pdate_ms(nullif((data -> (%(o_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))) FROM measure_instances_1000 WHERE collection = %(coll)s AND (data -> 'status') = %(fstatus)s::jsonb AND xpr.truthy(to_jsonb(xpr.truthy(to_jsonb(to_jsonb((xpr.pdate_ms(nullif((data -> (%(w_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) IS DISTINCT FROM NULL::jsonb)) AND xpr.truthy(to_jsonb(xpr.ord((%(w_p3)s)::text, to_jsonb((xpr.pdate_ms(nullif((data -> (%(w_p1)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8), to_jsonb((%(w_p2)s)::float8)))))) ORDER BY (CASE WHEN to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) IS NULL OR jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='null' THEN 4 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='boolean' THEN 0 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='number' THEN 1 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='string' THEN 2 ELSE 3 END), (CASE WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='boolean' THEN (CASE WHEN to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8)='true'::jsonb THEN 1.0 ELSE 0.0 END) WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='number' THEN xpr.f8(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8)) ELSE 0.0 END), (CASE WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='string' THEN (to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) #>> '{}') ELSE '' END) COLLATE "C" LIMIT 50
```

**B3**

```sql
SELECT (data || jsonb_build_object('days_left', to_jsonb((xpr.pdate_ms(nullif((data -> (%(o_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))) FROM measure_instances_1000 WHERE collection = %(coll)s AND data @> %(fcontain)s::jsonb AND xpr.truthy(to_jsonb(xpr.truthy(to_jsonb(to_jsonb((xpr.pdate_ms(nullif((data -> (%(w_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) IS DISTINCT FROM NULL::jsonb)) AND xpr.truthy(to_jsonb(xpr.ord((%(w_p3)s)::text, to_jsonb((xpr.pdate_ms(nullif((data -> (%(w_p1)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8), to_jsonb((%(w_p2)s)::float8)))))) ORDER BY (CASE WHEN to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) IS NULL OR jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='null' THEN 4 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='boolean' THEN 0 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='number' THEN 1 WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='string' THEN 2 ELSE 3 END), (CASE WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='boolean' THEN (CASE WHEN to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8)='true'::jsonb THEN 1.0 ELSE 0.0 END) WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='number' THEN xpr.f8(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8)) ELSE 0.0 END), (CASE WHEN jsonb_typeof(to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8))='string' THEN (to_jsonb((xpr.pdate_ms(nullif((data -> (%(s_p0)s)::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms((%(ctx)s)::jsonb), true)))) / 86400000.0::float8) #>> '{}') ELSE '' END) COLLATE "C" LIMIT 50
```

**B4**

```sql
SELECT data || jsonb_build_object('days_left', to_jsonb((((data->>'due_date')::date - DATE '2026-08-19')::float8))) FROM measure_instances_1000 WHERE collection = %(coll)s AND (data -> 'status') = %(fstatus)s::jsonb AND (data ? 'due_date') AND (((data->>'due_date')::date - DATE '2026-08-19')::float8) < 7 ORDER BY (((data->>'due_date')::date - DATE '2026-08-19')::float8) LIMIT 50
```

Bind values for B2: `coll='noun:Sample'`, `ctx='{"now": "2026-08-19T12:00:00Z"}'`, `fstatus='"open"'`, and the compiler's own literals (`'due_date'`, `7.0`, `'<'`).
