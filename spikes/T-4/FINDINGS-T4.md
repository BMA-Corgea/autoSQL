# T-4 · FINDINGS — the timing run: how long does a person actually wait?

**Run date:** 2026-09-08, 17:59:44Z → 18:45:18Z · **Verdict: FAIL** (§4.5)
**Driven by:** an agent on the owner's recorded authority (GA-24; the true actor is recorded in the ledger, which is not public) · harness `spikes/T-4/bench_t4.py`

> ## THE WIDGET IS INVENTED
> Every number below for the `load_score` widget is a measurement of a widget **nobody
> uses**. It is the default taken under item 7 of the second form, not one of the owner's
> (§7.2). A latency figure silently attributed to real usage is a fabricated result
> regardless of how carefully it was measured (§6 item 3), so the label travels with every
> table here. `days_left` is the original sweep's widget, run as a **control**.

---

## 1. The verdict, and what decides it

**FAIL.** At every size that was measured on a clean host, the shippable compiled path
(**arm C**) misses its absolute bar *and* fails §4.2's kill condition against the Python
path measured in the same session.

**The verdict rests on 20,000 and 100,000 rows, both taken on an exclusive host.** The
1,000,000-row cells were disturbed partway through (§3) and are reported with that
disclosure; their measured cost turned out to be **zero**, but the verdict does not lean on
them. Under §4.5 that changes nothing either way: *"a miss is evidence; a gap elsewhere
cannot cancel it"*, and FAIL stays FAIL even where another size is untested.

### It is not a near miss, and it is not a regression from what was believed

**T-1 put the compiled path at 3.79×–7.15× slower than Python. This run measures it
faster than that — and it still loses.** The refinement is real and it runs in the
compiled path's favour, which is worth stating plainly rather than reporting only the ways
the thing failed:

| C ÷ A, same session | 20,000 | 100,000 | 1,000,000 |
|---|---:|---:|---:|
| **INVENTED widget** — the one the bar applies to | **2.09×** | **2.56×** | **2.55×** |
| `days_left` control — T-1's own widget, the like-for-like comparison | 3.18× | 4.90× | 5.35× |

Two things follow. **The ratio is flat across two orders of magnitude** — 2.09× to 2.55×
while the row count moves 50-fold — so this is not a curve that crosses over at some larger
size. T-1's "no crossover" is *confirmed by independent measurement*, not merely repeated.
And **the honest comparison against T-1's 3.79×–7.15× is the date control**, since that is
T-1's widget: at 3.18×–5.35× it is a genuine improvement on the recorded range and still
nowhere near 1.0×. The invented widget does better again at ~2.5× and still loses.

**A design that is 2.5× slower than what exists does not become viable by being tuned;
it becomes viable by not doing the same work.** §4 of this document says where that is.

### Arm C — the shippable path, the arm the bar applies to · widget INVENTED

| rows | median | **bar** | | tail | **tail bar** | | same-session Python (arm A) | **§4.2 requires** | |
|---:|---:|---:|:--|---:|---:|:--|---:|---|:--|
| 20,000 | **413.76 ms** | ≤ 350 ms | **MISS** | p95 421.50 | ≤ 700 ms | pass | 197.94 ms | ≤ 297.94 ms (+100) | **MISS by 115.82 ms** |
| 100,000 | **2,004.61 ms** | ≤ 1,000 ms | **MISS ×2.00** | p95 2,019.11 | ≤ 2,000 ms | **MISS** | 784.04 ms | < 784.04 ms | **MISS — 2.56× slower** |
| 1,000,000 | *21,085.00 ms* | ≤ 5,500 ms | *(not relied on)* | worst of 9 *21,474.89* | ≤ 8,331 ms | *(not relied on)* | *8,277.16 ms* | < 8,277.16 ms | *(not relied on)* |

**The kill condition is failed at 100,000 rows on clean evidence.** §4.2: *"Failing to beat
what already exists is a kill whatever the absolute number."* The compiled path is
**2.56× slower** than the Python path it would replace, measured on the same rows, in the
same session, on a host whose load is recorded at both ends.

At 20,000 rows the test is the softer one — no perceptible regression, within +100 ms of
the same-session Python median — and it is missed by 115.82 ms.

### §4.2's own built-in check on whether the host was quiet — and it passes

§4.2 does not only set the kill line. It ships a **falsifiable test of this run's own
conditions**, written before any evidence was collected:

> *"If the same-session Python median lands far from 8,331.43 ms, that is itself evidence
> the host was not quiet, and §6 item 1 voids the cell."*

| same-session Python (arm A) at 1,000,000 | measured | vs the recorded 8,331.43 ms |
|---|---:|---:|
| INVENTED widget | 8,277.16 ms | **0.65% apart** |
| `days_left` control | 8,442.60 ms | **1.33% apart** |

