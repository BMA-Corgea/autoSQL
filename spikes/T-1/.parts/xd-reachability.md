## Cross-cutting D — is any of this reachable from real GIMS data?

Closes `critic.md` §5. **`f1` §1.11 item 6** — "whether any of D1–D23 is reachable from real GIMS dashboard
data… every witness is a constructed record", declared **not established** there, and now carrying a forward
pointer to this section instead **[punch]** — together with `f2` §2.9 and `f4` §4.1/§4.11, declared the same
gap independently — while `index-shape.md:113-126` records that a real 17,087-row `LedgerRecord` collection was opened
read-only *during this spike*. This pass asks those questions of that corpus and every other real corpus here.

**What this pass is, labelled exactly [consistency].** It is **a new read-only instrument, built this pass**
(`xd_sweep.py`, §D.1), **cross-checked against `json_tree`** — not a re-read of artifacts that already existed.
It reads only: no compiler run, no Postgres connection, no write to any file in either GIMS tree, no fix
(FRAMING §3, attested §D.11). The earlier draft called this "a read-only sweep, not a new experiment"; the
*read-only* half is true and attested, the *not a new experiment* half was a stretch and is withdrawn. Nothing
is fixed and nothing is written, so no stop rule is touched — but the instrument is new, and a reader weighing
§D.3–§D.6 is weighing an instrument built here, whose only independent check is the `json_tree` agreement in
§D.1. It matters because `f1` §1.9.3 breaches FRAMING §4's bar *outside the fixture*, and a bar tripped only by
inputs no production writer can generate is a different fact from one tripped by ordinary tenant data.

### D.1 Method and the read-only guarantee

Every database opened `sqlite3.connect("file:<path>?mode=ro&immutable=1", uri=True)` — the form
`index-shape.md:1271` used. Two independent instruments over the same bytes, so a defect in one is visible against
the other (FRAMING §8). **W** — Python walker (`…/scratchpad/xd_sweep.py` → `xd_sweep.json`):
`json.loads(txt, parse_float=FNum, parse_int=INum)` captures the **raw number literal** of every scalar, then
recurses over the decoded tree classifying every value and key. **T** — SQLite `json_tree`, no Python in the path:
`SELECT count(*), max(abs(t.value)) FROM instances i, json_tree(i.data) t WHERE t.type IN ('integer','real')`.

**They agree exactly.** W: **5,236,427** numeric JSON nodes. T: **5,235,942** over `instances` only. The
difference, **485**, is precisely the numeric nodes W found in the `*_verb_log` tables T did not scan
(`guts_verb_log` 289 + `guts-code_verb_log` 196) — an instrument miscount of the kind FRAMING §8 warns about
would not produce that identity.

