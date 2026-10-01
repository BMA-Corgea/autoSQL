# T-44 · FINDINGS — a faster compiled path, measured against the bar fixed before it ran

**Run date:** 2026-10-01 (overnight) · **Bar:** `FRAMING.md` §4, with the §10 loaded-host
amendment, both committed before the first timed repetition · **Driven by:** an agent on the
owner's recorded authority (GA-34, GA-35; the true actor is in the ledger, which is not public)

> ## THE WIDGET IS INVENTED
> Every millisecond below is for `load_score`, the widget T-4 invented. It is not one of
> the owner's. The label travels with every table.

---

## 0. THE QUIET RE-TIME — PASS (2026-10-01, 09:00–09:09Z)

**PASS on `C_both` under the bar as written** (§4, read under §10). The run went the moment the host
went quiet: the foreman called a quiet window, and the watcher (`quiet_retime.sh`) saw ten
consecutive 1-minute loads under 2.0, 30 seconds apart, the last 1.19 at 08:59:54Z. The negative
control ran first: **25/25** with all eight arms (`out/negative-control-quiet.json`). Numbers:
`out/timing-quiet.json`.

| widget INVENTED · median / p95, ms | 20,000 · num | 20,000 · text | 100,000 · num | 100,000 · text |
|---|---:|---:|---:|---:|
| **C_both** (the verdict arm) | **29.20 / 30.38** | **37.36 / 39.21** | **108.69 / 123.28** | **136.71 / 151.52** |
| C_t52 (T-52's head, the SHIPPING candidate; reported) | 28.84 / 33.35 | 37.24 / 38.69 | 108.46 / 123.88 | 135.69 / 149.98 |
| C_inline | 44.24 | 60.29 | 226.10 | 311.89 |
| C_par | 232.15 | 254.93 | 804.08 | 868.08 |
| arm A, today's Python, same session | 203.66 | 212.62 | 829.46 | 833.76 |
| C_ship, the shipping path before T-52 | 452.17 | 513.66 | 2,237.26 | 2,550.64 |
| the bar | Python +100 | Python +100 | ≤ 300 / ≤ 600 | ≤ 300 / ≤ 600 |

- **C_both meets every condition:**
  - S1 at 100k: ≤ 300 / ≤ 600 ms on both encodings.
  - S2: it beats same-session Python in paired rounds, by a median 719 / 690 ms at 100k (number /
    text) and 173 / 175 ms at 20k.
  - S3 at 20k: well inside Python + 100 ms.
  - K5: identity row for row against the uncapped Python oracle, in every cell.
  - K1–K4 already PASS (`out/K_summary.json`).
- **C_inline is a NEAR-MISS.** Its 100k text-encoded median is 311.89 ms, inside the 25% margin.
- **C_par FAILS.** On text-encoded rows at 100k it is slower than Python.
- **The run's verdict is its best candidate's: PASS.**
- **The number that ships:** T-52's head (`C_t52`, `dc088f7`) emits byte-identical SQL to C_both for
  this widget. It measured the same: 108.46 / 135.69 ms at 100k.
- **Host check.** Python took 829.46 ms against T-4's quiet record of 784.04 ms (+6%). T-4's own arm C
  (C_spike) took 2,122.37 ms against 2,004.61 ms (+6%). This is a quiet host.
- **Disclosure.** Per repetition, the 20k cells ran at 1-minute load 1.73–1.89 and the 100k cells at
  2.11–2.81. The 100k text-encoded cell STARTED at load 2.35. T-4's original §5.1 start ceiling
  (≤ 2.0) would have voided it, and the text encoding would then read INCOMPLETE. §10, written
  before both runs, replaced that ceiling with "recorded, never voids". The margins are 2.2–2.8×
  under the median bar and 4.0–4.9× under the p95 bar.
- **The loaded run below stands as measured.** It is what a load of 27–40 on 20 cores costs.

---

## 1. The verdict OF THE LOADED RUN (superseded by §0 for the decision)

**FAIL, as the bar reads tonight. Every candidate gives zero wrong numbers and beats Python
by seconds at 100,000 rows. None meets ≤ 300 ms on this host, which is loaded to about 35 on 20
cores.**

| at 100,000 rows · widget INVENTED · load ~30–36 | number-encoded | text-encoded |
|---|---:|---:|
| **C_both** (lever a + b), median / p95 | **456.85 / 753.35 ms** | **516.59 / 823.85 ms** |
| C_inline (lever b), median / p95 | 734.03 / 1,111.76 ms | 1,019.04 / 1,184.02 ms |
| C_par (lever a), median / p95 | 1,808.94 / 2,091.34 ms | 1,887.49 / 2,162.39 ms |
| C_ship (the shipping pair, baseline) | 4,783.58 ms | 5,180.10 ms |
| **arm A — today's Python, same session** | **4,292.07 ms** | **4,380.19 ms** |
| the bar (S1) | ≤ 300 / ≤ 600 ms | ≤ 300 / ≤ 600 ms |

- **Correctness is green for all three candidates** (K1–K5). Identity holds at every timed size
  and encoding, row for row against the uncapped Python oracle.
- **S2 (beat same-session Python) and S3 (20k within +100 ms) pass for all three.**
- **S1 fails for all three, so the verdict is FAIL**, under §4.3 and the §10 amendment: *"a miss
  measured under load is reported exactly as measured"*. The fastest, C_both, misses its median
  by 52% on number-encoded rows and 72% on text-encoded ones. Both are past the 25% near-miss
  line, so this is not a near-miss.
- **The same load slowed today's Python 5.5× and T-4's own arm C 2.3×**, against their
  quiet-host records (784.04 → 4,292.07 ms and 2,004.61 → 4,637.63 ms). That is the measured
  cost of tonight's host. No load-corrected number enters the verdict (§10.3). It is why
  "re-time on a quiet host" is the first option in the decision packet.

**A ratio may appear in this report; it does not appear in the verdict.**

---

## 2. Correctness: the bar's first half, and it is green for all three candidates

**K1–K4 pass for C_par, C_inline and C_both.** `out/K_summary.json` computes this from the
battery outputs (`summarize_k.py`); nothing in it is copied by hand.

| gate | C_par (lever a) | C_inline (lever b) | C_both (a + b) |
|---|---|---|---|
| **K1** three subset batteries, 11,367 expressions, efd 1, recursive rule | 0 wrong numbers | 0 | 0 |
| **K2** no new refusal, no changed SQLSTATE, vs the shipping pair, case by case | pass | pass | pass |
| **K3** contract fixture | 130/130 | 130/130 | 130/130 |
| **K4** K1 + K2 again under `debug_parallel_query = on` | pass | n/a (no parallel labels) | pass |

Beyond the gates, **every candidate returns the same jsonb text and the same predicate as the
shipping pair on all 11,367 battery cases.** That holds under both comparison rules, and under
forced parallel mode for the two parallel candidates (`out/K2_*.txt`).

### 2.1 The shipping pair, through the batteries for the first time

The shipping compiler and runtime (`compiler/compile.py`, `runtime/runtime.sql`) had never
been through the batteries: `differ.py` imports the frozen spike compiler. `battery.py` makes
the frozen import resolve to whichever compiler it is given, and reads back what actually
loaded. It was validated first, by reproducing T-6's variant-C result exactly: 3801 / 125 / 74
(`out/repro_T6VC_*`).

**Result: zero wrong numbers on all three profiles.** One finding:

**The shipping compiler refuses 2 more expressions than the spike compiler (11 vs 9 on
`sub_extreme`), and the cause is plan-time constant folding.** With the runtime held fixed,
the 2 cases flip from AGREE to a 22003 refusal when only the compiler changes
(`out/diag_spikecompiler_on_shiprt_*`). The battery binds each record as a constant, and
`xpr.j` is IMMUTABLE, so Postgres folds whole subtrees at plan time. That includes a constant
`1.797693134862316e+296 * 1e+16` that Python evaluates to infinity, and that sits in an
expression whose answer never depends on it. `EXPLAIN` alone raises: proof that it happens at
plan time. The spike compiler's `to_jsonb` is STABLE, which blocks the folding, so a NULL
operand short-circuits the whole multiplication. **These are refusals, not wrong numbers:**
the 22003 kind that GA-4's ruling allows. The candidates inherit exactly the same 11.

### 2.2 Lever (a): the runtime was not parallel safe, and now is, exactly

- **`xpr.num` was not parallel safe as written. This is measured.** Its `EXCEPTION` block opens
  a subtransaction, and PostgreSQL 16 refuses that in parallel mode. Under forced parallel
  mode, with the shipping bodies merely *labelled* safe, the batteries raise `25000 cannot
  start subtransactions during a parallel operation` **395 times** (173 / 76 / 146), and K2
  flags every one (`out/NC_*`). This is K4's negative control. It fired, and its positive
  control showed a worker launched.
- **The rewrite** uses PostgreSQL 16's `pg_input_is_valid(t, 'numeric')`, which is parallel
  safe, in place of the `EXCEPTION` block. It is **identical to the shipping `xpr.num` on 6,140
  inputs**: 2,239 values (bit for bit, sign of zero included), 51 NULLs, 2,686 `XPR01` refusals
  and 1,164 `22003` errors. Every overflow boundary is covered: numeric's dscale 16383/16384,
  the 1000-character and 4-digit-exponent guard, DBL_MAX, underflow, and non-ASCII digits with
  exponents (`out/num_diff.json`).
- **One volatility label was false.** `xpr.ecma_num` was IMMUTABLE while reading float8's text
  output, which follows `extra_float_digits`, a session setting. That is compile.py's own
  `KNOWN_DIVERGENCES` entry `extra_float_digits_guc`. It now pins `SET extra_float_digits = 1`,
  T-9's fix for `xpr.j`, so the label is true. Four other functions call STABLE builtins
  (`to_jsonb`, `to_char`, `extract(epoch …)`) whose results cannot vary here: the setting is
  pinned, the format patterns are fixed, and an epoch does not depend on the time zone. Those
  labels stand, with that reason recorded.
- **All 23 functions are labelled PARALLEL SAFE**, generated from the shipping file by asserted
  substitutions (`make_runtimes.py`; `diff runtime/runtime.sql spikes/T-44/runtime-par.sql`
  is the whole change).

### 2.3 Lever (b): the inline compiler

A subclass of the shipping compiler, loaded by path (`compile_inline.py`). It adds:
- a float8 channel between arithmetic operations;
- the coercion `CASE jsonb_typeof(…)` written inline, for cheap arguments: JSON numbers in
  range, booleans, and plain ASCII decimal strings, with `xpr.f8` / `xpr.num` for every other
  path;
- native `< <= > >=` between numbers;
- `compile_predicate()`.

The inline coercion is **identical to `xpr.num` on 3,216 targeted inputs, on both runtimes**.
Those cover every jsonb type, plain decimals at 297–301 characters, the DBL_MAX literal and
beyond it, and every near miss that must fall through (`out/coerce_diff_*.json`).

---

## 3. Timing

**Design** (§10): seven arms in interleaved, rotating rounds; n = 25 per cell; the 1-minute load
read before every repetition (`out/timing.json`, 06:46–07:07Z).

**Host.** A second foreman run (GUTS) held the load at 30–36 on 20 cores for the whole window.
That included a RAG refresh at ~716% CPU, test suites, and a browser. Nothing of it was stopped
(§10). Steam was running with a game open. **It was left running on purpose:** the whole Steam
process tree used 5.2% of one core, and closing the owner's game risked unsaved state for no
measurable gain. Discord was not running. JIT appeared in no captured plan.

### 3.1 Medians (ms), widget INVENTED

| cell (load) | A Python | B4 | C_spike | C_ship | C_par | C_inline | C_both |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20,000 · num (~32.5) | 859.38 | 25.52 | 914.20 | 992.17 | 465.91 | 122.16 | **112.16** |
| 20,000 · text (~35.3) | 791.44 | 36.89 | 1,016.20 | 1,046.49 | 534.25 | 156.60 | **88.79** |
| 100,000 · num (~35.6) | 4,292.07 | 100.23 | 4,637.63 | 4,783.58 | 1,808.94 | 734.03 | **456.85** |
| 100,000 · text (~30.2) | 4,380.19 | 95.83 | 5,033.49 | 5,180.10 | 1,887.49 | 1,019.04 | **516.59** |

p95 at 100,000: C_both 753.35 / 823.85; C_inline 1,111.76 / 1,184.02; C_par 2,091.34 / 2,162.39
(number / text). Parallel workers launched: C_par and C_both, 1 at 20,000 and 2 at 100,000. B4:
2 at 100,000. Every other arm: 0. Arm A's recall at 100,000 is **26.0%**, the correctness
failure this project exists to fix. It is 100% at 20,000.

### 3.2 Where C_both's 456.85 ms goes (100,000 · num), measured

| part | ms |
|---|---:|
| SQL execution, server side (one `EXPLAIN ANALYZE`, same load) | 161.74 |
| shipping the 5,311 matching rows to Python and decoding them (median sql+fetch 352.3, minus the above) | ~190 |
| Python sort and limit, median | 107.9 (T-4 measured this tail at **5.36 ms** on a quiet host) |

**Most of the miss is Python-side work slowed by the load,** not the compiled SQL. The arm-C
shape returns every matching row to Python for sorting (T-4 §4: sort and limit stay out of SQL).

### 3.3 Two robustness checks, reported, not gated

- **Against the quiet-host Python record** (T-4: 784.04 ms at 100,000; 197.94 ms at 20,000).
  A candidate's quiet time cannot exceed its loaded time. So a candidate that is faster,
  loaded, than Python was quiet beats Python on a quiet host too. **C_both does that in all
  four cells. C_inline does it in three: not in 100,000 · text (1,019 ms).** C_par does it in
  none. So S2 does not depend on the load inflating Python more than SQL. It visibly did:
  5.5× against 2.3×.
- **Paired, per round** (candidate minus arm A in the same round), median at 100,000: C_both
  −3,760 ms (num) / −3,733 ms (text); C_inline −3,510 / −3,398.

### 3.4 The shipping path, measured for the first time

**C_ship is slower than T-4's arm C in every cell** (100,000 · num: 4,783.58 against C_spike's
4,637.63 in the same session). The ADR predicted this: the shipping compiler's per-row `xpr.j`
calls cannot be inlined. **C_both is about 10× faster than the shipping path, with identical
answers.**

