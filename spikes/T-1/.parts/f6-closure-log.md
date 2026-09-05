## Closure log — what the audit passes changed

**[punch] What this section is, and what its heading used to be.** It now records **two** repair
rounds. The first — the consistency-repair pass — is everything down to *Assembly*, kept as it was
written, with **[punch]** notes inserted only where a later measurement — or a re-read of the file a
row describes — showed something it said to be wrong.
The second is the **punch-list round**, appended at the end under its own heading. The heading above
read *"Closure log — what the consistency pass changed"* until the punch-list round; a link to the
old anchor `#closure-log--what-the-consistency-pass-changed` will not resolve.

The body above was drafted in parallel by nine seats, then read as one document by a tenth
(`.parts/consistency.md`), which found **24 defects in the drafted prose** and prescribed a repair for
each. Nine repair seats — one per section — then worked those items under a standing rule: **every repair
had to be re-verified against the raw artifact before it was written**, and where the artifact disagreed
with the consistency read, the repair was **refused and reported** rather than applied. This log is that
record. Each in-place edit is marked **[consistency]** at the point of change.

Nothing below fixes a defect *found by* the spike. `FRAMING.md` §3 forbids that, and the stop-rule audit
(`consistency.md` item 24) found no violation. This pass repaired the **document's accuracy** only.

### What was repaired