**One honest complication:** `guts-ledger/objects.db` is being written *by another process* during this session
(AutoDev's own ledger) — `LedgerRecord` read 17,145 at 14:14 and 17,148 at 14:20 — and `immutable=1` **ignores
the `-wal`**; both effects are quantified in §D.8.

### D.2 The corpus — what actually exists here

Every `objects.db` / `archive.db` under `gims-ledger/projects/` and `GIMS-Project/projects/`. Counts are per
`(table, collection)`, the unit `sources.py` scans (§D.7).

| tree · project | collection | rows | vs `MAX_SCAN` = 20,000 |
| --- | --- | ---: | --- |
| gims-ledger · guts-ledger | `LedgerRecord` | **17,148** | **85.7 %** |
| gims-ledger · guts | `Vector` | 6,821 | 34.1 % |
| gims-ledger · guts-code | `Vector` | 6,705 | 33.5 % |
| gims-ledger · guts | `LedgerRecord` | 5,186 | 25.9 % |
| gims-ledger · guts, guts-ledger, guts-code | `verb_log` ×3 (289·197·196) · `WorkOrder` ×2 (197·83) · `Repo` ×2 (5·5) | 972 | ≤ 1.4 % |
| GIMS-Project · LIMS-System | 18 collections, largest `Star Spirit Lore` 68, smallest 1 | **222 total** | ≤ 0.34 % |
| GIMS-Project · LIMS-System | **`Submission`** — the one real dashboard's source (one of the 222) | **7** | 0.04 % |
| GIMS-Project · LIMS-System | `archive.db` `noun_Sample`; 3 other `noun_*` + `instances` are empty | 28 | — |

**Swept: 37,078 rows · 5,236,427 numeric nodes · 495,115 string values.** `DurationDemo` (0 bytes), `RunlogTest`
and `Sterility` hold 0 rows in both trees. `gims-ledger/projects/LIMS-System/` has `noun_types.json` (98 declared
fields, `index-shape.md:1003`) but **no `objects.db`** — those 98 fields have zero rows here. **Excluded and
named:** 91 backup snapshot dirs under `gims-ledger/backups/*/*/` + 67 under `GIMS-Project/backups/*/*/`,
historical copies of LIMS-System whose live originals are above.

**How the table adds to 37,078 — the reconciliation, stated because it does not close as printed [punch].** The
table is a census read at 14:20; the **Swept** totals are the sweep's own read (`xd_sweep.json`, re-aggregated
read-only for this pass). Three details separate them, each verified against that file. **(i)** The sweep counted
`guts-ledger` · `LedgerRecord` at **17,145**, not the 17,148 in the table — the §D.1 concurrent writer, +3 in six
minutes; 85.7 % of `MAX_SCAN` either way. **(ii)** The `verb_log` group names three logs and omits a fourth,
`LIMS-System_verb_log`, **27 rows**, which *was* swept: four logs totalling 709 rows, not three totalling 682.
**(iii)** The 28 `archive.db` `noun_Sample` rows were **not** swept — that table is column-per-field (`_rowid`,
`_runID`, `image`, `received_date`, …) rather than a `data` JSON blob, so `xd_sweep.py` skipped it; that is what
the "—" in its `MAX_SCAN` column means, and it is why the row is listed but adds nothing. Corrected, it closes
exactly: 17,145 + 6,821 + 6,705 + 5,186 + 280 (`WorkOrder` ×2) + 10 (`Repo` ×2) + 222 (LIMS `instances`) =
**36,369 `instances` rows**; 289 + 197 + 196 + 27 = **709 `*_verb_log` rows**; **36,369 + 709 = 37,078**. The
published total is right; the table's legs were not printed in a form a reader could add.

### D.3 Q1 — does any stored number reach the 297-digit guard (D1–D5)?

D1–D5: every finite double with `|v| ≥ 1.797693e+296` is mishandled by `xpr.f8`, and 16 of 16 `f8`-reachable paths
diverge (`f1` §1.9.2 rows **D5** and **D1** **[punch]**, `fuzz/A_f8_guard.txt` §A2/§A3). Instrument T, run per database:

```sql
SELECT count(*) FROM instances i, json_tree(i.data) t
WHERE t.type IN ('integer','real') AND abs(t.value) >= 1.797693e296;
```

| | |
| --- | ---: |
| numeric nodes examined (T, `instances`) | 5,235,942 |
| **rows matching `abs(v) >= 1.797693e296`** | **0** |
| rows matching the one-decade-early tripwire `abs(v) >= 1e290` (W) | **0** |
| **largest `abs(v)` in the whole corpus** | **1,787,169,706,037** (≈1.787e+12) |
| where | `$.payload.blocked_since`, `LedgerRecord` key `52580851-018e-422a-ab38-a479ea6f3bed` — epoch **ms** |

**0 rows matched; the query is shown.** The gap between the largest number any GIMS writer here has stored and
the guard D1–D5 needs is **284 decimal orders of magnitude**; next largest magnitudes are embedding components,
`|v| ≤ 3,054`. *Absence in one corpus, not safety* — §D.8.

### D.4 Q2 — non-ASCII digits or whitespace in coercible strings (D8, D10)?

D8 is `xpr.num`'s ASCII gate vs Python's Unicode-aware `_to_num` (`f1` §1.9.2 row **D8** **[punch]**); D10 is `str.strip()` vs
`btrim(E' \t\n\r\f\v')` on dates — 10 of 12 whitespace code points diverge (`f1` §1.9.2 row **D10** **[punch]**,
`expr.py:413` vs `runtime.sql:273`). W decodes every string value and key, classifying non-ASCII chars by `unicodedata.category`:

| | |
| --- | ---: |
| string values + object keys examined | 1,096,202 |
| **strings carrying a non-ASCII decimal digit (`Nd`)** | **0** |
| **strings carrying non-ASCII whitespace (`Zs`/`Zl`/`Zp`/`isspace`)** | **0** |
| …of those, at a string edge, where `strip`/`btrim` actually differ | **0** |

> **What 1,096,202 counts, and the one gap in its producer — re-verified at the consistency pass [consistency].**
> `f1` §1.9.5 and §1.11 item 6 now quote this denominator, and `f5` §5.4(4)/§5.6/§5.9(5) quote it alongside
> §D.2's **495,115**, so both are pinned here. **1,096,202 is string values *plus* object keys, over the
> `instances` tables only** (36,372 rows). **495,115 is string values *only*, over all 37,078 swept rows**
> (`instances` + the four `*_verb_log` tables). Different unit *and* different scope — neither is a subset
> label for the other, and neither can be substituted for the other in a rate.
>
> **The two tie exactly, and the tie is this [punch].** Of §D.2's 495,115 string values, **491,813** are in
> `instances` and **3,302** are in the four `*_verb_log` tables — 491,813 + 3,302 = 495,115, exact, re-aggregated
> read-only from `xd_sweep.json` for this pass. **491,813 is therefore the string-value half of 1,096,202**, and
> the remaining **604,389** is the object-key half — *arithmetic*, 1,096,202 − 491,813, and arithmetic precisely
> because the key count itself was never retained (the gap below). That is why the larger number covers the
> *smaller* corpus: it adds ≈604 k object keys and drops the 3,302 `verb_log` string values. The `instances`
> row count behind it, **36,372**, is §D.2's swept **36,369** plus the same **+3** `LedgerRecord` drift the census table's 17,148
> carries — one writer, one offset, stated in both places.
>
> **The gap in its producer, stated exactly [punch].** `xd_sweep.py` tallies object keys in memory
> (`a.keys[k] += 1`) but **emits no key count into `xd_sweep.json`** — the per-unit fields it writes are `rows`,
> `nums`, `ints`, `floats`, `strs` and the witness lists, and none of them is a key count — and it passes only
> string *values* through the `unicodedata.category` classifier. So at the time of drafting the object-key half
> of this denominator had **neither a retained producer for its count nor any producer for its zero**; only the
> 491,813 string-value half is re-derivable from the retained artifact.
>
> **Closed by re-running it:** a second independent walker that classifies keys *and* values, `mode=ro&immutable=1`,
> over the same corpora, returns **0 non-ASCII `Nd` digits and 0 non-ASCII whitespace across 491,861 string values
> + 604,350 object keys = 1,096,211** on `instances` (1,103,311 including `verb_log`). The nine-node difference
> from 1,096,202 is the concurrent writer of §D.1, not a correction. The Unicode-tolerance control re-derives too:
> **218** distinct non-ASCII code points, **29,773 of 36,372** rows, `U+2500` ×**144,265**, `U+26A0` ×**27,736** —
> all exact; occurrences **206,571** vs the drafted 206,567 and em-dash **28,708** vs 28,704, the same +4 rows of
> drift. **The claim stands; its provenance is now two instruments rather than one** — three as of this pass
> **[punch]**: a further read-only walker, run for the punch list against the same corpora with
> `mode=ro&immutable=1` and classifying **both** halves, returns the same two zeros. Its denominators are larger
> again (the §D.1 writer has kept writing) and are **not** published here; it was run to check the split and the
> zeros, not to restate them.

**The zero is load-bearing only because the corpus is demonstrably Unicode-tolerant:** the same sweep found **218
distinct non-ASCII code points, 206,567 occurrences, in 29,773 of 36,372 rows (81.86 %)** — `U+2500` ×144,265,
em-dash ×28,704, `U+26A0` ×27,736, arrows, smart quotes, emoji, Greek delta. What GIMS writers have never once
put in is a non-ASCII **digit** or **space**. An ASCII-only corpus would make this zero worthless; this one is
not. **In passing:** the raw stored JSON *text* holds **0 non-ASCII bytes in all 36,372 rows** — every code point
is `\uXXXX`-escaped, i.e. `json.dumps()` at default `ensure_ascii=True`, matching `core/storage/sql.py:362,563`.
Corroborates §D.5.