**Both land inside one and a half percent of a figure fixed in advance.** This is the
strongest single line of evidence in the run that the numbers were taken on a quiet
machine, because it is **independent of the load averages recorded here and independent of
the host having been cleared** — it is an outcome measure, not a process one. Anyone
arguing a kill verdict was measured on a dirty host has to explain how a dirty host
reproduced a pre-registered figure to within 0.65%.

One precision, because §7.2 forbids the obvious misreading: **this is not the old corpus.**
Adding the two generator fields shifted the random stream, so 999 of every 1,000 rows
differ from the rows 8,331.43 ms was measured on. That is exactly what makes the agreement
meaningful — it is a check on the *host and the instrument*, not a row-level reproduction,
and it is the use §4.2 prescribes.

---

## 2. Full table, all five arms, both widgets

Median is the headline (§5.2). `p95` appears only where n ≥ 20; below that the column is
`worst of n`, which is the maximum under its own name rather than a percentile wearing a
misleading one.

### 20,000 rows — n = 25 · host load 0.38 → 0.86 · CLEAN

| arm | widget INVENTED | | | | widget `days_left` (control) | | | |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| | median | p95 | max | stdev | median | p95 | max | stdev |
| A — today, capped | 197.94 | 205.93 | 210.76 | 8.84 | 285.71 | 297.44 | 298.03 | 9.39 |
| A-uncapped | 196.63 | 204.54 | 207.45 | 8.27 | 287.34 | 309.63 | 311.09 | 11.47 |
| **C — shippable** | **413.76** | **421.50** | 451.06 | 7.87 | **907.00** | **919.09** | 920.87 | 5.94 |
| B2 — all in SQL | 473.22 | 485.75 | 490.94 | 5.48 | 1,073.40 | 1,082.50 | 1,085.71 | 4.08 |
| B4 — native ops | 9.07 | 10.72 | 10.78 | 0.62 | 12.52 | 12.80 | 12.96 | 0.16 |

### 100,000 rows — n = 25 · host load 0.86 → 1.07 · CLEAN

| arm | INVENTED median | p95 | stdev | control median | p95 | stdev |
|---|---:|---:|---:|---:|---:|---:|
| A — today, capped | 784.04 | 836.79 | 25.96 | 876.81 | 898.70 | 20.21 |
| A-uncapped | 1,053.25 | 1,075.40 | 18.06 | 1,506.18 | 1,534.42 | 19.52 |
| **C — shippable** | **2,004.61** | **2,019.11** | 14.02 | **4,298.74** | 4,319.01 | 9.28 |
| B2 — all in SQL | 2,403.37 | 2,416.46 | 8.93 | 5,210.69 | 5,665.57 | 242.04 |
| B4 — native ops | 28.43 | 28.89 | 0.33 | 34.53 | 35.46 | 0.47 |

### 1,000,000 rows — n = 9 · NOT RELIED ON (see §3)

| arm | INVENTED median | worst of 9 | control median | worst of 9 |
|---|---:|---:|---:|---:|
| A — today, capped | 8,277.16 | 8,653.72 | 8,442.60 | 8,747.46 |
| A-uncapped | 11,949.00 | 12,018.77 | 16,715.62 | 17,156.03 |
| **C — shippable** | **21,085.00** | 21,474.89 | 45,188.61 | 46,770.27 |
| B2 — all in SQL | **VOID** `host_load` | — | 55,116.89 | 55,950.09 |
| B4 — native ops | **VOID** `host_load` | — | 246.18 | 248.49 |

---

## 3. HOST-STATE DISCLOSURE — the 1,000,000-row window was disturbed, and it cost nothing

A run that says *"the host was quiet"* is worth less than one that says *"the host was
disturbed here, this is what it did, and here is the measurement showing it did not
matter."* This is the second.

**What happened.** At **18:14:42Z**, mid-flight in the 1,000,000-row size, a browser was
launched on the host and the owner's GUTS development stack came back up — the GEDS
`--reload` spin-loop at **85.8% of a core**, four uvicorn servers and a vite front end. A
wallet application followed at 18:44:34Z. None of it was this session's. The foreman
stopped the GUTS stack again under GA-25 at about 18:17Z and **deliberately did not send
word during the window**, because messaging the driving session would have started a turn
inside a timed cell, which §5.1 item 4 forbids. That was the right call and it is recorded
here rather than in a private message.

**The load peaked at 1.98**, and the harness read **2.14** at one cell boundary.

**What it cost, measured rather than assumed:**

| check | result |
|---|---|
| repetitions lost to the disturbance | **0** — `excluded_void_reps` is 0 on **every arm at every size** |
| repetition counts | intact: **25 / 25 / 9**, exactly as §5.2 rules |
| loadavg recorded across the 1M size | **1.07 · 1.70 · 1.57 · 1.27** — every reading inside §5.1's band |
| cells actually lost | **2** — `B2` and `B4` at 1M INVENTED, both **reported-not-gated** arms |
| gated arm affected | **none** — arm C measured admissibly at all three sizes |
| §4.2's independent host check | **passes to 0.65%** (see §1) |