| item | section repaired | what changed | verified against |
| --- | --- | --- | --- |
| **1** | `f5` §5.3(b), §5.9(4) · `xc` C.3 (D17 row) | The bolded absolute *"No index containing compiled output can be created at all"* was **false** and is removed. Restated as **no compiled *predicate* (W1–W9) and no compiled *derive* column (D1)**, with the measured counter-fact in place: the compiled **sort key S1** carries no `to_jsonb` wrapper, is indexable, and was measured index-backed. `xc` C.3's D17 row carried the same false absolute in a parenthetical ("moot today — no such index can be created at all"), **not named by the consistency read**; the `xc` seat found and repaired it under the same adjudication, and D17's DDL-policy obligation is now **live, not moot**. | `proto/idxshape_preds.json` — re-derived here: **11 compiled outputs, `to_jsonb` in exactly 10**; `S1` = `nullif((data -> (%(p0)s)::text), 'null'::jsonb)`, zero wrappers. `f3` §3.6 H4: `Index Scan using idxprobe_score_operand`, **0.065 ms**. `xc` C.5's own H1 row was only obtainable because such an index *was* created |
| **2** | `xa` A.5 (heading + body) · `xc` C.13 (last bullet) | Three sections disagreed about whether *"the in-memory fallback can itself raise"* had been answered. `xa` deleted its own **"No section considers it."** — it is the section that answers it. `xc` C.13's *"no section of this spike adjudicates it"* became a forward pointer to `xa` A.5(ii), naming what genuinely **remains** open: the **production frequency of N1–N4**. `xc` C.3's D7 row and C.11(a)'s R1′ row already considered the retry raising and were left untouched. | `xa` A.5(ii)'s own measurements: poison row at index 0/5/9 → uncaught `OverflowError` in both `_apply_derive` and `_filter_rows` (`sources.py:147`, `:162`); HTTP 500 via `core/errors.py:113-119`; **40.9% (65/159)** of SQL raises also raise in the retry (`analysis/fuzz/G2b_round_raises.txt`) |
| **3** | `xb` B.10 | **Already applied before this pass.** B.10 no longer attributes a CONDITIONAL-GO to `f5`; `grep` finds no "CONDITIONAL-GO" anywhere in `xb`. The seat added only a traceability marker and an explicit *"(`f5` recommends NO-GO)"*. | `f5`'s opening verdict block, verbatim: "**Verdict: NO-GO** on the architecture as scoped"; `grep -c CONDITIONAL-GO` over `xb` = **0** |
| **4** | `f1` §1.11 item 6 and §1.9.5 · `xc` C.13 bullet 1 | Two sections declared reachability open and prescribed the exact sweep the next section performs. Both became forward pointers: **closed for this corpus by `xd` D.3–D.5; production-scale reachability remains open (`xd` D.8)**. `f1` §1.9.5 carried a **second, dependent** stale cross-reference not named by the consistency read; the `f1` seat repaired it too. `xc` added a scope limit the read did not state: **`xd`'s four predicates do not screen for offset-bearing or out-of-range date strings**, so the closure is real for the numeric and Unicode classes and **empty for the §5 clause-2 (raise → value) breach**. | `xd` D.3/D.4/D.5: **0 / 5,235,942**; **0 / 1,096,202** (string values **+ object keys**); **0 / 5,236,427**; plus the writer-signature test. `xd` D.8 for the production-scale limit |
| **5** | `f5` §5.10 and §5.4 | The elapsed-cost figure cited a timestamp not in the file it named and excluded `f5` itself. Corrected to **4 h 01 min** (`sp-investigate` opened `16:50:18.060Z`; `f5` landed `20:51:51Z`), with `20:33:32Z` identified as `xd-reachability.md`'s **file mtime**, not an event. The seat also repaired **§5.4's opening line** (not on the list): this pass rewrote `xa`–`xd` in place, so their landing mtimes no longer read as published; the landing order now cites `consistency.md` §2, which is the only surviving independent record. | `.autodev/events.jsonl` (`stage.advanced` at `16:50:18.060Z`); `ls --full-time spikes/T-1/.parts/`. See the refusal below — `events.jsonl` has since gained records and a **4th** `worker.started` |
| **6** | `f5` §5.7 (E1 "State to beat") | `H_unicode` was published as **4/3 863**, which is the AGREE count, not the ran count. Corrected to the ran count with the unit labelled and the arithmetic shown. The other two entries (3 881, 3 880) were **already correct** ran-counts and were not changed. `f1` §1.9.2 was already right and needed no edit. | `analysis/fuzz/H_unicode.txt`, re-read here: `AGREE 3863 · DIVERGE 4 · PARSE_ERROR 133` of `N=4000` → **ran = 3867** |
| **7 / adj. A** | `f4` §4.9(2), §4.11 · `f5` §5.3(a), §5.5(3) | Two headline ranges for one multiplier. The binding headline is **3.79×–7.15×**, from the six-size sweep medians. **2.55×** may appear only as a single load-controlled re-run at N = 20,000, with its provenance caveat **in the same sentence**, never as the headline. Both files now state it identically. | `analysis/measurements.json`, re-derived here: B2 ÷ A = **4.152 / 3.892 / 3.794 / 4.363 / 6.713 / 7.152**. `analysis/probes.json → recheck` at 20,000: A 492.63 ms, B2 1 257.03 ms = **2.552×** — the block `f4` §4.11 itself records as having **no retained producer** |
| **8** | `f5` §5.5(3) | The cheaper-alternative argument cited `sources.py:61`'s comment as anticipating "the change"; the comment anticipates **pushdown** — this project — so read correctly it is evidence **for** the ticket's premise. And the alternative's cost was stated only against the prototype, never against today. Both corrected in place. | `GIMS-Project/api/dashboard/sources.py:61` comment, read live: *"(Pushdown filtering removes this.)"*. `analysis/measurements.json`: Path A at 1 M = **8 331.43 ms**, so the one-line change is **≈2.0× slower than today's latency** and leaves the 98%-of-time acquisition and the 2.4 GB per-request heap untouched |
| **9** | `f5` §5.6, §5.9(6) | *"a harness proven able to fail"* overstated what the negative controls do, as `f1` §1.7 had already corrected in place. Corrected, and the residual added to `f5` §5.9's "stated against the spike" list, which had omitted it. | `proto/conformance.py:376-455` — the outcome-assignment branches are **exercised by nothing**; the 23/23 controls construct no case entry and assert no `outcome` |
| **10** | `f5` §5.6 | *"best single constant 20/130, **so** 75 of 130 agreements are unreachable by any constant"* switched denominators mid-sentence. The premise yields **110**; **75** comes from the union of all five constants (55/130). Derivation corrected; the conservative number is unchanged. | `proto/results.json` → `degenerate_baselines`, re-read here: `{true: 20, null: 19, false: 15, zero: 1, empty-string: 0}` → 130 − 20 = **110**; 130 − 55 = **75** |
| **11 / adj. D** | `f2` §2.4 · `f1` §1.9.3 | Two corrections `xa` A.6 ordered were never applied in place, and both sections come first in reading order. `f2` **deleted the inference** ("403 independent confirmations of the totality premise") and **kept the count**, with a forward footnote to `xa` A.6. `f1`'s understated "4 witnesses of 45 date probes" became **8 mechanisms across 9 source lines and 4 exception types**, also footnoted. | `xa` A.2 (the eight mechanisms) and A.3 — the 403-probe domain tops out at `\|value\|` 2026.0, nesting depth 4, `ndigits ∈ {−1, 2}`, zero `%`, zero offset-bearing dates, so it **cannot reach any of the eight raise sites**. `proto/coverage_probe_results.json` for the retained 403/403 count |
| **12** | `xb` B.4 | **Already applied before this pass** — the unit note distinguishing the table-wide count from `xd`'s `LedgerRecord`-only count was present, and already said "two units, not two measurements of one number". Its **arithmetic did not hold**, and the seat corrected that in place; see the refusal below. The published figure **17 342 → 17 345**, with the old figure left visible and the residual disclosed as unexplained. The numerator (**4 166**) and the rate (**24.0%**) are exact and unchanged. | `xd` D.2's collection census; a `mode=ro&immutable=1` re-count of `guts-ledger/instances` |
| **13** | `f5` §5.1, §5.2, §5.4 | Seat [1]'s value-vs-construct argument was left unrebutted while §5.7 instantiates a construct-keyed subset. `xc` C.1's DETECT/AVOID distinction — the one closure item that cuts **for** a CONDITIONAL-GO — was missing from §5.4's list and is now item (5) there, with its measured limits. §5.2's ruling now rests on the fixture-adequacy question. | `xc` C.1: **AVOID** is static and construct-keyed, decidable at `sources.py:345`; it satisfies FRAMING §5 but **not** §4's "detectable". `xc` C.10 for its cost (46/130 cases, 12/22 functions) |
| **14** | `f5` §5.5/§5.9 | `f3` §3.9's OPINION recommends shipping **rule 3** first; `f3` explicitly defers rule 3's economics to finding 4, and `f4` answers **no**. No section joined the two. A paragraph now records that `f4` removes rule 3's premise. | `f3` §3.9 (the emission rule); `f4` §4.4 and §4.9(2) (3.79×–7.15× slower) |
| **15 / adj. E** | `f5` §5.9(2), §5.4(4)/§5.6 · (`f5` §5.8(a), beyond the list) | Denominator drift: an **id** count added to a **class** count. Corrected to `xc` C.8's own units — **34 `expr`-layer ids → 15 detectable ids**; **19 undetectable ids = 18 classes**; **33 distinct classes** after folding D21. `f5` §5.3(c) was **already correct** ("18 of 33 distinct classes") and was not touched. Separately, **1 096 202** is labelled as `xd` D.4's *"string values **+ object keys**"*; the string-values-only figure is **495 115**. The seat found and repaired the **same slip in §5.8(a)** ("6 of 34 register ids" next to "18 classes"), which the consistency read did not name. **[punch]** *"`xc` C.8's own units" was true of C.8's **body table** and not of C.8's **bolded headline**, which at the time read "15 detectable, 18 undetectable" — itself an id count added to a class count, summing to 33 while naming the 34-id register. `consistency.md` item 15 had compared the body figures, ruled "**xc is right**" and prescribed no `xc` edit, so the headline went uninspected through this pass; it was repaired in the punch-list round (below). What `f5` was corrected to were C.8's **body** figures, which were and are correct.* | `xc` C.8 (the register counts); `xd` D.2 and D.4 (the two string denominators) |
| **17** | `f1` §1.1 | Three non-regenerable captures were named where the section's own table (25 outputs, 21 runs) requires **four**. The fourth is `H_parse_errors.txt`, which `f1` §1.10 identifies separately as a superseded capture. | The four `.txt` in `analysis/fuzz/` with no corresponding `.py`; `proto/run_all.sh` = 21 `run` lines |
| **18** | `xb` B.8 | *"Ten substantive obligations. Zero compiled, zero tested, zero fallback-ruled"* read against B.8's own rows 1 and 6, which record hand-written SQL in `bench.py`. Restated as **zero emitted by `proto/compile.py`, zero tested, zero fallback-ruled** across all ten obligations, with the exception named: the only SQL anywhere for `filters` or `sort` is hand-written for one widget, and B.3 measures that clause **dropping 2 of 3 rows**. | `proto/compile.py` (emits none of the ten); `proto/bench.py:94-101` and `:226` (the hand-written clauses) |
| **19** | `f5` §5.4(3), §5.9(3) | The flat claim that migrating the store "changes the answer on 4 166 real rows" dropped `xb`'s own scope note. Carried across in place: the answer changes only **for a query that resolves a `runid`-normalising key**, and `xb` labels the production relevance an **INFERENCE** — *whether a production `DataSource` targets a collection holding the colliding pair is not established*. | `xb` B.4's scope note and its INFERENCE label; `f2` §2.9 (the `DataSource` corpus is absent) |
| **20** | `f0` (this header) | **Already applied before this pass**, at 15:07 — the map carries the four cross-cutting sections §A–§D, and the `recon/semantics.md` §11 correction. **Verified at assembly:** all nine map rows match the actual `##` headings in the actual body files, in assembly order, with the right titles. The assembly seat made two further header repairs, marked **[consistency]**: the provenance row *"Nothing was written to either"* (see "new concerns" below), and a pointer to this log. A **Contents** table was added after "How to read this document". | The nine part files' first lines, compared against the map row-by-row; `git status --porcelain` in both GIMS trees |
| **21** | `f3` §3 summary line | The summary led with *"3 of 130 fixture cases (2.3%)"* while §3.5(c) and §3.9 already carried the operative figure. **[punch] Corrected description of the result, read off `f3` as it now stands, because this row did not match it.** The summary paragraph *leads* with "No — and the index is not the reason"; the routable figure sits at the **end** of it and reads **2 of 130 fixture cases (1.5%), one distinct expression shape** (§3.5(c), §3.9 rule 1) — a shape cannot be routed if one of its records is silently wrong. **3 of 130 (2.3%) was not removed**: it is retained in the sentence that follows, labelled *"its per-case upper bound"*, with the third case named (case 34, shape `$.x == null`, the shape that silently diverges at case 33). The form **1 of 113 distinct expressions (0.9%)** is carried by **§3.5(c)**, not by the summary line; the drafted version of this row attributed it to the summary. §3.5's ladder and §3.9 rule 1 were **already correct** and were not touched. | `f3` §3.5(c)'s existing reconciliation; `proto/idxshape_preds.json`, `proto/idxshape_plans.json` |
| **22** | `f4` §4.2, §4.7, §4.11 · `xd` D.7 | The measurement corpus's missing-key rate is **5%**; the one real collection's is **42.9%** — an **8.6×** difference nobody had applied to `f4`'s selectivity, derive-cost or recall figures. Now paired where the 5% lives, with the effect on each, and a reciprocal pointer added in `xd` D.7. The **net direction is returned as *not established***, because the two legs push opposite ways (see "new concerns"). `f4` §4.7 additionally now states that the recall cliff is a property of the **synthetic sweep only** — no collection on this machine is over `MAX_SCAN`. | `proto/gen_data.py:30` (the 5% generator rate); `xd` D.7 (42.9%, **n = 7**); `xd` D.8 (largest real collection 17 148 rows = 85.7% of `MAX_SCAN`) |
| **23 / adj. G** | `f1`, `f3`, `f4`, `xa`, `xc` (added) · `f2`, `xb`, `xd`, `f5` (confirmed / extended) | Compliance attestations were present in four sections and absent from five. Each of the five now carries one, attesting **only to what its artifacts support**. `f2`, `xb`, `xd` and `f5` already had one and were **not given a second**; `xb` extended its existing block to cover the Postgres probes it had been silent on, and `xd` **corrected** its existing block (see "new concerns"). | Each section's own run record; `xd_sweep.py`'s `mode=ro&immutable=1` connection strings; `analysis/index-shape.md` §12.4 (verified end-state: 200,000 rows, `idxprobe_pkey` only) |
| **24** | `xd` D.1 header and §D.10 | The label *"a read-only sweep, not a new experiment"* overstated the case: `xd_sweep.py` is a **new read-only instrument, built this pass, cross-checked against `json_tree`**. Relabelled in both places. No defect is fixed anywhere in the spike; the stop-rule audit's "no violation found" conclusion stands, with the two grey areas disclosed. | `xd_sweep.py` (session scratchpad, outside the repository); `xd` D.1's `json_tree` aggregate cross-check |