### D.5 Q3 — >17 significant digits, or any sign of a non-Python writer (D12–D14)?

D12–D14 need a number **not** produced by a Python float (`f1` §1.9.2 rows **D12–D14** **[punch]**). `fuzz/D_rawjson.py:12-17` already
fixed the direction: `gims-ledger/api/storage_aws.py:743-754` writes via psycopg `Jsonb(record)` and therefore
**cannot** produce such rows, while `:694` (`json.loads(cell)`) **will mis-read them if another writer does**. The
open question was the **writer**, not the reader. W answers it, keeping every number's literal text:

| test, over all 5,236,427 numeric literals | matches |
| --- | ---: |
| significant digits > 17 | **0** |
| **literal ≠ `repr(float(lit))`** (floats) **or ≠ `str(int(lit))`** (ints) — a literal `json.dumps` of a Python number could not have emitted | **0 of 5,236,427** |
| JSON parse failures on the stored text | 0 |
| maximum significant digits observed | **17** — e.g. `-0.017092391848564148` at `$.embedding[1]`, `Vector` key `geds::api/index.py` |

> **INFERENCE:** every row in every corpus on this machine was written by `json.dumps()` over a Python object —
> the `ensure_ascii` signature (§D.4) and the writer at `core/storage/sql.py:362,563` agree. No ETL, no `psql`, no
> restored dump, no second-language service has written these tables. D12–D14 have **no witness here, and no
> writer here that could make one.**

A claim about this machine's writers, not about Postgres: `storage_aws.py:326-335`'s own comment documents this
disagreement as a parity bug they fixed once (`fuzz/D_rawjson.py:16-18`) — evidence a non-Python writer *has*
existed in this system's history.

### D.6 Q4 — the tolerant/coercion class. **This one is reached, repeatedly.**

The `human_required = "false"` shape (`index-shape.md:126`). W censused every `(project, collection, JSON path)`
by JSON type. **D.6.1 — boolean-looking STRING where a boolean belongs:**

| project · collection | path | string `"true"`/`"false"` | real JSON bool |
| --- | --- | ---: | ---: |
| guts-ledger · `LedgerRecord` | `$.human_required` | **17,144** | **4** |
| guts · `LedgerRecord` | `$.human_required` | **5,182** | **4** |

Not 4 stray typos — a key **99.977 % string and 0.023 % boolean** in the largest real collection on the machine.
`index-shape.md:126` reported the string; the **mixture** is new here, and is the harder fact.

**D.6.2 — a key holding a NUMBER on some rows and a STRING on others:**

| project · collection | path | number | string | the strings are |
| --- | --- | ---: | ---: | --- |
| guts-ledger · `LedgerRecord` | `$.payload.blocked_since` | **315** | **9** | ISO-8601, e.g. `2026-08-14T16:40:15+00:00` |
| guts · `LedgerRecord` | `$.payload.blocked_since` | **57** | **4** | same |

One key, one collection, two incompatible physical types at **2.8 %** of the rows that have it — a **real witness
for hazard H3, which was demonstrated with a constructed `{"score":"n/a"}` record** (`f3` §3.6, row H3) **[punch]**:
`CREATE INDEX … (((data->>'blocked_since')::float8))` cannot be built over this table, because 9 real rows raise
`invalid input syntax for type double precision`. The constructed record was not a straw man. Corpus-wide: **0**
keys mix a number with a *numeric-looking* string; **2** mix a number with a non-numeric string.

**D.6.3 — semantically numeric fields stored 100 % as strings:**