**The two lost cells are the void path working.** `B2` and `B4` voided with
`host_load: 1-min load 2.14 > 2.0`. That is the harness refusing to report a number
because the host had been disturbed — firing unprompted, on live data, at the moment a real
disturbance occurred. It is the first time in this project's history that a benchmark has
declined to produce a figure rather than printing a plausible one, and it happened to catch
the exact event it exists to catch.

**A correction to two earlier readings of this episode, since both were wrong.**

1. The 2.14 was first attributed to the run's own arms warming the load. That was an
   inference from a top-process snapshot taken at a different moment, and it was wrong:
   the disturbance was external, and is now identified.
2. It was then attributed to the browser alone. Also incomplete — the GUTS stack restarting
   is the larger consumer of the two, at 85.8% of a core.

**Which cells sit inside the disturbed window:**

| cell | window | status |
|---|---|---|
| all 20,000 | 17:59:47 → 18:01:38 | **clean** — entirely before it |
| all 100,000 | 18:01:46 → 18:10:18 | **clean** — entirely before it |
| 1M INVENTED arm A | 18:10:56 → 18:12:25 | clean |
| 1M INVENTED arm A-uncapped | 18:12:25 → 18:14:30 | clean, by 12 seconds |
| **1M INVENTED arm C** | 18:14:30 → 18:18:21 | **spans the disturbance** |
| 1M INVENTED arms B2, B4 | — | **VOID** `host_load` |
| all 1M control | 18:20:16 → 18:43:05 | after the stack was stopped again |

**One methodological finding worth carrying forward.** §5.1 and §5.4 item 1 gate the load
*"when a size starts"* and *"when a size ends"*; the harness applied the start ceiling
**per arm**, which is stricter and makes admissibility depend on arm ordering. The gate was
deliberately **not relaxed** — loosening a bar after seeing a number it rejected is the move
§4.2 forbids, and nothing was bought by it, since the two cells it cost are ungated. The
*missing* half was added instead: §5.1's **size-level end ceiling was never enforced at
all**, and now is.

**What a 1M re-take would buy:** completeness of the table, not an answer. §4.5 makes the
clean FAIL at 100,000 decisive on its own, and arm C's 1M reading — disturbed — is 3.8×
over its bar, so no plausible correction reaches it.

## 4. What the numbers say about *why*, which outlives the verdict

**1. The cost is the runtime, not the tail.** Arm C's split is almost entirely SQL:
411.53 of 413.76 ms at 20,000; 1,971.92 of 2,004.61 ms at 100,000. The Python sort-and-limit
tail that the shippable shape keeps out of SQL costs **0.87 ms and 5.36 ms** respectively.
Moving sort and limit into SQL would win nothing worth having.

**2. The safe runtime costs ~70× the native operators.** At 100,000 rows the same predicate
is 28.43 ms through native Postgres operators (arm B4) and 2,004.61 ms through the `xpr`
runtime (arm C). B4 is not a candidate — it raises on a malformed value where the language
must return null, which is the whole reason `xpr` exists — but it fixes the ceiling:
**the gap between the two is the price of null-safety, and it is the entire problem.**

**3. Arm C's per-row cost is flat; the bar is not.** 20.7 µs/row at 20,000, 20.0 at
100,000, 21.1 at 1,000,000 — against bars of 17.5 → 10.0 → 5.5 µs/row. The compiled path
does not get worse with size; **the bar tightens because a person's patience does not scale
with the row count**, so the miss widens from 1.2× to 3.8×.

**4. The approved cap lift is now measured rather than inferred.** `FINDINGS.md` §5.5 quoted
≈16.7 s at 1M as arithmetic. Measured here for the date control: **16,715.62 ms**. The
inference was sound.

**5. Doing everything in SQL is slower than the shippable split.** B2 > C at every size
(473.22 vs 413.76; 2,403.37 vs 2,004.61) — B2 compiles the derive twice, once to sort by and
once to emit.

---

## 5. Admissibility, and the review round that changed it

**Assume the instrument is wrong until something has tried to break it.** The harness was
written but unproven when this ticket resumed; driving it found four defects that would each
have produced a confident wrong answer, and an independent review then found fourteen more.
Both passes are recorded here because the credibility of every number above rests on them.

### What the review found that mattered

