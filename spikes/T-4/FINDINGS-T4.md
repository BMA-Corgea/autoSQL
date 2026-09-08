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
1,000,000-row cells are reported below but are **not relied on** — the host stopped being
exclusive partway through them (§3). Under §4.5 that changes nothing: *"a miss is
evidence; a gap elsewhere cannot cancel it"*, and FAIL stays FAIL even where another size
is untested.

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

## 3. What went wrong with the 1,000,000-row cells, stated plainly

**A browser was launched on the host at 18:14:42Z, mid-run**, 16 minutes after the
hands-off notice went to the owner's phone. A wallet application followed at 18:44:34Z.
Neither is this session's, and neither was stopped — by then a person was plausibly at the
keyboard, and "kill every process that's in the way" (GA-25) does not obviously extend to
closing the owner's browser out from under him.

Cell timestamps place the damage exactly:

| cell | window | status |
|---|---|---|
| all 20,000 | 17:59:47 → 18:01:38 | **clean** — entirely before the browser |
| all 100,000 | 18:01:46 → 18:10:18 | **clean** — entirely before the browser |
| 1M INVENTED arm A | 18:10:56 → 18:12:25 | clean |
| 1M INVENTED arm A-uncapped | 18:12:25 → 18:14:30 | clean, by 12 seconds |
| **1M INVENTED arm C** | 18:14:30 → 18:18:21 | **spans the launch** — the gated arm at the binding size |
| 1M INVENTED arms B2, B4 | — | **VOID** `host_load`, 1-min load 2.14 > 2.0 |
| all 1M control | 18:20:16 → 18:43:05 | after the launch |

**The void path fired for real, unprompted, on live data** — the first time in this
project's history that a benchmark has refused to report a number rather than printing a
plausible one. That is §6.1's whole purpose, and it worked.

**A correction to an earlier reading of it.** The 2.14 was first attributed to the run's
own arms warming the load. The timeline does not support that: the browser was up before
those cells started, so it is at least as likely the cause, and the honest position is that
**the two are not separable after the fact**. The cells stay void.

**One methodological finding worth carrying forward.** §5.1 and §5.4 item 1 gate the load
*"when a size starts"* and *"when a size ends"*; the harness applies the start ceiling
**per arm**. That is stricter than the framing, and it makes admissibility depend on arm
ordering — later arms inherit whatever the earlier arms of the same size left behind. The
gate has deliberately **not been changed**: relaxing a bar after seeing a number it
rejected is the exact move §4.2 forbids, and nothing is bought by it here, since B2 and B4
are reported-not-gated and cannot move the verdict in either direction.

**What a 1M re-take would cost:** one exclusive window of roughly 50 minutes. It cannot
change the verdict — §4.5 makes a clean FAIL at 100,000 decisive on its own — so it buys
completeness of the record, not an answer.

---

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

## 5. Admissibility

| requirement | status |
|---|---|
| §6.1 negative control, **passed before any millisecond** | **11/11 at 17:53:38Z** — `.autodev/evidence/T-4/negative-control.json` |
| §6 item 2 — corpus complete, selectivity in 4.5–6.0% | 5.385 / 5.311 / 5.265% (invented); row counts exact |
| §6 item 4 — no index help | every compiled plan is a bare **Seq Scan**; zero index nodes |
| §6 item 6 — arms return the same answer | `all_agree=True`, every size, both widgets, checked tiebroken |
| §6 item 3 — invented widget labelled | `"invented": true` in every cell; labelled in every table here |
| §6 item 9 — `synchronize_seqscans` recorded | `on`, read from the run's own container |
| §5.3 — cache state measured, never claimed | `shared_hit` / `shared_read` per cell; warm-up recorded, excluded |
| §5.4 items 1–18 | recorded per size, from the run's own container |
| §6 item 11 — nothing written into GIMS | verified: no new `__pycache__`, tree unchanged |

**Two honest notes rather than a claim of a perfectly quiet host:**

- **`glp_strong` was not idle.** §5.4 item 16's two counters show **354 commits** across the
  100,000-row window (`xact_commit` 19,171 → 19,525, `numbackends` 1). Light — well under
  one per second — but *measured*, which is the entire point of item 16, and not the zero
  that would have licensed the word "idle".
- The host was made exclusive at 17:58Z by stopping the AutoDev watch sidecar and the GUTS
  dev stack (a `--reload` API server, a vite front end, and a bridge inside a respawn
  wrapper), all of which were running despite the machine having been reported clear.

---

## 6. What this does NOT decide

`sp_decide` is **the owner's** and is parked, not cleared — GA-24 Q2. This document is the
packet for that ruling, not the ruling. Specifically it does not decide:

- whether the correctness win is worth 2.56× the latency *anyway*, at sizes where today's
  answer is 26% recall and this path is right;
- whether to spend a second exclusive window completing the 1,000,000-row row of the table;
- whether a native-operator path with an explicit null-guard (somewhere between B4's 28 ms
  and C's 2,005 ms) is worth designing, which is the one direction these numbers actually
  point.
