## Cross-cutting B — `filters`, `sort` and `limit`: the half of the question with no evidence

*(Closure pass; closes critic gaps 4 and 15. Every number is re-derived from a raw spike artifact or measured
this pass by a read-only re-check of an existing instrument. Nothing below is fixed — FRAMING §3 forbids it;
each defect is recorded with cause, blast radius and direction.)*

*(**Compliance** — extended here to the form `f2`, `xd` and `f5` use. **[consistency 23]** Read-only throughout:
both GIMS trees, `proto/`, `analysis/`, `recon/`, `FRAMING.md`, `.autodev/` and `kb/` were read and not written;
the only file written is this one. Every SQLite connection carries `mode=ro&immutable=1` (B.4, and the
re-derivation in the unit note below). No defect is fixed and no grammar redesigned. **What is attestable and what
is not:** the committed instrument re-run in B.6, `proto/idxshape_sort_semantics.py`, was verified this pass to
contain no `CREATE`/`ALTER`/`DROP`/`INSERT`/`UPDATE`/`DELETE` — `SELECT`-only against the scratch db
`autosql_spike`, so no Postgres object was created, altered or dropped and nothing required rolling back. The
one-off `::jsonb` probes reported in B.4-B.6 ran in the session scratchpad and were **not retained**, so their
read-only character rests on this attestation rather than on an artifact a reader can open; the scratch db
`autosql_spike` is the spike's own, not `glp_strong` (FRAMING §7).)*

*(**Punch pass addendum. [punch]** The `[punch]`-marked edits in B.4 were made in a later pass whose only writes
were to this file. That pass re-censused all three `gims-ledger` stores read-only — `sqlite3.connect("file:…?
mode=ro&immutable=1", uri=True)`, `SELECT count(*)` / `SELECT collection, count(*)` / `SELECT data` only, no
`-wal` or `-shm` opened — and re-read the spike's own retained sweep output `xd_sweep.json` from the earlier
session's scratchpad. `core/deep_search.py`'s `_norm_key` was imported from `GIMS-Project` as the oracle, exactly
as the original census did; that import reused the **pre-existing** `core/__pycache__/deep_search.cpython-312.pyc`
(mtime **2026-06-26**) and **no `.pyc` in either GIMS tree carries an mtime inside this pass's window** — both
trees hold only the pre-existing dirty entries `xd` D.11 records. **No Postgres connection was opened at all**,
nothing was written to any database, and no defect was fixed (FRAMING §3); the working script lives in the session
scratchpad, outside the repository. **What this pass could not re-verify, said plainly:** the **14:16:56** mtime in
B.4 is the checkpoint's own timestamp, read live while it was still that store's last checkpoint — `guts-ledger`
has since been checkpointed again (mtime **16:15:17**), so it is no longer re-readable from the file. What this
pass did verify independently brackets it on both sides: `xd_sweep.json` holds `LedgerRecord` 17 145 and was
written at 14:16:57, and `xd` D.1's 14:20 read holds 17 148.)*

### B.1 Why this section exists

FRAMING §1 asks whether `sources.py` can push **`derive` / `where` / `sort` / `limit`** into the database.
`derive` and `where` reduce to `expr` evaluation and are the subject of findings 1–2. **`filters` and `sort` do
not**: their semantics live outside `expr.py`, in three helpers in `GIMS-Project/api/dashboard/sources.py`. f2's
census is a census of `expr.py`'s grammar (f2 §2.1: 48 constructs) and contains none of them. Measured this pass
(`grep -c` over `.parts/f1.md…f5.md`): `_pass_filters` **0 hits in all five sections**, `find_actual_key` **0 in
all five**, `_field_value` 0/0/0/**1**/0, `_sort_key` 0/0/3/3/1. Over the prototype, `proto/compile.py` has
**0** hits for `filters`, `limit`, `_field_value`, `find_actual_key`, `derive` (its one `sort` hit,
`sorted(params.items())` at `compile.py:453`, is unrelated), and `proto/conformance.py` /
`proto/coverage_probe.py` have 0 for all four. **Nothing in the prototype models `filters` or `sort`;**
`bench.py` hand-writes one `filters` clause and one sort emulation for one widget, and nothing tests either.

### B.2 The exact semantics, as written

**`_field_value(row, key)` — `sources.py:67-85`.** Total, never raises. `:70-71` non-dict row or non-str key →
`None`; `:72-73` **exact** key → `row[key]`; `:74-76` else `find_actual_key(row, key)` — **tolerant**, first hit
wins; `:77-84` else, if `"." in key`, walk the dotted path, any miss → `None`; `:85` else `None`.
`find_actual_key` (`core/deep_search.py:29-39`) iterates `obj.keys()` **in dict order** and returns the first
`k` with `_norm_key(k) == _norm_key(desired)`; `_norm_key` (`deep_search.py:19-26`) is `str(k).lower()` with
every `" "`, `"_"` and `"-"` deleted.

**`_pass_filters(row, filters)` — `sources.py:88-96`.** Conjunctive; each `key → want` fails the row if
`_field_value(row, key) != want` (`:94`) — **Python `!=`, on Python objects**. Absent/empty `filters` passes
(`:91-92`); a missing field yields `None`, so it fails unless `want is None`; non-Mapping `filters` → 400
`DASHBOARD_FILTERS_INVALID` (`:153-155`).

**`_sort_key(value)` — `sources.py:99-115`.** A 3-tuple `(rank, float, str)` giving a total order that never
compares across types. Re-derived this pass: `False`→`(0,0.0,'')`, `True`→`(0,1.0,'')` (rank 0 = bool);
`2.5`→`(1,2.5,'')`, `5`→`(1,5.0,'')` (1 = number); `'Zebra'`→`(2,0.0,'Zebra')`, `'apple'`→`(2,0.0,'apple')` (2 =
string); `[1,2]`→`(3,0.0,'[1, 2]')`, `{'a':1}`→`(3,0.0,"{'a': 1}")` (3 = other, **keyed on Python `str()`**);
`None`→`(4,0.0,'')` (4 = null last).

**`_apply_sort` — `sources.py:168-177`.** Key is `_sort_key(_field_value(r, str(field)))` — **the sort field
goes through the same tolerant resolution as a filter**. `dir` is matched case-insensitively against `"desc"`
(`:176`); everything else ascends. `sorted(..., reverse=descending)` is **stable both directions**: measured,
five rows tied on the key return `r0…r4` for `asc` *and* `desc` — the fact `bench.py:385-389` states, and the
reason the bench bolted a `TIE` column (`bench.py:178-179`) onto every arm before rows could be compared.

**`_apply_limit` — `sources.py:180-187`.** `int(limit)`; `TypeError`/`ValueError` → **all rows**; `n < 0` →
**all rows**; else `rows[:n]`. Measured on 5 rows: `None`→5, `2`→2, `0`→0, `-1`→**5**, `"3"`→**3**,
`"abc"`→**5**, `2.9`→**2**, `True`→**1**. Pipeline order is fixed at `sources.py:353-356` (derive → filter →
sort → limit) over rows already truncated to `MAX_SCAN = 20_000` at `:348-351`.

### B.3 `filters`: the tolerant-key divergence — verified, cause, blast radius

**Verified.** `analysis/measurements.json → tolerant_key_probe` reproduces. Three records —
`{"id":"T-1","status":"open",…}`, `{"id":"T-2","Status":"open",…}`, `{"id":"T-3","status ":"open",…}` — under
`filters: {"status":"open"}`: Path A (Python `_pass_filters`, `sources.py:88`) returns `["T-1","T-2","T-3"]`;
Path B (compiled `(data -> 'status') = %(fstatus)s::jsonb`, `bench.py:226`) returns `["T-1"]`; `agree: false`,
`rows_only_python_finds: ["T-2","T-3"]`, `rows_only_sql_finds: []`. Re-derived independently by calling
`_pass_filters` directly: `T-1/T-2/T-3` all `True`, `_field_value` returns `'open'` on all three, `"status" in
row` **false** for T-2 and T-3.

**Cause.** `_field_value` stage 2 (`sources.py:74`) → `find_actual_key` → `_norm_key`. The SQL is exact-key by
construction; `bench.py:352` says so in a comment (*"compile.py models expressions only, so a compiled `filters`
clause is EXACT-key"*). Not a `compile.py` bug — `compile.py` never claimed `filters`. It is **a clause with no
compiler at all, whose obvious one-line pushdown is silently wrong**. **Direction: silent, toward
under-reporting** — SQL returns a strict subset; the widget shows fewer rows and no error. Under FRAMING §5 and
the §4 NO-GO bar that is disqualifying for a `filters` pushdown. It was never scored: no harness in this spike
has a `filters` case.

**Blast radius.** `_norm_key` lowercases and deletes ASCII space, `_`, `-`. Measured against desired key
`status`: **matched** (SQL exact-key misses each) — `Status`, `STATUS`, `status `, ` status`, `stat us`,
`st-atus`, `st_atus`, `s_t-a t u s`, `Status_`, `-Status-`; **not matched** — `statu\ts`, `statu\ns`
(tab/newline are not stripped), `státus`, `ｓｔａｔｕｓ` (no Unicode folding). The trigger set is exactly **any
difference in ASCII letter case, spaces, underscores or hyphens** — `run_ID` vs `run id` vs `runid` vs `RunID`,
the normal spelling drift of tenant-authored column names. GIMS treats it as **contract, not accident**:
`tests/test_dashboard_sources.py:169-177` (`test_tolerant_and_dotted_field_access_in_filters`) asserts `filters:
{"sample_id": "S-1"}` matches a record keyed `"Sample ID"`, and `filters: {"nested.ph": 6.9}` resolves a dotted
path — so a pushdown that drops tolerant matching breaks a locked upstream test.

### B.4 `filters`: tolerant matching is *ambiguous*, and the ambiguity is in real data

`find_actual_key` returns the **first** key in dict-iteration order that normalises to the target, so when two
keys of one record normalise the same, the answer depends on JSON key order — measured:
`{"Status":"open","status_":"closed"}` → `_field_value(row,"status")` = `'open'`, the same two keys inserted in
the other order → `'closed'`. Not hypothetical; read-only census of the live ledger stores
(`gims-ledger/projects/*/objects.db`, `mode=ro&immutable=1` — the instrument `analysis/index-shape.md §1.2`
already used):

| store / table | dict rows | rows with ≥1 key where `_norm_key(k) != k` | **rows with two keys normalising the same** |
| --- | --- | --- | --- |
| `guts-ledger/instances` | **17 345** *(17 342 one checkpoint earlier; see the unit note)* | 17 345 (100%) | **4 166 (24.0%)** |
| `guts/instances` | 12 095 | 12 095 (100%) | **1 966 (16.3%)** |
| `guts-code/instances`; the three `*_verb_log` tables | 6 710; 197 / 288 / 196 | 100% | 0 |

*(Unit, because the body carries four different ledger row counts: these are **table-wide** — every collection in
that store's `instances` table, **not** `LedgerRecord` alone — whereas `xd` D.2 counts the same bytes per
`(table, collection)`. They reconcile by summation, re-derived read-only this pass with the same
`mode=ro&immutable=1` instrument: `guts` = `Vector` 6 821 + `LedgerRecord` 5 186 + `WorkOrder` 83 + `Repo` 5 =
**12 095** and `guts-code` = `Vector` 6 705 + `Repo` 5 = **6 710**, matching this table exactly; `guts-ledger` =
`LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345**, exactly — that store holds **no `Repo` collection**,
both of `xd` D.2's two `Repo` ×2 (5·5) sitting in `guts` and `guts-code` and already consumed by those two sums.
`xd`'s 17 148 and this table's 17 345 are two units, not two measurements of one number.* **[consistency 12]**

*(Correction, same marker; re-derived at the punch-list pass. **[punch]** The figure first published here was
**17 342**, and the two claims made about it in the earlier draft — that a writer *"cannot move an `immutable=1`
count in either direction"*, and that 17 342 is *"superseded and unexplained"* — are **both withdrawn as
over-claims**. `immutable=1` ignores the live `-wal` and reads the **main db file only**; it does not follow that
the count is fixed. It moves — **exactly when a checkpoint lands**, rather than continuously with the writer — and
one did. **17 342 is fully explained: it is this same table, read one checkpoint earlier.** Re-derived this pass
from the spike's own retained sweep output `xd_sweep.json` (same `mode=ro&immutable=1` instrument, `xd` D.1):
`guts-ledger`/`instances` held `LedgerRecord` **17 145** + `WorkOrder` **197** = **17 342**, the published figure
exactly, and `xd` D.1's 17 145 is that same pre-checkpoint state. The `guts-ledger` main file was then
checkpointed (mtime **14:16:56**, read live before the store was next checkpointed — bracketed by
`xd_sweep.json`'s 14:16:57 write, which still holds 17 145, and `xd` D.1's 14:20 read, which does not), and that
**single event** moved the table to `LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345**. It is the *same*
event behind `xd` D.1's own pair, 17 145 at 14:14 → 17 148 at 14:20 — one checkpoint, two sections, one
explanation. Neither `guts` nor `guts-code` moved across those two reads — their sums in the note above are
identical to `xd_sweep.json`'s — which is what a checkpoint-driven rather than writer-driven count predicts.)*

*(The corrected figure, stated once so a citation can be checked against it. **[punch]** **`guts-ledger`/`instances`
is 17 345 = `LedgerRecord` 17 148 + `WorkOrder` 197, the whole table as of the 14:16:56 checkpoint, and the
collision rate is 4 166 / 17 345 = 24.02 %.** `f5` §5.4(3) quotes "4 166 of 17 342 rows (24.0%)"; the numerator and
the percentage are unchanged, the denominator should read **17 345**. **It is a snapshot, not a standing property
of the store,** and the earlier draft's error was to treat it as one: a read-only re-census at **16:21:55** this
pass — after a further checkpoint, main-file mtime **16:15:17** — returns **17 398** (`LedgerRecord` 17 199 +
`WorkOrder` 199) for the same table and **12 109** for `guts`. Cite 17 345 against its checkpoint; a reader who
re-runs later will get a larger denominator. **What does not move is the numerator:** the colliding-row count is
**4 166**, **1 966** and **0** at every read taken, so the 56 rows `guts-ledger` and the 14 rows `guts` gained
between the first and last of them added **none** — the pair is `run_id` / `_runID` in every one of the 4 166 and
1 966, and all rows still decode to dicts (0 non-dict, 0 parse failures, re-measured on all three stores at
16:21:55). The published **24.0 %** and **16.3 %** belong to the 17 345 and 12 095 denominators; against the
16:21:55 ones the same numerators read 23.9 % and 16.2 %.
**No finding in B.3–B.10, no obligation in B.8 and no verdict changes.**)*

The colliding pair is the same in both: **`run_id` and `_runID`, both → `runid`**, holding *different values*
(first such row: `run_id = ""`, `_runID = "one-body-phase-1"`). A tenant filter or sort on `runID` / `run id` /
`RunID` / `RUN_ID` resolves through `find_actual_key` and gets whichever comes first. Which one comes first is
**a property of the store, not of the record** — measured, one record, one `_field_value(row, "runID")` call:
via SQLite TEXT → `json.loads` (today's path) the keys arrive `['run_id','_runID']` and it resolves to `run_id`
= `''`; via Postgres `jsonb` → `::text` → `json.loads` they arrive `['_runID','run_id']` and it resolves to
`_runID` = `'one-body-phase-1'`. Cause: `jsonb` does not preserve object key order — it stores keys sorted by
length then bytewise (measured: `{"run_id":…,"_runID":…,"zz":…,"a":…}::jsonb` enumerates `a, zz, _runID,
run_id`), while `json.loads` preserves document order. **Moving the store to `jsonb` changes the answer of the
existing Python path on 4 166 real rows, with no pushdown involved.** Direction: silently different value,
either way, no error.

*(Scope, INFERENCE: these are ledger `instances`, not a `Sample` noun collection; whether a production
`DataSource` targets a collection holding this pair is **not established by this spike** — that needs the
`DataSource` corpus f2 §2.9 records as absent. What **is** established: the collision occurs in real stored GIMS
records at 24.0% and 16.3%.)*

### B.5 `filters`: the value comparison diverges too, independently of the key

`_pass_filters` compares with Python `!=` on Python objects (`:94`); any pushdown compares with jsonb `=`. Two
further silent divergence classes follow, neither compiled nor fallback-ruled — **Python's `bool`/`int`
identity** (`1 == True`, jsonb rejects) and **missing-key vs explicit-null** (Python keeps the row, SQL drops
it). Both sides measured this pass:

| case | Python `_pass_filters` | SQL `(data->'k') = <lit>::jsonb` | agree |
| --- | --- | --- | --- |
| row `{"v":1}`, `filters {"v": true}` | **True** (`1 == True`) | **false** | **no** |
| row `{"v":true}`, `filters {"v": 1}` | True | false | **no** |
| row **without** `k`, `filters {"k": null}` | **True** (`None != None` is false) | **false** (`NULL = 'null'` → NULL) | **no** |
| controls: `{"v":1}`/`1.0`; `{"v":"1"}`/`1`; `{"k":null}`/`null` | True / False / True | true / false / true | yes |

### B.6 `sort`: the ordering mismatch — both orderings, and every place they differ

`proto/idxshape_sort_semantics.py`, re-run unchanged this pass against the live container (PostgreSQL 16.14, db
`autosql_spike`), reproduces f3 §3.6 H4 exactly:

```
sources.py _sort_key ascending : [false, true, 2.5, 5, "Zebra", "apple", [1, 2], {"a": 1}, null]
jsonb btree ascending          : [null, "Zebra", "apple", 2.5, 5, false, true, [1, 2], {"a": 1}]
SAME ORDER? False
```

Position by position — `_sort_key` vs `jsonb` — `0: false/null · 1: true/"Zebra" · 2: 2.5/"apple" · 3: 5/2.5 ·
4: "Zebra"/5 · 5: "apple"/false · 6: [1,2]/true · 7: {"a":1}/[1,2] · 8: null/{"a":1}`. **9 of 9 positions
differ.** The orders are `_sort_key` (`:105-106`) **bool < number < string < other < null-last** versus `jsonb`
B-tree (f3 §3.6) **null < string < number < bool < array < object**. They agree only on a
column uniformly one JSON type and non-null, which nothing in GIMS enforces: `_sort_key`'s docstring at
`:104-106` exists because columns *do* mix types, and `tests/test_dashboard_sources.py:182-188`
(`test_sort_never_crashes_on_mixed_bool_and_container`) locks a column mixing `True`, `[1,2]`, `{"k":1}`, `"x"`
and a missing key.

**A rank-triple emulation is possible but partial.** `bench.py:94-101` `sort_sql()` does emit the triple in SQL
(`CASE` on `jsonb_typeof` for ranks 0/1/2/4, `xpr.f8` for the numeric slot, `#>> '{}' COLLATE "C"` for the
string slot). Its own comment at `bench.py:91-92` records the hole: **rank 3 (list/dict, keyed on Python `repr`)
is NOT compilable**, and the harness asserts the corpus never produces it rather than handling it. Measured —
`_sort_key`'s rank-3 slot (Python `str()`) vs `jsonb::text`: **agree** on `[1,2]`, `[]`, `{}`, `[1.0]`;
**disagree** on `{"a":1}` (`{'a': 1}` vs `{"a": 1}`) and `["x"]` (`['x']` vs `["x"]`) — quote style; on
`[true,null]` (`[True, None]` vs `[true, null]`) — Python literals; and on `{"z":1,"a":2}` (`{'z': 1, 'a': 2}`
vs `{"a": 2, "z": 1}`) — jsonb reorders keys. That last case is unfixable in principle: rank-3
ordering depends on **document key order**, which `jsonb` destroys (B.4), so a container-valued sort column is
**uncompilable**, not just uncompiled.

Two further `sort` properties no arm reproduces. **(1) Stability** — `sorted()` at `:177` is stable both
directions, Postgres' sort is not, so `bench.py` added `TIE = ", data->>'id' COLLATE \"C\""` (`:178`) to every
SQL arm *and* mirrored it into the Python reference (`:399-400`): **the comparison that produced f4's numbers
deliberately changed both sides' sort to make them comparable**. Recorded prose-only at `analysis/measurement.md
§9.2`; f4 §4.11 confirms **no record in `measurements.json` or `probes.json`**. **(2) Tolerant resolution** —
`:177` calls `_field_value`, so every defect in B.3–B.5 applies to the sort field; `bench.py`'s arms sidestep it
by sorting on an *inlined derive expression* (`bench.py:218`, `sort_sql(d_sql_sort)`), never on a
tolerantly-resolved stored key.

### B.7 `limit`: inherits, and adds nothing of its own

`LIMIT n` is trivially compilable but **only well-defined relative to a total order**, so it inherits every
defect in B.6: with 9 of 9 positions differing, `LIMIT 50` over a mixed-type column picks a different 50 rows,
silently. It also inherits B.3–B.5 via the `filters` setting the candidate list, and its own coercions (B.2) must
be replicated *before* emitting SQL — `"abc"` and `-1` mean **no `LIMIT` clause**, not `LIMIT 0`.

### B.8 What a pushdown of each clause must reproduce — and its status

"Compiled" = emitted by `proto/compile.py`; "tested" = scored in `proto/conformance.py` / `coverage_probe.py`
under FRAMING §8's three-outcome rule; "fallback ruled" = a named, query-time-detectable fallback (FRAMING §4 #2).

| # | Obligation | Source | Compiled | Tested | Fallback ruled |
| --- | --- | --- | --- | --- | --- |
| 1 | exact-key lookup | `:72-73` | no (hand-written in `bench.py:226` only) | no | no |
| 2 | tolerant key match (case/space/`_`/`-`, first wins) | `:74-76`, `deep_search.py:19-39` | **no** | **no** | **no** |
| 3 | first-wins tie-break under document key order | `deep_search.py:36-38` | no — **input destroyed by `jsonb`** (B.4) | no | no |
| 4 | dotted-path fallback | `:77-84` | no | no | no |
| 5 | Python `!=` value semantics (`1 == True`; missing vs null) | `:94` | no | no | no |
| 6 | 5-rank order `bool<num<str<other<null` | `:99-115` | partial — `bench.py:94-101`, ranks 0/1/2/4, one widget | no | no |
| 7 | rank-3 key = Python `repr` of the container | `:115` | **no — uncompilable** (B.6) | no | no |
| 8 | stable sort in both directions | `:177` | no — bench *replaced* it with a tiebreak on both sides | no | no |
| 9 | sort field resolved via `_field_value` (so 1–4 recur) | `:177` | no | no | no |
| 10 | `limit` coercion (`"3"`→3; `"abc"`/`-1`→unlimited) | `:180-187` | no | no | no |
| 11 | `filters`/`sort` spec validation → 400 | `:153-155`, `:171-172` | n/a | n/a | n/a |

**Ten substantive obligations (1–10). Zero emitted by `proto/compile.py`, zero tested, zero fallback-ruled.**
**[consistency 18]** — stated precisely, because two rows of the table above do carry SQL: "compiled" here means
*emitted by `proto/compile.py`*, per this section's own definition, and by that definition the count is exactly zero.
The SQL that exists for obligations 1 and 6 is **hand-written in `bench.py` for one widget, outside the compiler**:
row 1's exact-key `filters` clause (`bench.py:226` — which B.3 measures dropping 2 of 3 rows) and row 6's partial
rank-triple sort (`bench.py:94-101`, ranks 0/1/2/4, rank 3 excluded by its own comment at `:91-92`). Neither is
scored by any harness, so **zero tested** and **zero fallback-ruled** hold literally for all ten. Obligations 3 and 7
additionally carry a positive argument that they *cannot* be compiled, not merely that they have not been.

### B.9 GAP 15 — `derive` chaining and shadowing

`_apply_derive` (`sources.py:133-148`) compiles each expression once over `derive.items()` (`:142` — **mapping
insertion order**), then per row does `row[name] = evaluate(...)` (`:147`), **writing back into the row being
iterated**. Docstring `:135-136`: *"later derives can reference earlier ones."* Re-checked this pass through the
existing Python path, on row `{"id":"S-1","due_date":"2026-08-21","priority":2}` with `ctx.now =
2026-08-19T12:00:00Z`:

| # | `derive` mapping | result |
| --- | --- | --- |
| A | `days_left`; `urgent: "$.days_left < 7"`; `score: "$.days_left * $.priority"` | `days_left=2.0, urgent=True, score=4.0` — **chaining works, two levels deep** |
| B | the same two entries in **reverse** order | `urgent=None, days_left=2.0` — **silently wrong, no error** |
| C | `priority: "$.priority * 10"` (shadows a stored key) | stored `priority: 2` **overwritten** with `20.0` |
| D | C, then `p2: "$.priority"` | `p2 = 20.0` — a later derive reads the **shadowed** value |
| E | `x: "1"` | the caller's row object is **mutated in place** (`res[0] is r` → `True`) |

No measured arm exercises any of this: f4 §4.3's four arms (B1 faithful, B2 inlined, B3 containment, B4 native)
all handle the **single** derive `days_left` (`bench.py:32-39`); f2's census is per-expression with no notion of
inter-derive dependency; f3's predicates are single-expression. Consequences a pushdown must carry: **(1) order
is semantic** — the compiler must preserve the JSON object's key order, and case B yields `null` rather than an
error when it is lost, the same class as FRAMING §5's non-negotiable; note the collision with B.4, since a spec
round-tripped through a `jsonb` column loses that ordering. **(2) shadowing is legal**, so a compiled `$.k` must
bind to the *derived* `k` when an earlier derive defined it and the stored `k` otherwise — a scoping rule
`compile.py` has no representation for (`column=` names one jsonb source, `compile.py:15-17`). **(3)** B1's
`data || jsonb_build_object(name, …)` (`bench.py:204`) composes by nesting in principle and B2's `subst()`
(`bench.py:216`) inlines one derive into `where`, but **whether either composes correctly for n ≥ 2 derives, and
survives shadowing, is not established by this spike.** What would establish it: a two-derive widget where
`derive2` reads `$.derive1`, plus a third shadowing a stored key, run through `proto/conformance.py`'s existing
three-outcome scorer against `sources._apply_derive` as oracle. That is new machinery; FRAMING §3 forbids
building it here.

### B.10 What this does to the spike's headline

f1 §1.2 reports **130/130** fixture cases `COMPILED_AGREES` (`proto/results.json`). That number is sound, and a
statement about **`expr` evaluation only** — about `derive` and `where`. `tests/fixtures/expr_vectors.json` holds
130 cases with keys `{expr, record, context, expect, group, name}` and **zero** occurrences of `sort`, `filters`
or `limit` (measured this pass). It cannot speak to two of the four clauses, and no other harness here does.

- **130/130 covers `derive` and `where`. It says nothing about `filters`, `sort` or `limit`.**
- On `filters`, the only pushdown anyone actually wrote **silently dropped 2 of 3 rows** on plain ASCII keys
  (B.3). On `sort`, the natural index-backed order disagrees with the Python order at **9 of 9 positions** (B.6).
  `limit` is meaningful only under a matching order and has neither.
- Under FRAMING §4 — *"NO-GO if any case diverges **silently**… One silently-wrong number is disqualifying on
  its own"* — B.3, B.5 and B.6 are each disqualifying **for a pushdown of that clause**. They do not touch f1's
  `expr` result, nor by themselves decide the verdict `f5` reaches (`f5` recommends **NO-GO**); they do establish
  that **any named subset cannot include `filters` or `sort` on the present evidence**, and that shipping either
  without obligations 1–10 of B.8 would breach FRAMING §5 on data that exists today. **[consistency 3]**

### B.11 Not established by this spike

| question | status | what would establish it |
| --- | --- | --- |
| Does any production `DataSource` use `filters`, or `sort` on a mixed-type / colliding key? | not established — no `DataSource` corpus (f2 §2.9) | read the deployed dashboard specs; count clause usage |
| Can tolerant matching be compiled at all (e.g. a normalised-key expression index)? | not established — obligation 3 has an impossibility argument, obligation 2 does not | compile a `jsonb_each` + `_norm_key` lateral and score it three-outcome |
| Does `bench.py`'s rank-triple emulation agree with `_sort_key` over mixed types? | not established — never scored; only asserted absent from one corpus (`bench.py:91-92`) | run it as a conformance battery over a mixed-type column |
| Does derive chaining compile for n ≥ 2, and under shadowing? | not established (B.9) | two-derive + shadowing widget through `proto/conformance.py` |
| How large is the SQL-vs-Python sort instability? | not established — prose-only, `measurement.md §9.2`, absent from raw per f4 §4.11 | re-run one arm without `TIE` and diff the returned id lists |