| project · collection | path | numeric-looking strings | other types | samples |
| --- | --- | ---: | --- | --- |
| LIMS · `Potency Sample` | `$."Sample Weight (g)"` / `$."Dilution Weight (g)"` | 7 / 7 | null ×7 | `'1'`, `'24'` |
| LIMS · `Terpene Sample` | the same two paths | 3 / 3 | — | `'1'`, `'24'` |
| LIMS · `Sample` | `$.sample_id` · `$.received_date` | **20** · 7 | string ×35 · ×43, null ×5 | `'14190.52'`, `'12345'` |
| LIMS · `Instrument Type List` | `$."ID #"` | 4 | — | **`'0002'`, `'0000'`, `'0003'`** |
| LIMS · `Submission` | `$.received_date` | **5** | string ×1, null ×1 | **`'60824'`** (×5), `'2025-06-11'` |

A field literally named *"Sample Weight (g)"* is a **string** in 100 % of the rows that have it. `ID #` is
`'0002'` — leading zeros, so `number('0002')` = 2.0 destroys the identity and text sort disagrees with numeric
sort. `Submission.received_date` is `'60824'` on 5 of 7 rows: numeric-looking and **not a date** — `_DATE_RE`
(`expr.py:402`) and its mirror (`runtime.sql:273-276`) reject it, so date functions over it yield null. **The
coercion class is not exotic; it is the ordinary condition of this data, in both trees.**

### D.7 The one real dashboard, against its own real rows

`coverage.md:652-670` found one dashboard in two backups. It is also **live**:
`GIMS-Project/projects/LIMS-System/project_nodes/nodes.db`, table `dashboards`, **1 row**, id
`143c987947874e36b728bb66f5a9125c` ("Testy Test") — same id, so still **n = 1 distinct dashboard**, 3 widgets, 2
of them `csv` (never reach `resolve()`). Its one resolver-reaching widget, verbatim from `layout_json`:

```json
{"type": "noun", "noun_type": "Submission",
 "derive": {"days_left": "round(days_between(today(), $.due_date), 1)"},
 "where": "$.status == \"in progress\"", "sort": {"field": "days_left", "dir": "asc"}}
```

`sources.py:193-206` (`_noun_records`) loads one noun type and `:348-351` caps that loader's result, so the scan
unit is `Submission` — **all 7 rows**:

| `submission_id` | `status` | `due_date` | `priority` | kept by `where`? |
| --- | --- | --- | --- | --- |
| Sub0608250000 | `in progress` | `2026-07-02T17:00:00` | `true` (bool) | **yes** |
| Sub0608250001 | `in progress` | `2026-07-04T17:00:00` | `false` (bool) | **yes** |
| Sub0611250001 | `in progress` | `2026-07-10T17:00:00` | `true` | **yes** |
| Sub0608250002 | `completed` | `2026-07-05T17:00:00` | `false` | no |
| Sub0608250003 · Sub0608250004 · asdfasdfasdf | **null** | **ABSENT** | ABSENT | no |

1. **Null propagation is live in real data.** `due_date` is absent on **3 of 7 (42.9 %)** rows, so
   `days_between(today(), $.due_date)` → `expr` null → SQL `NULL` on 43 % of the collection — the
   `index-shape.md` §1.2 generator modelled this at 8 %, so the real rate is **5× higher**.
   **Cross-reference — the corpus `f4` actually measured on is at 5 %, not 8 % [consistency].** 8 % is
   `index-shape.md` §1.2's *modelled* rate; the generator that produced every row behind `f4`'s numbers omits
   `due_date` on **5 %** (`proto/gen_data.py:30`, `if rnd.random() >= 0.05:`, quoted at `f4` §4.2). Against
   42.9 % that is **8.6×**, and it bears on `f4`'s selectivity, derive-cost and recall figures rather than on
   anything in this section; `f4` §4.2 now records it and works the direction through in `f4` §4.11, where the
   net effect is left **not established**. Re-verified for this pass, read-only, against
   `GIMS-Project/projects/LIMS-System/objects.db` (`instances`, `collection = 'Submission'`): 7 rows, `due_date`
   absent on `Sub0608250003`, `Sub0608250004` and `asdfasdfasdf` = **3 of 7 = 42.857 %**. **Stated against this
   section: n = 7.** The rate is exact for this collection and extrapolates to nothing (§D.8) — it is a real
   counter-example to the 5 % assumption, not a replacement parameter.