| finding | why it mattered |
|---|---|
| **`buffers_from_plan` summed CUMULATIVE per-node counts** | Postgres reports buffers cumulatively — a parent's line already contains its children's. The date-control 1M B2 plan carries the identical line 4 times and the cell reported **220,860 shared reads: 1.7 GB against a 700 MB table**, an impossible number. Overstated by exactly the plan depth, **4× and 5×**. |
| **§6.1's exclusion checks were helper unit tests** | They called `aggregate()` on a hand-built list — which §6.1 rules out in as many words — and passed while the real exclusion path stayed as dead as `conformance.py`'s three branches, because no repetition could ever void. *This is the project's own defect class, found inside the instrument built to prevent it.* |
| **The identity oracle was `B2`** | `B2` and arm C are built by the same function, so a builder defect would have made arm C agree **by construction** while the two independent implementations were voided as the dissenters. The gate was oriented to bless the arm under test. |
| **Identity compared id lists, not rows** | §6 item 6 says row-for-row. An id check cannot see a wrong *derived value* — and the derived value is the number the widget puts on the screen. |

**The corrected buffer figures do not weaken the run — they confirm §5.3's arithmetic.**
Arm C, the gated arm, was **unaffected** (1.00×): with no ORDER BY its plan is a single Seq
Scan node. Corrected: **0 shared reads at 20,000** (the table fits in the 128 MB cache) and
**56,911 at 1,000,000** (it cannot possibly be warm — §5.3 predicted exactly this from a
700 MB table against 128 MB of `shared_buffers`). Recomputed from the plans stored in the
run's own output, so no re-measurement was required; the raw files are left as produced.
`.autodev/evidence/T-4/buffers-corrected.json`.

**Then the control caught a regression in one of the fixes.** Tightening the index guard to
require an `Index Cond` broke the case proving it *admits* a legitimate pkey lookup. The
fixture was unrealistic, not the guard; it was made realistic, and a new injection (`I3c`)
was added proving a pkey index that answers the **predicate** still voids. That is the
guard discriminating rather than pattern-matching on the substring `_pkey`.

### Standing admissibility

| requirement | status |
|---|---|
| §6.1 negative control, **passed before any millisecond** | **12/12**, `.autodev/evidence/T-4/negative-control.json` — includes the end-ceiling branch, the exclusion clause driven through `run_cell` rather than a helper, and index-guard discrimination in **both** directions |
| §6 item 2 — corpus complete, selectivity 4.5–6.0% | 5.385 / 5.311 / 5.265% (invented); row counts exact |
| §6 item 4 — no index help | every compiled plan is a bare **Seq Scan**; zero index nodes |
| §6 item 6 — arms return the same answer | **row-for-row**, every field at float epsilon, via the frozen `rows_match`, against the **real uncapped Python pipeline** as oracle: `all_agree=True` at every size, both widgets. `.autodev/evidence/T-4/identity-reverified.json` |
| §6 item 3 — invented widget labelled | `"invented": true` in every cell; labelled in every table here |
| §6 item 9 — `synchronize_seqscans` recorded | `on`, read from the run's own container |
| §5.2 — reps and dispersion | 25 / 25 / 9; n, min, median, max, stdev per cell; **no column called p95 below n = 20** |
| §5.3 — cache state measured, never claimed | corrected `shared_hit`/`shared_read` per cell; warm-up recorded, excluded, and flagged where an EXPLAIN preceded it |
| §5.4 items 1–18 | recorded per size, from the run's own container |
| §6 item 11 — nothing written into GIMS | verified: HEAD unchanged, 8 dirty files before and after, 49 `__pycache__` before and after, **zero** written during the session |

**On the claim that the fixes did not change what was timed.** Every generated statement was
diffed against the pre-fix commit and found byte-identical for all five arms, both widgets,
all three sizes. **This is evidence produced by the same agent that wrote the fixes, and it
has not been independently audited.** It is offered as precision about *this document*, not
as support for the ruling: the verdict is a ~2.5× gap at every size, and no statement-level
change plausibly flips that. The in-run `builder_faithfulness` assertion — the t4 builder
reproducing the frozen builder byte-for-byte, checked at the start of every run and recorded
in every output file — is the stronger and independently re-runnable form of the same claim.

**`glp_strong` was not idle.** §5.4 item 16's counters show **354 commits** across the
100,000-row window (`xact_commit` 19,171 → 19,525, `numbackends` 1). Light, but *measured* —
which is the whole point of item 16 — and not the zero that would have licensed the word
"idle".

## 6. What this does NOT decide

`sp_decide` is **the owner's** and is parked, not cleared — GA-24 Q2. This document is the
packet for that ruling, not the ruling. Specifically it does not decide:

- whether the correctness win is worth 2.56× the latency *anyway*, at sizes where today's
  answer is 26% recall and this path is right;
- whether to spend a second exclusive window completing the 1,000,000-row row of the table;
- whether a native-operator path with an explicit null-guard (somewhere between B4's 28 ms
  and C's 2,005 ms) is worth designing, which is the one direction these numbers actually
  point.