**Item 16 is not a repair** — it is the consistency read's list of roughly forty figures it re-derived from
`results.json`, `measurements.json`, `idxshape_preds.json`, the fuzz captures and the GIMS tree that **came
back exact**. It is recorded here so the repairs above are not read as a general indictment of the body's
citation discipline.

### What was refused, and why

Every seat was required to verify a repair against the raw artifact **before** writing it, and to refuse
where the artifact disagreed. **Five refusals stand, across four seats — `xb`, `f1`, `f3` and `f5` (twice).
Three of the five refused a prescribed repair outright and the seat wrote its own corrected version instead
(items 12, 11, 23); in the other two — items 1 and 5, both `f5` — the prescribed repair *was* applied and
what the seat refused was a supporting claim: a characterisation in one, an evidentiary premise in the
other. [punch]** *Reconciliation, because the three places this document counted refusals did not agree.
This line read "Four refusals stand", which is the **seat** count; `f0`'s audit paragraph read "three",
which is the count of **prescribed repairs refused outright**; the table below has **five rows**, one per
refusal. Each number was true of something and none described the table. All three now state the same
thing: **5 refusals · 4 seats · 3 of them prescribed repairs.** Counted off the five rows below, row by
row.* `consistency.md` is authoritative about what is wrong; it is not infallible about the fix.