2. **On this corpus the widget's own filter removes exactly those rows** — `status` is null on precisely the 3 rows
   lacking `due_date`, so *kept ∧ due_date-absent = 0* and `sort` never orders a null. **OPINION: an n = 7
   coincidence, not a property of the widget.** One tenant adding an `in progress` submission with no due date
   puts a null into `sort`, which is `f3` §7.4's ordering divergence.
3. **The date shape is real datetime, not bare `YYYY-MM-DD`** — `2026-07-02T17:00:00` is inside both parsers'
   `[T ]` branch (`expr.py:402-406`, `runtime.sql:273-276`) and the fixture exercises it (13 datetime-with-time
   vs 19 bare-date literals): not a gap, recorded because it could have been. `received_date` = `'60824'` is in
   the same collection (§D.6.3) — no widget reads it today, nothing prevents one.

### D.8 `MAX_SCAN`, and how representative this corpus is

`MAX_SCAN = 20_000` (`sources.py:61`), per loader result (`:348-351`) — one collection for `noun` sources.
Largest real collection (`guts-ledger` · `LedgerRecord`): **17,148 = 85.7 % of MAX_SCAN**, headroom **2,852
rows**, `created_at` spanning 2026-07-06 → 2026-08-19 (**44.2 days**, 27 distinct days with rows). Growth is
bursty, so the answer is a range, not a point:

| rate basis | rows/day | days to cross `MAX_SCAN` |
| --- | ---: | ---: |
| largest observed single day (2026-08-06) | 3,515 | **0.8** |
| mean, last 14 full days | 807 | **3.5** |
| mean, whole 44.2-day history | 388 | **7.4** |
| mean, last 7 full days (a quiet week) | 58 | 49.4 |

**No collection here exceeds `MAX_SCAN` today**; one is within a week of it on three of four bases. **OPINION:
"nothing is over the cap" is the weakest available argument against pushdown.**

**Representativeness — stated against the spike, not for it.** *n = 1 machine, 1 operator*; no second machine, no
tenant sample, no production snapshot in scope. *The corpus is the tooling, not tenants*: 22,334 of 37,078 rows
(60.2 %) are `LedgerRecord` written by AutoDev itself, 13,526 (36.5 %) are code-embedding `Vector` rows, and the
LIMS tenant project — the only one shaped like the dashboard use case — contributes **222 rows across 18
collections**, the one real dashboard's source **7**. Every claim about "ordinary tenant data" rests on those 222
rows. *One writer*: §D.5 shows a single writer signature across 5.2M literals, and a corpus with one writer cannot
answer a question about a second writer — exactly what D12–D14 ask; the sharpest limit on this section. *The WAL
is invisible*: `immutable=1` ignores `objects.db-wal`, **543,872 bytes** for `guts-ledger` at 14:20 and growing;
the checkpointed count moved 17,145 → 17,148 in six minutes, small against 17,148 but **not zero and not
measured**. *158 backup snapshots not swept* (§D.2). **Nothing here extrapolates to production.**

### D.9 What this changes

| class | reachable from real GIMS data here? | basis |
| --- | --- | --- |
| **D1–D5** (297-digit `f8` guard) | **No witness.** 0 / 5,235,942 numeric nodes; max `|v|` is 284 decades short | §D.3, two instruments |
| **D8, D10** (non-ASCII digits / whitespace) | **No witness.** 0 / 1,096,202 **string values + object keys** **[punch]** — in a corpus with 206,567 non-ASCII code points | §D.4 |
| **D12–D14** (jsonb `numeric` ≠ IEEE double) | **No witness, and no writer here that could make one.** 0 / 5,236,427 literals deviate from `json.dumps` output | §D.5, `D_rawjson.py:12-17` |
| **coercion / tolerant class** | **REACHED, at scale** — 17,144 bool-strings on one key; a number/string key at 2.8 %; weight fields 100 % string; `'0002'`; `'60824'` | §D.6 |
| **null propagation through `derive`** | **REACHED** — 42.9 % of the one real dashboard's own collection | §D.7 |
| `f3` §3.6 **H3 index hazard** **[punch]** (`::float8` expression index un-buildable) | **REACHED with a real record**, not a constructed one | §D.6.2 |