---

## 4. Admissibility

| requirement | status |
|---|---|
| bar fixed before any run | `FRAMING.md` at `69efb20`; §10 amendment at `48b1400`; both before the first timed repetition |
| negative control, before any millisecond | **24/24** through the real harness (`out/negative-control.json`): load 40 recorded and never voiding; a short corpus voids the cell; index help voids the arm; one perturbed row fails each candidate's K5 or voids a reported arm; a raising repetition is excluded; ten synthetic bar cases, including 375 ms = NEAR-MISS against 376 ms = FAIL |
| corpus | row counts exact; selectivity 5.385% (20k) / 5.311% (100k) on both encodings, matching T-4; the text copies are row-for-row identical apart from the encoding (`out/setup.json`) |
| runtimes installed | `xpr_ship` and `xpr_par` fingerprints match the battery databases'; T-4's `xpr` (21 functions) untouched |
| live database | never contacted: the harness does not call T-4's `host_state()`, which reads 55433 |
| PostgreSQL | 16.14 |

---

## 5. What this does NOT decide

- **Whether the faster design meets 300 ms on a quiet host.** That was not measured tonight, so
  it is the first option in the decision packet (`kb/wiki/decision-t44-faster-path.md`).
- **Real widgets.** Every number is for the invented `load_score`.
- **Data the plain-decimal fast path does not cover.** Strings with whitespace, exponents or
  non-ASCII digits take the exact but slower `xpr.num` path. The text encoding here is plain
  integers.
- **1,000,000 rows**, which was not measured (§7).
- **T-23's equality question**, deferred until a shipping change exists. The levers do not
  touch `==`.
- **The shipping change itself.** Promoting `compile_inline.py` into `compiler/compile.py` and
  the lever-(a) edits into `runtime/runtime.sql.in` (then regenerating) is separate work. It
  happens only after the owner rules.