| item | who refused | what was refused | the raw evidence |
| --- | --- | --- | --- |
| **12** | `xb` | The prescribed reconciliation **"17,148 + 197 + 5 = 17,350, minus six minutes of writer drift"**. The `+ 5` is wrong: the `guts-ledger` store holds **no `Repo` collection at all** — `xd` D.2's two `Repo` collections are in `guts` and `guts-code`, where `xb`'s own sums already consume them. Applying it would have invented a fifth collection. The "writer drift" clause is also unavailable as an explanation: `immutable=1` reads the main db file only, and that file's mtime (**14:16**) predates both reads, so an `immutable=1` count **cannot drift**. The corrected identity **17,148 + 197 = 17,345** was applied instead, and the 3-row residual against the published 17 342 recorded as **unexplained** rather than explained away. **[punch]** *The refusal itself stands: the `+ 5` invents a fifth collection, `xb`'s own per-store sums already consume both `Repo` collections, and **17 345** is still the applied figure. Its **secondary** clause has been superseded — an `immutable=1` count does not drift continuously with the writer, but it does move **when a checkpoint lands**, so the main-file mtime cited here (**14:16**) is not evidence that the count could not have moved; `xb` B.4 now identifies a checkpoint at **14:16:56** as the single event that moved it. The residual is therefore **no longer unexplained** — see the correction under "New concerns" below.* | `xd` D.2's collection census (`Repo` ×2, both outside `guts-ledger`); `xb`'s own per-store sums (guts 12,095 ✓, guts-code 6,710 ✓); the store's main-file mtime |
| **11 / adj. D** | `f1` | The sub-clause *"Of 11 re-verified witnesses, 4 are raise→value, 3 raise→null, 3 both-raise"*, copied verbatim. **4 + 3 + 3 = 10, not 11.** Rather than reproduce arithmetic that does not reconcile, `f1` wrote what is exactly countable from `xa`'s own table — **10 tabulated direction rows** (4 raise → value: R1×2, R2, R8; 3 raise → null: R4 @ `DBL_MAX`, R6, R7; 3 both-raise: R3, R4 @ 1.7e296, R5) — and noted that `xa` counts 11 because its R6 row carries **two** witnesses (`floor("1e400")` *and* `ceil("-1e400")`). The headline figure the adjudication actually turns on — **8 mechanisms, 9 source lines, 4 exception types** — was verified independently and applied verbatim. | `xa` A.5(i)'s direction table (10 data rows); `xa` A.2's R6 row (two witnesses folded into one line) |
| **23 / adj. G** | `f3` | The prescribed attestation wording *"f3's DDL probes all ran in rolled-back transactions with post-rollback verification"*. True of the **closure** pass; **false as a blanket statement**. The four committed investigation-pass SQL scripts contain **no `BEGIN` and no `ROLLBACK`** — indexes are created and dropped in autocommit, one script leaves its indexes for the next to drop, and the H5 probe `INSERT`s a row and `DELETE`s it. This is **not** a stop-rule violation (it is all inside the spike's own scratch database, which `FRAMING.md` §7 provisions), but attesting "all rolled back" would be an untrue attestation. `f3` wrote the **split** version instead. | The four committed `proto/*.sql` scripts (`grep` for `BEGIN`/`ROLLBACK`: none); `idxshape_exprindex.sql` → `idxshape_jsonpath.sql:2-4`; `idxshape_hazard.sql:40`/`:49`; `analysis/index-shape.md` §12.4's verified end-state |
| **1** | `f5` | Not the repair — the **characterisation**. The dispatch described `f5` §5.9(4) (*"no compiled predicate can appear in any index today"*) as a defect to be fixed "so the two agree". Under adjudication F that sentence was **already true as far as it went**, and `consistency.md` item 1 itself quotes it approvingly as "the correct form 230 lines later". Rewriting it as though it had been false would have introduced an error where none existed. `f5` **extended** it with the derive column and the measured S1 counter-fact instead, so §5.3(b) and §5.9(4) now say the same thing at the same strength. | `consistency.md` item 1's own text; `proto/idxshape_preds.json` |
| **5** | `f5` | One **evidentiary premise** of the repair, not the repair. `consistency.md` states that `events.jsonl`'s *"last event of any kind is `18:49:12.087Z`"*. That was true when it was written; **it is not true now**. `f5` time-scoped the statement rather than publish a claim about the file that no longer holds. The prescribed repair is unaffected — **4 h 01 min stands**, because the later worker opened this closure pass, after `f5` landed. | `.autodev/events.jsonl`, re-read at assembly: last record **`21:37:26.830Z`**; a **4th** `worker.started` on `T-1/sp-investigate` at **`21:32:32.536Z`** |

### New concerns the consistency read missed

Each was found by a repair seat while verifying. **Where a seat did not own the file, it reported rather
than edited** — hard rule 1 of this pass. Nothing here is fixed; several are recorded as known rather than
latent errors.

**Repaired in place by the seat that found it** (each marked **[consistency]** in the body):

- **`xc` C.3's D17 row carried the same false indexability absolute as item 1**, in a parenthetical, and it
  contradicted `xc`'s own C.5 H1 measurement — which was only obtainable *because* such an index was
  created. Repaired; D17's DDL-policy obligation is **live**, not moot.
- **`f5` §5.8(a) mixed an id count with a class count** — *"6 of 34 register ids"* next to *"the 18
  undetectable classes"*, unlabelled, inviting the exact subtraction adjudication E forbids. Both figures
  are correct against `xc` C.8; the units were not.
- **`f1` §1.9.5 carried a second stale reachability cross-reference** pointing at the very line item 4
  orders repaired. Left alone it would have recreated the defect. This means the consistency read's own
  sweep for stale *"not established"* lines **was not exhaustive**.
- **`f5` §5.4's opening line cited `.parts/` mtimes as evidence**, which this pass invalidated by rewriting
  those files in place. The mtime-provenance defect is **systemic**: `ls --full-time` now contradicts every
  such citation, and the only surviving independent record of the original landing order is
  `consistency.md` §2. Citations to `proto/` and `analysis/` mtimes are unaffected.
- **`f0`'s provenance row said *"Nothing was written to either [GIMS tree]"***, which a read-only seat
  cannot observe. `xd` D.11 records a **concurrent non-spike writer** — AutoDev's own ingestion verb —
  creating `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` **inside** the spike window and moving
  `LedgerRecord` 17,145 → 17,148 during the sweep. The row is now scoped to what is attestable: no file in
  either tree was opened for writing **by this spike**, and both HEADs are the `FRAMING.md` §7 values.
- **`xd` D.11's attestation was falsified by the tree it attests about** — flagged independently by `f1`
  and `f4`, corrected by `xd` itself. The drafted *"8 pre-existing modified files, all mtime 2026-08-13"*
  is wrong in two particulars: the counts differ per tree (**8** in `GIMS-Project`, **9** in
  `gims-ledger`), and three entries are not 2026-08-13. What is attestable stands unchanged.

**Reported, not fixed — the seat did not own the file:**

- **`xa` A.5(i)/A.6's 10-vs-11 witness count.** *"4 of 11 witnesses"* against a 4/3/3 split summing to 10.
  It reconciles — one row packs two witnesses — but nothing in `xa` says so, and the section mixes a **row**
  count with a **witness** count in the same sentences. `xa` deliberately did **not** unilaterally fix it,
  because `f1` was being repaired in parallel and a one-sided change would have manufactured the very
  cross-file divergence this pass exists to remove. Not decision-blocking: the **4** raise → value
  witnesses — the §5-breaching number — is correct under both readings.
- **`xc` C.8's last row states "9 in Blocks A–C" as an id count that includes D21**, which the same section
  folds into D1–D5. As distinct **classes** it is 8. It is not currently added to a class count anywhere,
  so it does not breach adjudication E as written — but it is one quotation away from reproducing item 15's
  slip. **[punch] The second sentence's reassurance was too broad, and is corrected here.** At the time it
  was written the id/class mix *was* live, in this very section: `xc` C.8's own bolded headline read
  *"15 detectable, 18 undetectable"* — an id count added to a class count, summing to 33 against the 34-id
  register it names — and C.11(b) paired *"18 are invisible"* with the **34-id** denominator. Both were
  repaired in the punch-list round (below). What survives unchanged is the **narrow** claim about this row:
  the "9 in Blocks A–C" is still not summed into a class count anywhere, re-checked across the parts this
  round, and the row itself was not edited.
- **`f2` §2.4/§2.5 cite probe witnesses as `cases[344]`, `cases[226,227]`** — but
  `proto/coverage_probe_results.json` has **no `cases` key**; its top level is a bare list. The integer
  indices are all correct (9 of them re-verified), so no evidence is wrong; the wrapper name is fiction.
- **`f2` §2.4's surviving word "adversarial"** for the 403 probes is false for the magnitude/boundary axis
  (`xa` A.3: max `|value|` 9.0 in records, nesting depth 4, no `%`, no offset-bearing dates). Reduced to
  "403 inputs" in the one sentence the seat was authorised to rewrite; it survives elsewhere.
- **A live GIMS application was writing to `gims-ledger` *during* `f4`'s measurement sweep.**
  `projects/guts/verbs/ingestion/data_dumps/` holds `decompose-*` output directories with 2026-08-19
  mtimes at 11:22, 12:20, 12:25, 12:38, 12:58, 14:04, 14:10, 14:16 and 14:32; the sweep ran 11:57 → 12:27.
  `f4` §4.6 says "the sweep's own load was never recorded"; the truthful statement is stronger — **the host
  was demonstrably not quiet, and a named concurrent writer existed**. Recorded in `f4`'s new compliance
  block as an INFERENCE. It enlarges the declared error term on **absolute levels**; it leaves **ratios and
  counts** — which is what §4.7 and §4.9(2) are — alone.
- **Item 22's implied direction is the opposite of what the evidence supports on net.** On the one real
  collection the four rows that *do* carry `due_date` are all in the past, so the widget's `< 7` predicate
  would hold on 4/4 against the generator's ~9%. Real selectivity plausibly runs an order of magnitude
  **above** the synthetic 5.2%, not below. `f4` states both legs and returns *not established* on the net.
- **`xd` D.2's corpus table has two errors that nearly cancel** — the `verb_log` group omits
  `LIMS-System_verb_log` (27 rows, which *was* swept) and the table lists 28 `noun_Sample` rows that were
  **not** swept (that table is column-per-field, so `xd_sweep.py` skipped it). The arithmetic closes only
  the corrected way: 36,369 + 709 = **37,078** exactly. The published total is right.
- **`xd` D.6.3/D.7 print `Submission.received_date` as `'60824' (×5)`.** The count of numeric-looking
  strings is right (5 of 7); the literal is not uniform (`'60824'` ×4, `'60822'` ×1). Nothing rests on it.
- **`f3` §3.5(d)(i)'s J5 re-run and §3.7 item 6's re-derivations are prose-transcribed with no
  machine-readable capture** — already disclosed in `f3` §3.8 items 4, 5 and 9. Finding 3's
  machine-checkable spine is exactly two files: `proto/idxshape_preds.json` and `proto/idxshape_plans.json`.
- **`xa` A.5(ii)'s poison-row probe has no retained producer.** It is described and tabulated but no script
  survives; it is trivially re-derivable and independently corroborated by `xc` C.3's G2b numbers, which
  *are* backed by a committed capture. This is the same provenance weakness item 7 penalises in
  `probes.json`'s `recheck` block, and it sits on a §5 non-negotiable. Recorded in `xa`'s attestation.
- **`xb` B.4's published 17 342 does not reproduce under any reading of the instrument `xb` names**, and
  the writer-drift explanation is unavailable (see the refusal). Either the original census miscounted by
  3, or it did not use the named instrument. Disclosed rather than papered over. **[punch] Withdrawn — it
  does reproduce, and neither disjunct holds.** 17 342 is this same table read **one checkpoint earlier**.
  `immutable=1` ignores the live `-wal` and reads the main db file only; it does not follow that the count
  is fixed — it moves **when a checkpoint lands** rather than continuously with the writer, and one did.
  Verified here against the spike's own retained sweep output `xd_sweep.json` (session scratchpad, written
  14:16:57, same `mode=ro&immutable=1` instrument): `guts-ledger`/`instances` holds `LedgerRecord` **17 145**
  + `WorkOrder` **197** = **17 342**, the published figure exactly, and `guts` / `guts-code` sum to 12 095 /
  6 710 there as `xb`'s table prints them. The checkpoint (main-file mtime **14:16:56**) moved the table to
  `LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345** — the same single event behind `xd` D.1's
  17 145 at 14:14 → 17 148 at 14:20. `xb` B.4 now carries this reconciliation and withdraws its own
  *"a writer cannot move an `immutable=1` count"* and *"superseded and unexplained"* as over-claims. **The
  refusal recorded above is untouched:** the prescribed `+ 5` was still wrong for the reason given, and
  **17 345** is still the figure — what changes is that the 3-row residual is now explained rather than
  unexplained, and that the figure is a snapshot pinned to a checkpoint, not a standing property of the
  store.
- **`xb`'s one-off `::jsonb` probes in B.4–B.6 were scratchpad-only and are not retained** — unlike `f3`'s
  DDL there is no artifact a reader can open to check them. Same grey-area class as item 24's two.
- **`xb` B.1's grep-derived counts are measured over `f1.md`–`f5.md` only**, and those files were rewritten
  by this pass — the `xb` seat flagged that they could go stale, and ***checked at assembly, two of the four
  have.*** `_pass_filters` (0 in all five) and `_field_value` (0/0/0/1/0) still hold. `find_actual_key`,
  published as **0 in all five**, now returns **2 hits in `f5`** — introduced by item 19's repair, which
  carries `xb`'s own scope note and names the helper. `_sort_key`, published as **0/0/3/3/1**, is now
  **0/0/4/3/2**. B.1's *argument* is unaffected — the identifiers remain absent from findings 1 and 2, and
  `f5`'s new hits exist only because a repair quoted `xb` — but the published counts no longer reproduce.
  Not repaired: `xb` is read-only to the assembly seat.
- **`f3` §3.6 H4 cites `sources.py:99-115` for `_sort_key`; `analysis/index-shape.md` §7.4 cites
  `:99-119`.** `f3` is **right** — `def _sort_key` opens at 99 and its last statement is line 115 — and
  `f3` §3.7 item 5 already records this as a drift fix. Noted so nobody "corrects" `f3` back to the wrong
  number.
- **`xb` B.8 row 6's "ranks 0/1/2/4" is shorthand.** The rank *expression* does emit a rank-3 value
  (`bench.py:94-96`, `ELSE 3`); what is not compiled is rank 3's sort **key**, so all container values tie.
- **The word-count figure in `f5` §5.10 is unresolvable and was left alone.** `f5` says ~117 000 words;
  `consistency.md` §16 says it checked ~119 k. Neither is checkable after the fact — the `.parts/`
  directory has since gained `critic.md`, `consistency.md` and this pass's additions. Per the pass's own
  rule against inventing numbers, no figure was substituted.
- **`f5`'s "stated against the spike" list is now longer than its headline comfortably carries.** Item 9's
  residual — `conformance.py`'s outcome-assignment branches exercised by nothing — is qualitatively
  different from the other three disclosures: it touches **the instrument that produced the 130/130
  headline itself**, and `FRAMING.md` §8 named this exact failure mode in advance. The `f5` seat stated it
  plainly in place rather than softening it, and recorded that whether "130/130, answered yes and audited"
  should still lead §5.9 is a judgement **above the repair seat's authority**.
- **`xd` D.3–D.5 does not bound D11's reachability.** `xd`'s four predicates screen for magnitude,
  non-ASCII digits, non-ASCII whitespace and significant digits — **none** screens for offset-bearing or
  out-of-`datetime`-range date strings, which is the shape carrying D11 and `xa`'s R1/R2 raise → value
  witnesses. Stated in place in `xc` C.13; it means adjudication C's closure is **empty for the FRAMING §5
  clause-2 breach**.
- **`f1` §1.9.2's "40 of 45 agree" is, strictly, 39 measured agreements plus one mislabelled control** —
  `E_dates.py:42` is captioned "NBSP U+00A0 padding" but holds a plain space. `f1` §1.10 already discloses
  the mislabel in place; the 4 `PY_RAISE` are unaffected and were re-verified.
- **`xd` D.7's cross-reference makes one clause in `f4` stale** — `f4` now says "`xd` D.7 compares itself
  only to `f3`'s 8% generator", which stopped being true when `xd` added the reciprocal pointer. Cosmetic.

### What the repairs did to the argument

The verdict was **not** the repair seats' to move, and none moved it: `f5` still recommends **NO-GO**.
Several repairs **weaken** individual legs of it, and each seat was required to say so **in place**, in a
labelled sentence, rather than let the recommendation absorb the change. This table is a finding-aid to
those in-place statements, not a substitute for reading them.

| leg | direction | where it is stated in place |
| --- | --- | --- |
| Gap 13 leg (b) — indexability | **narrowed.** "No index containing compiled output can be created at all" was false. Restated as no compiled *predicate* and no compiled *derive* column, with S1 measured index-backed at 0.065 ms. The coupling the leg exists to establish **survives** — the index that would fix leg (a) is a *predicate* index, still refused — but at its true strength | `f5` §5.3(b), §5.9(4); `f3` §3 opening (which never over-claimed) |
| `f5` §5.5 reason 3 — the cheaper alternative | **weakened, the largest single movement in this pass.** Both halves were overstated: `sources.py:61`'s comment anticipates *pushdown*, so read correctly it is evidence **for** the ticket's premise; and the alternative is **≈2.0× slower than today's latency** while leaving the 98%-of-time acquisition and the 2.4 GB heap in place. Reason 3 now claims only that the alternative is cheaper **to build** | `f5` §5.5(3) and the marked paragraph at the end of §5.5 |
| the performance leg | **firmer.** Demoting the un-audited `recheck` block raises the floor from 2.55× to **3.79×** — worse for the compiled arm | `f4` §4.9(2); `f5` §5.3(a), §5.5(3) |
| the fixture-adequacy leg | **firmer.** 130/130 was scored by a harness whose "compiled and diverges" and "did not compile" branches have **never been emitted, only inferred** | `f5` §5.2, §5.9(6); `f1` §1.7 |
| the FRAMING §5 *null → value* breach | **weakened.** Reachability is no longer "not established"; it is **measured at zero** for these corpora (0/5,235,942; 0/1,096,202; 0/5,236,427). It becomes an argument about **exposure**, not observed harm | `f1` §1.9.3 bottom line, §1.11 item 6; `xc` C.13 bullet 1 |
| the FRAMING §5 *raise → value* breach | **unchanged, and larger than `f1` had stated** — 8 mechanisms across 9 source lines and 4 exception types, firing on the **expression text a tenant writes**, with no unusual stored data. Untouched by the reachability sweep | `f1` §1.9.3; `xa` A.2, A.5(i) |
| the fallback-is-not-a-harbour leg | **firmer.** An unadjudicated worry became a measured failure: uncaught `OverflowError` at any poison-row position, and 40.9% of SQL raises also raise in the retry | `xa` A.5(ii); `xc` C.13; `f5` §5.4(2) |
| the `MAX_SCAN`-urgency leg | **weakened.** The 88%/38%/4% recall collapse is real but is a property of the **synthetic sweep**; no collection on this machine is over the cap. "The cap silently changes the answer once crossed" survives; the implied "and it is being crossed" does not | `f4` §4.7(iii) |
| the totality premise | **the pro-GO datum is retracted**, not replaced. `f2` §2.4's "403 independent confirmations" is deleted and the count kept. `f2`'s two null-mismatch rows (**0** value → null, **0** null → value) are untouched | `f2` §2.4 and its new footnote |
| seat [1]'s value-vs-construct argument | **narrowed.** `xc` C.1 shows it forecloses a *detecting* subset, not a construct-keyed one — and `f5` §5.7 instantiates a construct-keyed subset. §5.2's ruling now rests on fixture adequacy, which is where the evidence is | `f5` §5.1, §5.2, §5.4(5) |
| `f3`'s no-per-key-DDL route | **narrowed at the headline** — 3/130 (2.3%) → **2/130 (1.5%)**, one distinct expression, matching what §3.5(c) already said | `f3` §3 summary line, §3.5(c) |
| `xb`'s 4 166-row claim | **unchanged, arithmetic tightened.** Denominator 17 342 → **17 345**; numerator and rate exact and unchanged. `xb` and `xd` now reconcile with zero residual | `xb` B.4; `f5` §5.4(3) |

`f5`'s own summary of where this leaves a reader who wants to rule the other way, stated in §5.5 so the
gate does not have to find it: **attack reason 3 and leg (b) first, because those are the two the evidence
now supports least.** `human:owner` decides at the `sp_decide` gate.

### Assembly

`FINDINGS.md` is the concatenation of the ten part files in the order `f0 · f1 · f2 · f3 · f4 · xa · xb ·
xc · xd · f5`, copied **byte-for-byte** (verified: each part's bytes occur in the assembled file, in order,
without overlap). The only content the assembly seat wrote is the two header repairs marked
**[consistency]** in §0, the Contents table, and this section. No body part was edited at assembly; the
defects found in body parts at assembly time are reported above, not repaired. Heading structure was
checked, not changed: **one h1** (the title), **ten h2 sections** plus the header's own, all subsections
below them. All artifact links resolve from `spikes/T-1/` — verified by opening all sixteen targets. No
part links to another part file by filename.

**One caveat a reader should have.** The parts cite each other in prose as "`f1` §1.4", "`xa` A.5(ii)",
"`xc` C.8" — that idiom survives concatenation and was left alone. But a handful of citations in `xd` and
`f5` use the **file:line** form (`f1.md:693-701`, `f3.md:611`) against the *part* files, whose line numbers
do not correspond to `FINDINGS.md`'s. Those were **not** rewritten: converting a line range to a section
reference is a judgement, not a mechanical fix, and this pass's rule was to report rather than guess. The
`.parts/` directory is kept beside this file, so they still resolve.

### Punch-list round

The assembled `FINDINGS.md` — 4,926 lines, written at **16:00:42** — was then read by **three adversarial
lenses**. All three returned the same bottom line: the evidence is sound, `f5`'s **NO-GO** still follows, and
**nothing they found is decision-blocking**. Their findings — **21 items, all dispatched as "credibility" or
"minor"** — were turned into a punch list and worked under the same standing rule as the repair pass:
**verify against the raw artifact before writing, and where the artifact disagrees, refuse and report.** Each
in-place edit from this round is marked **[punch]**, so it stays distinguishable from **[consistency]**.

**A weakness in this record, stated before the record.** The three lens reads are **not retained as files.**
`.parts/` keeps `verifications.json`, `critic.md`, `panel.json`, `consistency.md` and `closure-reports.md`
from the earlier passes, but there is no lens artifact — so *"21 items, none decision-blocking"* is the
dispatch's count, not one a reader can re-derive. The same holds one level down: **no repair seat's report is
retained, in either round.** This log is their only record, and it is written from reports that reached the
bookkeeping seat, not from files on disk. Where a report did not reach this seat, the row below says so and
the entry is read off the seat's own in-place text instead.

#### What was repaired

| seat / file | what changed | verified against |
| --- | --- | --- |
| **`xc`** `xc-fallback-register.md` §C.8 headline, §C.11(b) | The register's bolded headline mixed units: *"15 detectable, 18 undetectable"* adds an **id** count to a **class** count, sums to **33**, and names a **34-id** register. Restated in one unit at a time and closed in both — **15 detectable ids + 19 undetectable ids = 34**; folding D21 into D1–D5, **15 + 18 = 33 classes** — with the fractions given rather than the word "half": **19 of 34 ids (55.9%)**, **18 of 33 classes (54.5%)**. §C.11(b)'s *"34 ids, of which 18 are invisible"* now holds the class unit throughout. **No register figure changed**; both fractions are above half, so the section's force is unchanged | Read in place, and the counts taken off C.8's own two id lists rather than off the prose: **15** detectable ids (C1–C4 · D6, D7, D9, D14, D19, R1 · D20 · S1–S3 · R6) and **19** undetectable (D1–D5, D8, D10–D13, D15–D18, D21–D23, R2, R5) — 15 + 19 = 34 ✓, 18 once D21 folds, 19/34 = 55.9%, 18/33 = 54.5%. The Block A/B/C re-extraction behind them is that seat's. `consistency.md` item 15 had already ruled the underlying figures right ("**xc is right**") — the defect was the headline only |
| **`xa`** `xa-totality.md` — nine marked edits: the section preamble, §A.2's R4 row, §A.3 (×2), §A.5(i), §A.6 (×3), and a punch-pass addendum | The f2 sentence `xa` argues against — *"403 independent confirmations of the totality premise"* — **no longer stands in f2**, which deleted the inference and kept the count during the repair pass. The quotation is now introduced as f2 *"as first drafted"*, with a reading note saying so; §A.3's *"is therefore"* became *"was therefore… which is why §A.6 ordered the inference deleted, and why f2 has since deleted it"*; the verdict paragraph's *"is wrong"* became *"was wrong — and f2 has since withdrawn it"*. §A.6 gained a **"two applied, two recorded"** status block: the corrections ordered onto `f1` and `f2` are applied and were re-read to confirm it, while `recon/semantics.md` §11 and `FRAMING.md` §5 are read-only to this pass and are **recorded, not applied**. §A.6's `f1` row dropped the drafted 4+3+3-of-11 sub-clause for the countable form — **10 direction rows carrying 11 witnesses** (the `floor`/`ceil` row holds two), **4** raise→value either way | Read in place. `f2` §2.4 confirmed to carry the deletion, the retained count and the forward footnote; `f1` §1.9.3 confirmed to still carry its quoted clause and the widened "8 mechanisms across 9 source lines and 4 exception types"; `FRAMING.md` §5 confirmed unchanged. The seat's report reached this log truncated before its refusals section — see below |
| **`xb`** `xb-filters-sort.md` §B.4 | The 3-row residual this log recorded as **unexplained** is now explained, and two of `xb`'s own claims are withdrawn as over-claims (*"a writer cannot move an `immutable=1` count"*, *"superseded and unexplained"*). 17 342 is the same table **one checkpoint earlier**; a checkpoint moves the main-file count, a writer does not. B.4 also now states plainly that 17 345 is a **snapshot pinned to the 14:16:56 checkpoint**, not a standing property: a read-only re-census at 16:21:55 returns **17 398**. **The numerator does not move** — 4 166 at every read taken, pair `run_id`/`_runID` in all of them | Re-verified here against `xd_sweep.json` (session scratchpad, written **14:16:57**, `mode=ro&immutable=1`): `guts-ledger`/`instances` = `LedgerRecord` **17 145** + `WorkOrder` **197** = **17 342** exactly, with `guts` 12 095 and `guts-code` 6 710 as B.4 prints them. No report from this seat reached this log; the entry is read off B.4's own `[punch]` paragraphs |
| **`xd`** `xd-reachability.md` — fourteen marked edits in §D.2, §D.4, §D.9 and seven cross-references | **Citations and reconciliations only, by the seat's own attestation, and no published measurement changed.** Seven `.parts/f1.md:NNN` / `f3.md:NNN` line references — which resolve only inside the working directory and which the rewritten files had made stale — became section references; `f3` §7.3 (an `analysis/index-shape.md` number) became `f3` §3.6; §D.2's census table gained the reconciliation to the swept **37,078**; §D.4 gained the exact **491,813 + 3,302 = 495,115** tie; §D.9's D8/D10 row gained the *"string values + object keys"* label the row it summarises already carried | Read in place: `xd`'s own punch-pass compliance block lists each of the five and asserts 17,148 · 37,078 · 495,115 · 1,096,202 · 5,236,427 · 5,235,942 unchanged. No report from this seat reached this log |
| **`f5`** `f5.md` — eleven marked edits across §5.3(b), §5.4(3), §5.6, §5.7, §5.9, §5.10 and its compliance block | Six corrections, one of which is the new measurement below. §5.4(3)'s denominator **17 342 → 17 345** (numerator and 24.0% unchanged), with `xb`'s snapshot caveat carried across. §5.3(b)'s Gap-13 prop restated: **two obstacles in series and only the first is a refusal** — the wrapper makes the index uncreatable; an index on the character-exact compiled operand *is* created and is still unused, which is **"creatable but unusable", not refused**. §5.6 struck *"monotonic from row 20 001"* — never measured, withdrawn by `f4` §4.7 — for *"monotonic across the six measured sizes, 100 / 100 / 100 / 88 / 38 / 4%"*. §5.10 restated the wall-clock endpoint against `consistency.md` §5 rather than `.parts/` mtimes this pass invalidated, and recorded that the punch-list round emitted **no `worker.started` of its own**, so closure-side effort is **under-counted** by the event record | The seat's report carries its own verification per item and reached this log truncated after four of them; those four name `xb` B.4, `xd_sweep.json`, an independent read-only re-census, `.autodev/events.jsonl`, `f4` §4.7/§4.12 and `f3` §3.3 T4a. Re-verified here: the §5.7 measurement (below) and the §5.4(3) identity |
| **measurement seat** — `proto/closure_subset_coverage.py` → `analysis/subset-coverage.json` | Built the round's one **retained** instrument — `xd` and `f5` each wrote a further walker to a session scratchpad, outside the repository, and those are not retained — and produced its one new published number (below). Read-only, no database, imports the real parser and walks all 130 fixture ASTs | Both files carry **mtime 2026-08-19 16:27:39**, inside this round's window — `proto/` and `analysis/` mtimes are the class of citation this pass's systemic `.parts/` mtime defect does **not** touch. No report from this seat reached this log; `f5`'s compliance block names it as a separate seat and states `f5` read the two files without re-running them |
| **`f0` + this log** (this seat) | `f0`'s audit paragraph rewritten to describe **three** passes rather than one, with the refusal count reconciled; this log retitled, given the two over-claim corrections and row 21's correction above, and this section appended | The reconciliation is counted off the refusal table row by row; row 21 is read off `f3`'s summary paragraph as it now stands; the two over-claims are read off `xc` C.8/C.11(b) and `xb` B.4 as they now stand |

#### The new measurement — the one substantive addition this round makes

`f5` §5.7 names the subset a CONDITIONAL-GO would have to adopt, and until this round its fixture coverage
was published as **NOT ESTABLISHED** (*"computing it is one AST walk over `expr_vectors.json`, unrun"*). It
has been run. **The corrected subset is 32 of 48 constructs and covers 68 of 130 fixture cases — 52.3%.**

- **Re-counted here from the raw artifact** — `analysis/subset-coverage.json`, by tallying the **130
  per-case verdicts** rather than reading its headline block: `panel_subset` **84**,
  `corrected_subset_reading_A` **68**, reading B **62**, reading C **56**, all of 130, reproducing every
  published figure. That checks the file against itself, not the walker against the fixture; the
  independent walk of the fixture was `f5`'s. The construct arithmetic checks too: 10 node types + 4
  arithmetic operators + 6 comparisons + 7 functions + 5 field-path forms = **32**.
- **The control is what makes it credible.** The instrument reproduces `panel.json[0]`'s **84 of 130
  (64.6%)** — a figure computed by a different seat in a different pass — before it reports the corrected
  **68**. `f5` re-derived both again with a separately-written walker.
- **What it does to the argument: it weakens CONDITIONAL-GO, modestly, and moves nothing else.** The panel
  seat's coverage claim was **12.3 points of the fixture too high**; the correction costs 16 cases and
  decomposes exactly (`%` 7, `round` 5, `floor` 2, `ceil` 2). AVOID's price at the corrected subset is
  **62 of 130 refused (47.7%)**, not the 46 of 130 (35.4%) that three other places in `f5` still quote
  from the uncorrected subset. `f5` states in place that this does not move its verdict, which never
  rested on it.
- **What it is not.** A **contract-surface** count, not a fraction of production traffic — there is no
  `DataSource` corpus in either tree (`f2` §2.9) — and it says nothing about the **residual divergence rate
  inside** the surviving 68, which remains unmeasured and is what E1 exists to measure.
- **Grey area, disclosed rather than glossed.** This is a **new instrument built during a repair pass**, the
  same class of grey area `consistency.md` item 24 raised about `xd_sweep.py` and which this log records
  above. It fixes nothing and designs nothing (`FRAMING.md` §3); it counts, read-only, over artifacts the
  investigation already had. But the number is **younger than the investigation that surrounds it**, and
  `f5` §5.7 says so in place. Its own provenance block records `analysis/subset-coverage.json` as the only
  file it wrote, and does not list the script; the script exists and carries the same mtime.

#### What was refused

**One refusal is recorded, and the record is incomplete by construction.** Exactly one report — `xc`'s —
reached this log with its refusals section intact; `xa`'s and `f5`'s were truncated before theirs, and
`xb`'s, `xd`'s and the measurement seat's did not reach it at all. Those five entries are read off the
seats' own in-place text, and a refusal a seat made but did not write into its file would not appear here.
That is a gap in this log, not evidence that there were no others.

| seat | what was refused | the raw evidence |
| --- | --- | --- |
| **`xc`** | Extending the same unit repair into **§C.12 item 1**, which carries the identical id/class denominator switch. Refused on scope — the punch list named §C.8's headline and §C.11(b) only — and on merit: unlike the headline, **C.12 never performs the addition**. It says a run-time fallback "can only ever fire on the RAISE classes. That is **6 of 34**", then "for the **18 undetectable classes** there is nothing to trigger". Each is true in its own unit (6 RAISE ids of 34 ids; 18 undetectable classes of 33), so there is no false arithmetic to correct — only an unannotated denominator switch. Reported instead of edited | `xc` C.12 item 1. `f5` §5.8(a) quotes this exact pair, cites `xc` C.12 by name, and was **already annotated** in the repair pass — so the downstream citation now reads more carefully than the source it points at. One-token fix if a later seat is authorised: insert "(19 ids)" after "the **18 undetectable classes**" |

#### New defects found this round, and not fixed

- **`xc` C.12 item 1** carries the id/class denominator switch described in the refusal above. **Not
  decision-blocking** — both figures are true in their own units and the text never sums them — and not
  edited, because the punch list did not name it and three lenses had certified it.
- **`f5`'s "the measurement seat" is not represented in this log by a report.** Its two artifacts are
  self-describing and were re-derived independently here, so nothing rests on the gap; it is recorded so a
  later reader does not mistake the artifacts' provenance for something this log verified end to end.
- **`analysis/subset-coverage.json`'s `files_written` lists only itself**, not the script that generated it,
  which was written in the same second. Cosmetic; the script is present and named in the JSON's
  `generated_by`.
- **Line-length only, no figure involved:** the `xc` §C.11(b) sentence repaired this round sits on a
  ~200-character source line where the file otherwise wraps near 100. It renders identically; it was left
  unwrapped so the diff does not touch certified prose. Flagged so the assembling seat is not surprised.

#### What this round did to the argument

**Nothing moved the verdict, and no seat's in-place text claims otherwise.** `f5` still recommends
**NO-GO**; all three lenses independently said so before this round began, and every `[punch]` edit
either corrects a citation, restates a figure in one unit, or withdraws an over-claim. Three legs moved at
their edges, and a fourth entry records a figure whose residual is now explained rather than open. Each
says so in place:

| leg | direction | where it is stated in place |
| --- | --- | --- |
| Gap 13 leg (b) — indexability | **narrowed again, one level below the repair pass's narrowing.** "The index that would fix (a) is a *predicate* index, which is exactly the class still refused" was the last absolute standing in this leg. Two obstacles sit in series and only the first is a refusal; the second is **creatable but unusable**, and what lifts it is a change to what `compile.py` emits, not a permission — which is why `f3` §3.4 lists four compiler changes rather than one. The coupling the leg exists to establish survives | `f5` §5.3(b); `f3` §3.3 T4a and §3.4 |
| the `MAX_SCAN`-urgency leg | **weakened at the wording, not at the measurement.** "Monotonic from row 20 001" asserted an onset that was never measured; the six measured sizes stand, and the smallest over-cap size tested (25 000) is already 12% wrong | `f5` §5.6; `f4` §4.7 and §4.12 row 7 |
| the CONDITIONAL-GO reading | **weakened, modestly, and for the first time on evidence rather than on a gap.** The subset a CONDITIONAL-GO would name covers **68 of 130** of the contract fixture, not the 84 the panel seat argued from | `f5` §5.7 |
| `xb`'s 4 166-row claim | **unchanged; its residual explained and its shelf life stated.** 17 342 reproduces one checkpoint earlier; 17 345 is a snapshot, and a later reader will measure a larger denominator against the same numerator | `xb` B.4; `f5` §5.4(3) |

#### Assembly, as it now stands — four changes the next assembling seat needs

The *Assembly* note above describes the **previous** round's assembly and was left as written. Four things
have changed since it was written, none of them a change to the body:

- **Eleven parts, not ten.** The closure log was appended to `FINDINGS.md` by the repair pass and has since
  been extracted into `.parts/f6-closure-log.md`, so it assembles like any other part. The concatenation
  order is `f0 · f1 · f2 · f3 · f4 · xa · xb · xc · xd · f5 · f6`.
- **This section's anchor changed** with its heading, to `#closure-log--what-the-audit-passes-changed`.
  `f0`'s two links were updated in the same round; a grep across `.parts/` finds no other link to either
  anchor, and `f5` and `xd` refer to this log by **filename**, which is unaffected.