**INFERENCE — the only judgement this section makes.** The `f1` §1.9.3 breach of FRAMING §4's NO-GO clause is
carried by causes whose triggering inputs are, on this evidence, **not generated by any writer in this system**,
while the classes that *are* everywhere in real data are the tolerant/coercion ones. That does **not** clear the
bar — FRAMING §5 is about a *silent* wrong answer, and `f1` §1.9.5 shows a value→null divergence becomes
null→value the moment it sits under an `if()`. It changes the **shape of the risk**: from "an exotic float
silently corrupts a dashboard" toward "an ordinary string-typed weight, or a `"false"`, does". Different fallback
costs; `f5` should price them separately.

### D.10 Not established by this spike — each with what would establish it (none attempted, FRAMING §3)

1. **Whether the compiled SQL actually diverges on the real witnesses found here.** §D.6 shows `$.human_required`
   and `$.payload.blocked_since` exist; it does not run them through the compiler. *Would establish it:* feed
   those two real `LedgerRecord` rows to `proto/conformance.py`'s three-outcome harness. **Not run — that would
   execute the compiler.** *(Wording corrected [consistency]: the line to hold is "no compiler run, no database
   write", not "no new instrument" — this section did build a new read-only instrument, see the label note above
   and §D.1.)*
2. **Whether any non-Python writer exists anywhere in GIMS.** §D.5 proves none has written *these* tables. *Would
   establish it:* an audit of every `INSERT`/`COPY` path into `instances` in both trees, plus deploy-time
   migration and restore tooling.
3. **Whether production data resembles this.** *Would establish it:* this section's `xd_sweep.py` predicates run
   read-only against a production `instances` table, or collection of the `MAX_SCAN` warning `sources.py:350`
   already emits and nobody gathers.
4. **The dashboard usage distribution.** Still **n = 1 dashboard, 3 widgets** — confirmed live rather than only in
   backups, which does not increase n. *Would establish it:* the `dashboards` table from >1 deployment.
5. **What is in the un-checkpointed WAL.** *Would establish it:* a `mode=ro` non-immutable read, which touches
   `-shm` and was therefore not done. **6. Array-valued keys vs the lax/strict jsonpath split** (`f3` §3.8 item 7
   **[punch]**): this sweep recorded array presence but did not classify element types against the jsonpath route.

### D.11 Attestation

`GIMS-Project` HEAD `995cc59`, `gims-ledger` HEAD `7b7a049` — the FRAMING §7 values, unchanged; both working
trees carry pre-existing dirty entries, **none this seat's**.

> **Correction to this attestation, re-verified at the consistency pass [consistency].** The drafted line —
> "both working trees carry 8 pre-existing modified files, all mtime **2026-08-13**, six days before this
> spike" — is **wrong in two particulars**, both checked with `git status --porcelain` + `stat` and neither
> touching the read-only claim. **(i) The counts differ:** `GIMS-Project` has **8** dirty entries (7 modified,
> 1 untracked), `gims-ledger` has **9** (7 modified, 2 untracked). **(ii) "all mtime 2026-08-13" is false for
> three of them:** `projects/RunlogTest/verbs/Chemistry/data_dumps/R1/grid_save_debug.log` is **2026-06-28** in
> both trees (older, still pre-existing); `gims-ledger/backups/_config/schedules.json` is **2026-08-19
> 10:40:07 −0600**, ten minutes *before* `sp-investigate` opened (16:50:18Z = 10:50:18 −0600); and the
> untracked directory `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` carries mtime **2026-08-19
> 14:32:46 −0600**, which is **inside** the spike window. That last one is the **same concurrent writer §D.1
> discloses for `objects.db`** — AutoDev's own ingestion verb, which also moved `LedgerRecord` 17,145 → 17,148
> during the sweep — not this spike. **What is attestable stands unchanged:** every connection this section
> opened carries `mode=ro&immutable=1` (`xd_sweep.py`, read here), no file in either tree was opened for
> writing by this seat, and both HEADs are the FRAMING §7 values. **What is not attestable, said plainly:** a
> seat that only reads cannot prove another process did not write, and one demonstrably did.