- **`f1`–`f4` were not edited this round** — no `[punch]` marker appears in any of them — so the five files
  the punch-list round rewrote are `xa`, `xb`, `xc`, `xd` and `f5`, plus `f0` and this log.
- **The part-file `file:line` citations that note flags are gone.** `xd` converted its seven to section
  references this round, and a grep across every part now finds no `f<n>.md:<line>` or `x<x>-….md:<line>`
  citation at all. The `.md:<line>` citations that remain point at `analysis/index-shape.md` and
  `analysis/coverage.md`, which are stable files a reader can open.

#### Compliance — this seat, this round

Read-only except for the two files this seat was permitted to write: `spikes/T-1/.parts/f0-header.md` and
`spikes/T-1/.parts/f6-closure-log.md`. **No defect found by this spike was fixed** (`FRAMING.md` §3), no
database was contacted, no Postgres connection was opened, and nothing in `proto/`, `analysis/`, `recon/`,
either GIMS tree, `.autodev/` or any other part file was modified — `FINDINGS.md` included, which a later
seat regenerates from the parts. Read to verify the entries above: `.parts/consistency.md` (items 12, 15, 21
and the verdict), `FRAMING.md` §3/§4/§5, `.parts/closure-reports.md`, and the current state of `f3`
(§3 summary, §3.5(c)), `xc` (§C.8, §C.11(b), §C.12), `xb` (§B.4), `xa`, `xd` and `f5` (§5.7, §5.9, §5.10 and
the compliance block); `analysis/subset-coverage.json` re-counted with `python3`; `xd_sweep.json` re-read
from the earlier session's scratchpad; `ls --full-time` over `proto/` and `analysis/`. **The verdict was not
this seat's to move and was not moved.**