No file in either tree was opened for writing; every connection string here carries `mode=ro&immutable=1`. **No
Postgres connection was opened at all** — no object created, altered or dropped. `recon/`, `proto/`, `analysis/`,
`FRAMING.md`, `.autodev/` and `kb/` were read only; the only file written is this one. Working scripts live in the
session scratchpad (`…/scratchpad/xd_sweep.py`), outside the repository, throwaway by contract (FRAMING §3).

**Compliance, consistency pass [consistency].** The changes made to this file at the consistency pass are the
five marked **[consistency]** above — the label note in the header, the §D.4 denominator/provenance note, the
§D.7 item 1 cross-reference, the wording of §D.10 item 1, and the correction inside this attestation. **No number
in §D.2–§D.9 was changed**; the §D.4 note adds a second producer for a figure already published, and does not
restate it. Everything re-verified for that pass was re-verified **read-only**: `xd_sweep.json` re-aggregated from the retained scratchpad
output; a second independent walker re-run against the same corpora with `mode=ro&immutable=1` (a `/tmp` script,
outside this repository); `proto/gen_data.py`, `analysis/index-shape.md`, `.autodev/events.jsonl` and the other
`.parts` files read, never written; `git status`/`git rev-parse` in both GIMS trees, which write nothing. **No
Postgres connection was opened in this pass either**, and nothing anywhere was fixed (FRAMING §3). The only file
this seat wrote in either pass is this one.

**Compliance, punch-list pass [punch].** This pass changed **citations and reconciliations only**; it changed no
published measurement. Specifically: **(1)** the seven `.parts/f1.md:NNN` / `.parts/f3.md:NNN` line references —
which resolve only inside the working parts directory, and which the rewritten `f1`/`f3` have since made stale
anyway — were converted to section references (`f1` §1.11 item 6; `f1` §1.9.2 rows D1/D5, D8, D10 and D12–D14;
`f3` §3.6 row H3; `f3` §3.8 item 7), each checked by opening the cited section and matching the quoted claim;
**(2)** §D.9's "`f3` §7.3" was corrected to "`f3` §3.6" — §7.3 is `analysis/index-shape.md`'s section number for
the same hazard and resolves nowhere in this document; **(3)** §D.2 gained the reconciliation of its own census
table to the swept 37,078; **(4)** §D.4's denominator note gained the exact 491,813 + 3,302 = 495,115 tie and a
sharper statement of what `xd_sweep.json` does *not* contain; **(5)** §D.9's D8/D10 row, which read
"0 / 1,096,202 **strings**", now carries the same "string values + object keys" label the §D.4 row it summarises
has always carried — the figure is unchanged, the label was the loose half. **No number already published in
§D.2–§D.9 was changed** — 17,148 · 37,078 · 495,115 · 1,096,202 · 5,236,427 · 5,235,942 and every count in §D.3–§D.7 stand as
written. The figures newly *stated* (36,369 · 709 · 491,813 · 3,302 · 604,389 · 27 · 17,145) are re-aggregations
of the retained `xd_sweep.json` or arithmetic on figures already published, and the derivation is shown in place.
Read-only throughout: `xd_sweep.json` re-aggregated and `xd_sweep.py` re-read; one further walker and one
schema/row-count enumeration run against both GIMS trees with `mode=ro&immutable=1` (`/tmp` scripts, outside this
repository); `consistency.md`, `FRAMING.md`, `f1.md`, `f2.md`, `f3.md`, `f4.md`, `f5.md`,
`xc-fallback-register.md`, `f6-closure-log.md`, `FINDINGS.md`, `analysis/index-shape.md` and `analysis/coverage.md`
read, never written. **No Postgres connection, no write to any file in either GIMS tree, nothing fixed**
(FRAMING §3). The only file this seat wrote is this one; `FINDINGS.md` is regenerated from the parts by a later
seat and was not edited. **The verdict is unaffected** — nothing above moves a reachability result in either
direction, so `f5`'s NO-GO stands exactly as it stood.