---

### Final-check round — the one edit the fourth adversarial read asked for

After the punch-list round the assembled document was read once more, adversarially, end to end. That
read returned **gate-ready, 5 defects, none decision-blocking**, and independently re-derived the
round's newest claim: it wrote its own AST walker against the real parser and reproduced **84/130** for
`panel.json[0]`'s subset (the control), **68/130 (52.3%)** for the corrected subset, the `% 7 / round 5 /
floor 2 / ceil 2` decomposition with zero multi-blocker cases, and all three container-operand readings
(68 / 62 / 56). It also confirmed the assembly reproduces byte-identically (sha256
`3032b5f2…`) and that the refusal count reconciles 5/4/3 across `f0`, this log's prose and its table.

Its one substantive finding was that **this document understates its own case**, and one edit was applied
in response — by the dispatching session, inline, against an artifact that already existed:

| where | what changed | verified against |
| --- | --- | --- |
| `xc` §C.10 | "one hole that matters" → **two holes, the larger measured**. D1–D5 survives the corrected subset: `analysis/fuzz/A_f8_guard.txt` §A2 measures **8 of 16** paths diverging at `a = 1e300` as entirely in-subset, three of them order comparisons (the pushdown-predicate path), and `max($.l)` returning SQL `1` for Python's `1e+300` — a silently wrong *number*, FRAMING §4's disqualifying clause verbatim | `analysis/fuzz/A_f8_guard.txt` §A2 (16 of 20 paths diverge); `analysis/subset-coverage.json` → `subset_definition.corrected_functions` = `abs coalesce count if length max min`, `closure_removes.functions` = `ceil floor round`, `closure_removes.operators` = `%` |
| `f5` §5.5 reason 1 | the subset's residual is "not merely unmeasured but **partly measured and non-empty**", citing the same eight paths | same |
| `f5` §5.7(ii) | "still **unmeasured**" → "**not fully measured — but no longer zero-by-assumption**"; what remains unmeasured is the *rate* | same |
| `xc` §C.12 item 1 | "18 undetectable classes" → "18 undetectable classes **(19 ids)**", closing the last unannotated id/class denominator switch, which `f5` §5.8(a) already carried | `xc` §C.8 register rows |

**Direction: every one of these strengthens the NO-GO.** They remove ground a CONDITIONAL-GO advocate
could have taken because the document had conceded it unnecessarily. The four remaining defects from that
read were left as reported — a disclosed units slip, a 24-vs-23 item count the log corrects itself two
paragraphs later, a self-referential grep claim, and a citation-precision slip in an E1 parenthetical.
None is decision-blocking and none touches a measurement.

**The verdict was not moved by this round either.** It was tested a fourth time — against a live read of
`resolve()` in `GIMS-Project/api/dashboard/sources.py`, which returns exactly
`{"records", "count", "truncated"}`, with no `pushed_down` and no `fallback` field — and it held.

---

### Amendment round — three corrections a dead closure seat never applied

**Date: 2026-08-21. Authority: the owner, 2026-08-21 — the ruling recorded as go-ahead `GA-3`** in this ticket's
event log (`.autodev/events.jsonl`), whose item 2 reads *"Fix them — re-fingerprint the document."* Nothing
in this round is discretionary: it applies **three named corrections and nothing else**.

This is the first round to change `FINDINGS.md` since the final-check round above, and the first change of
any kind made to it **after** its contents were fingerprinted — see *Fingerprint* at the end of this entry.

#### Why there was anything left to fix

Two terms, since they are this document's own shorthand and not general English. A **closure pass** is the
round in which one worker per finding takes the list of corrections an independent verifier raised against
that finding, re-checks each one against the raw file it names, and then edits the finding in place. A
**seat** is one such worker — one finding, one worker, one report.

The seat for **Finding 2 — Coverage and fallback** never finished. It lost its API connection mid-response
and died. The only record of this anywhere in the spike is six words in
`.parts/closure-reports.md:13` — *"(agent died: API connection lost mid-response; file untouched)"* — and
`FINDINGS.md` did not disclose it at all. Worse, `f2`'s own compliance block (`:1330`) states that a single
§2.4 edit "is the only change made to this file after it was first written", which reads as a clean bill of
health rather than as the trace of a pass that never ran. Meanwhile the verifier's list survived intact:
`.parts/verifications.json → Finding 2 — Coverage and fallback → corrections` holds **six** corrections. All
six were lost with the seat. The 2026-08-21 re-check found them and re-derived them
(`RECHECK-2026-08-21.md` §3.2, and §6, which assigns the third of them here); **three** were confirmed as
live errors still standing in the published text. Those three are what this round applies.

#### What this round changed — three edits

Each is marked **`[amend-2026-08-21]`** at the point of change, with its own account of what the text used to
say and why it was wrong, so a later reader is never left comparing this file against its recorded checksum
with no explanation for the difference.

| # | where | what changed | re-verified here against |
| --- | --- | --- | --- |
| **A1** | `f2` §2.6, the C3 table (`:1124` as fingerprinted) | *"first failing size"* for `1 or 1 or …` / `1 and 1 and …` / `not not …1` corrected from **400 / 334 / 499** operands at **1996 / 1999 / 1997** chars to **333 / 333 / 332** at **1661 / 1993 / 1329**. The old integers were the *largest* chains fitting under `MAX_SOURCE_LEN = 2000`, not the first that fail — the ceiling published as the floor, which understated how easily C3 is reached. Direction: **against the compiler**, i.e. the defect is worse than published | Fresh bisection through the real `expr.parse` into `proto/compile.py`: `n−1` compiles and `n` raises for each of the three; all three still evaluate correctly in Python at the failing size; and the old 400 / 334 / 499 confirmed to be exactly one operand short of exceeding 2 000 characters. `verifications.json` `corrections[0]`, severity **material** |
| **A2** | `f2` §2.6, the C4 paragraph (`:1143-1144` as fingerprinted) | *"The parser permits depth 64 and 2000 characters permit depth 165"* → **depth 63**, with the second clause dropped as moot. `_primary` increments the depth counter **and then** tests it (`expr.py:185-187`) against `MAX_DEPTH = 64` (`expr.py:40`), so the counter reaches 64 only on the expression that is rejected and the deepest surviving nesting is one below the constant. The character budget never binds, because the depth guard refuses a 165-deep nest first | The GIMS source read directly, plus a live measurement: a 63-deep `date_add` nest parses, a 64-deep one raises `ExprError("Expression nesting too deep")`. Conclusion unaffected — 63 is still far past 24. `verifications.json` `corrections[5]` |
| **A3** | `f2` headline summary table (`:925` as fingerprinted) | The unscoped **403 / 403** out-of-fixture row is now scoped to **value-domain *kind* probes**, with a note recording the second, separate out-of-fixture set the table omitted: `proto/results.json → out_of_fixture_probes`, **8 probes — 3 agree, 4 `DIVERGES`, 1 `SQL_ERROR (totality violation)`**. Direction: **against the compiler**; a gate reader scanning only the table previously took away "100% clean out-of-fixture probing" | `proto/coverage_probe_results.json` re-counted: 403 entries, all `COMPILED_AGREES`. `proto/results.json` re-counted: `Counter({'DIVERGES': 4, 'agrees': 3, 'SQL_ERROR (totality violation)': 1})` over 8 probes. §2.5 and §2.7 R1–R4 confirmed to carry the four divergences already, so the body was never wrong — only the summary row. `verifications.json` `corrections[1]`, severity **material**; assignment per `RECHECK-2026-08-21.md` §6 |

**Every correction was re-verified against its raw artifact before a character was changed**, under the same
standing rule the consistency-repair pass worked to. None was refused: all three held.

#### What this round did NOT change

- **The other three of the six lost corrections are still unapplied.** All three are severity **cosmetic** in
  the verifier's own grading, and none was re-run by either 2026-08-21 seat, so none has been re-verified
  against its source: `corrections[2]` — §2.9's `cascade_deep_search` quotation is a splice of two different
  docstrings presented under one `deep_search.py:389-390` cite (the substantive claim, that the function is
  pure and does no I/O, is correct); `corrections[3]` — §2.9's `gims-ledger` sweep is described as covering
  "every SQLite database" when 2 of 33 files are malformed and were silently skipped (the n=1 result itself
  reproduces); `corrections[4]` — §2.1's line cites for unary `+` and for parentheses are both off by a few
  lines (the claim they support is correct). They are recorded here so the residue is visible rather than
  forgotten a second time.
- **Nothing else in the document was touched.** Every other correction the re-check found — the spent
  "never emitted" residual at `:5193`, the `+463%` framing and its orphan measurement block, the seat-count
  arithmetic, the three non-reproducing command outputs — is recorded in `RECHECK-2026-08-21.md` and was
  **out of scope for this round**, which was authorised for three named items only.
- **The verdict was not moved, and was not this round's to move.** All three corrections point the same way:
  each makes a defect look slightly worse than the published text did, so none of them can weaken a
  **NO-GO**. No measurement was re-run, no database was contacted, and no defect found *by* the spike was
  fixed (`FRAMING.md` §3).
- **Read-only elsewhere:** `FINDINGS.md` is the only file this round wrote. Both GIMS checkouts were read
  only — `expr.py` was read and its parser exercised in-process, nothing written. `proto/`, `analysis/`,
  `.parts/`, `RECHECK-2026-08-21.md`, `tracker.mjs`, `.autodev/tickets/` and `.autodev/events.jsonl` are
  unmodified.

#### Fingerprint

This document's sha256 as fingerprinted before this round — the value carried in `.autodev/events.jsonl` as
the evidence fingerprint of the earlier stage — is:

```
67fbe421adccd5cb8ad80d4f21127c04e2966df2b1d446a07ccc864c195a38c8
```

That value is **superseded** by this amendment and will no longer match this file. It is left standing in the
event log, which is append-only and was not edited here; the driving session records the supersession and the
new digest against `GA-3`. Anyone auditing this document should compare against the new digest, and read this
entry as the reason the two differ.
