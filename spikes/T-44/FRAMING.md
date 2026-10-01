# T-44 · Framing — a faster compiled path, held to the same bar discipline as T-4

**Parent:** T-4, ruled **C — "test a faster design first"** (GA-34 Q1; ADR in
`kb/wiki/decision-t4-timing-verdict.md`). **Written 2026-10-01, before anything in this
spike ran:** no battery, no probe, no timing. Everything in §4 is the bar, and it was
committed before the first database connection. Git history is the proof.

> **Vocabulary.** An **arm** is one way of answering the same dashboard widget, timed side by
> side. A **lever** is one change to the compiled path. A **battery** is a fixed, seeded set of
> random expressions run through both Python and SQL and compared. **Parallel safe** is a label on
> a Postgres function that lets the planner run it in worker processes; a wrong label is a bug that
> only shows on a table big enough to get a parallel plan. **Wrong number** means SQL and Python
> disagree on a value.

---

## 1. The question

> **Can the compiled path give zero wrong numbers and still beat same-session Python, under
> ~0.3 s at 100,000 rows?**

The 0.3 s target is the one the owner read on the form when ruling C: *"If it passes (target:
under ~0.3 s at 100k rows), autoSQL is ready for the GIMS plan."* The owner's rule from 5 Sep
stands: **it must beat Python.** The unit is milliseconds, never a ratio (GA-3).

---

## 2. What this spike inherits from T-4, unchanged

Read `spikes/T-4/FRAMING.md` for the full text. These hold here exactly as written there:

- **§5 measurement hygiene.** Load ≤ 2.0 when a size starts and ≤ 4.0 when it ends (§5.1); the
  host record (§5.4); cache state measured, never claimed (§5.3). n = 25 at 20,000 and 100,000
  rows, with no column called p95 below n = 20 (§5.2).
- **§6 inadmissibility**, items 1–14. Item 6 is tightened in §4 below.
- **§6.1 the negative control:** it runs through the real harness, and it passes **before any
  millisecond is quoted**. If any injection comes back scored as admissible, the run reports
  nothing.
- **The widget is INVENTED** (§7.2): `load_score = coalesce($.queue_depth, 0) +
  coalesce($.retest_count, 0) * 25`, where `$.load_score > 195`, sorted by `load_score` desc,
  limit 50. It must be labelled invented everywhere a number for it appears.
- **The corpus:** T-4's extended corpus in the held `autosql-corpus` container
  (`127.0.0.1:55434`, database `autosql_spike`, PostgreSQL 16.14). **Never 55433.**
- **The Python comparator is arm A** (today's capped in-memory pipeline). **The identity oracle is
  `A_uncapped`**, untimed and tiebroken (T-4's `identity_check`).

**What does NOT carry over:** T-4's absolute bars (350 / 1,000 / 5,500 ms) and its 1,000,000-row
size. The owner's target for this spike is at 100,000 rows. **1M is not measured** (§6).

---

## 3. The arms — fixed now, and no arm is added after the first timed cell

| arm | what it is | role |
|---|---|---|
| **A** | GIMS's in-memory pipeline, capped (`api/dashboard/sources.py` at GIMS `995cc59`) | **the comparator the bar uses** |
| **B4** | the predicate in native operators (raises on a malformed value) | ceiling, reported, never a candidate |
| **C_spike** | T-4's arm C: the frozen spike compiler and runtime | host check against T-4's record; reported |
| **C_ship** | the **shipping** compiler and runtime (`compiler/compile.py`, `runtime/runtime.sql`) | **the baseline**; reported |
| **C_par** | C_ship's SQL on a runtime made genuinely parallel safe (lever a) | candidate |
| **C_inline** | the inline compiler (lever b) on the shipping runtime's labels | candidate |
| **C_both** | the inline compiler on the parallel-safe runtime (a + b) | candidate |

All C arms keep T-4's shippable shape: SQL computes the derive and the predicate; Python sorts and
limits. The shipping and candidate runtimes are installed side by side, each in its own schema, so
every arm is timed in the same session on the same rows.

### 3.1 Lever (a): a runtime that is genuinely parallel safe, with honest labels

None of the 23 `xpr` functions carries a parallel label, so all default to PARALLEL UNSAFE, and a
query that calls one cannot use workers. T-4's audit saw Postgres run arm C in one process while
plain SQL used two workers.

**A label is a claim, so lever (a) changes code only where the claim would otherwise be false.**
One function is known not to be safe as written: `xpr.num` opens an `EXCEPTION` block on its
string path. In PostgreSQL 16 that starts a subtransaction, and a subtransaction cannot start in
parallel mode. Lever (a) therefore:

1. rewrites `xpr.num`'s overflow handling **without** an `EXCEPTION` block, with the same results
   and the same error codes on every input;
2. labels each function PARALLEL SAFE **only after reading its body** and every builtin it calls
   in `pg_proc`;
3. corrects any volatility label that is false (for example, a function marked IMMUTABLE whose
   result depends on a session setting). Each correction is listed, with its reason, in the
   findings.

### 3.2 Lever (b): the number checks written inline

A subclass of the shipping compiler. Everything not listed here is inherited unchanged.

1. **A float8 channel.** A node whose value is always a number or null keeps its value as `float8`
   between operations. This covers number literals, unary minus, the arithmetic operators, and
   the numeric builtins. The shipping compiler converts to `jsonb` and back between every pair of
   operations. Keeping `float8` is exact only if `xpr.num(xpr.j(x)) = x` for every finite `x`.
   That is a claim, and the batteries must prove it.
2. **An inline coercion** wherever a `jsonb` value must become a number, written as `CASE
   jsonb_typeof(...)`:
   - a **JSON number** within float8 range takes the native cast; anything outside the range goes
     to the unchanged `xpr.f8`, so the named refusal `XPR01` survives;
   - a **boolean** becomes 1 or 0;
   - a **plain ASCII decimal string** (no surrounding whitespace, no exponent, under 300
     characters) takes the native cast;
   - **every other string** (whitespace, an exponent, non-ASCII digits, long values) goes to the
     unchanged `xpr.num`;
   - anything else is null.

   The inline form repeats its argument. So it is used only where the argument is a cheap
   expression (a field path, or a `coalesce` of field paths and constants). Anything heavier goes
   to the unchanged `xpr.num`, which keeps the size of the SQL bounded.
3. **Native ordering** when both sides of `< <= > >=` are in the float8 channel. `xpr.ord` on two
   numbers is exactly a float8 comparison with null propagation.
4. **The predicate as a boolean.** `xpr.truthy(to_jsonb(b))` is exactly `COALESCE(b, false)`.
   The compiler gains `compile_predicate()`, and only the inline arms use it.

**Why plain decimal strings are included, which the 2026-09-26 sketch did not do.** The sketch sent
every string to `xpr.num` as a "rare path". It is not rare. T-5 measured the owner's real data:
**all 6 number-declared fields that carry rows hold strings**
(`kb/wiki/decision-t5-homework.md`). On the owner's data, the string path is how every number is read.

---

## 4. THE BAR — fixed here, before anything runs

The starting point is the bar proposed in `.autodev/handoffs/T-4.md` (WIND-DOWN 2026-09-26).
**Five amendments are marked [A1]–[A5], each with its reason, in §5.** The verdict is reached per
candidate (C_par, C_inline, C_both). The run's verdict is the best candidate's.

### 4.1 Correctness. Any failure here is a FAIL, never a near-miss

| # | condition |
|---|---|
| **K1** | **The three subset batteries** (`sub_ordinary`, `sub_unicode`, `sub_extreme`; N = 4,000; seed 2026; `extra_float_digits = 1`), with the verdict under T-6's **recursive** rule. The strict rule's counts are published beside it. Required: DIVERGE 0, NULLNESS 0, PY_RAISE 0, unexplained SQL_RAISE 0, and UNCOMPILABLE 0. |
| **K2** | **No new refusals [A5].** Every case a candidate refuses, the shipping pair also refuses, with the **same SQLSTATE**. Changing `XPR01` to `22003` counts as a regression even when the totals match: GIMS's fallback reads that code. |
| **K3** | **The contract fixture: 130 / 130** at efd 1. |
| **K4** | **[A1] Batteries under forced parallel mode.** For C_par and C_both, K1 and K2 are repeated with `debug_parallel_query = on`, which runs each battery query inside a parallel worker. **K4 counts only if its negative control fired first:** the shipping `xpr.num`, relabelled PARALLEL SAFE with its `EXCEPTION` block intact, must raise on a string-coercion case under the same setting. If the control does not fire, the forced run proved nothing, and K4 is **void, not passed**. |
| **K5** | **[A2] Identity at every timed size and encoding.** Each candidate's tiebroken top 50 matches `A_uncapped` row for row, every field, under the frozen `rows_match` (T-4's `identity_check`). For a candidate, **a disagreement is a wrong number: FAIL.** It is not a void cell. If the disagreement turns out to be the harness's fault, that size is VOID, and it is never a pass without a clean re-run. |

### 4.2 Speed — on a quiet host, per T-4 §5, n = 25

| # | condition |
|---|---|
| **S1** | **100,000 rows: median ≤ 300 ms and p95 ≤ 600 ms.** |
| **S2** | **100,000 rows: median strictly below arm A's median from the same session.** |
| **S3** | **20,000 rows: median ≤ arm A's same-session median + 100 ms** (T-4 §4.2: no perceptible regression where Python is already right). |
| **S4** | **[A3] Both encodings of the same rows.** **(i) As built:** the widget's two fields are JSON numbers, as in T-4's corpus. **(ii) Text-encoded:** the same rows, with those two fields stored as JSON strings (`"17"`), which is how the owner's real number fields are stored. **S1–S3 must hold on both.** Arm A is measured on each encoding, in the same session. |

The timed session is set up as T-4's was: `extra_float_digits = 1` and `synchronize_seqscans = on`,
and nothing else. **The server runs at its own defaults, recorded per cell.** That covers parallel
workers and JIT. No session tunes them, because GIMS will run on a default server. Each cell records
the workers planned and launched, and the JIT time, from its plan.

### 4.3 Verdicts

| verdict | when |
|---|---|
| **PASS** | At least one candidate meets K1–K5 and S1–S4, at both sizes and on both encodings, with every contributing cell admissible. |
| **NEAR-MISS** | No candidate passes, but at least one is correctness-clean (K1–K5) and meets everything except S1, missing the median and/or the p95 by **≤ 25%** (≤ 375 ms / ≤ 750 ms). The miss may be on one encoding or both. |
| **FAIL** | Neither of the above, with the required cells measured. **Any wrong number fails that candidate.** |
| **INCOMPLETE** | A required cell is untested or void, and no candidate has otherwise passed. T-4 §4.5 applies: a FAIL stays a FAIL even if another cell went untested. |

**Who rules (GA-34 Q2 = A).** On a **clear PASS**, the foreman clears `sp_decide` on the owner's
behalf, and the shipping change is filed (GA-35). A **NEAR-MISS or FAIL** parks for the owner, with
options and the numbers in hand. **A ratio may appear in the report. It may never appear in the
verdict.**

---

## 5. The amendments to the proposed bar, and why each is needed

- **[A1] The batteries cannot see a parallel-safety bug.** Every battery query is one row in a
  `VALUES`-shaped subquery, and Postgres never plans that in parallel. A function wrongly labelled
  parallel safe passes every battery. It fails only on a table big enough to get workers, which
  means during the timing run, or in production. This is the project's own defect class: *a
  check that never ran reads exactly like a check that passed* (`kb/wiki/lessons.md`). Forcing
  parallel mode makes the batteries exercise the label. The negative control shows the forcing
  works.
- **[A2] Wrong numbers can appear at scale that the batteries never generate.** The proposed bar
  named only the batteries and the fixture. T-4 held its arms to identity as an admissibility
  check. Here identity is promoted to a correctness condition, because a candidate's whole claim
  is that it gives the same answers faster.
- **[A3] The corpus stores numbers as JSON numbers, and the owner's data does not.** T-5 measured
  that all 6 number-declared fields in the owner's real data hold strings. A pass on number-typed
  rows alone would say *"ready for the GIMS plan"* about a path that data never takes. Gating on
  both encodings is stricter than the proposal. If this costs the pass, the result parks with
  both numbers, which is what Q2 = A prescribes for anything short of a clear pass.
- **[A4] The baseline is the shipping pair, not T-4's arm C.** T-4 timed the frozen spike
  compiler. The shipping compiler routes every number through `xpr.j`, which cannot be inlined, and
  its timing was never measured (ADR, Consequences). The proposed bar compares against Python, so
  the bar itself is unchanged. But without a same-session C_ship, no speed-up can be attributed
  to a lever. Its batteries are run **first**: the shipping pair has never been through them.
- **[A5] Refusal counts can hide a changed contract.** "No more refusals than the shipping
  compiler" is met by a candidate that swaps the named refusal `XPR01` for a native `22003`. That
  breaks GIMS's fallback signal. K2 compares the SQLSTATE case by case.

---

## 6. Order of work, timebox and stop rules

1. **Batteries on the shipping pair first** (K1–K3 baseline). Record what is actually installed
   (`installed_runtime_sha`), not the file the harness names (T-10). Record the compiler module
   that actually loaded: `differ.py` names the frozen spike compiler.
2. **Lever (a).** First a direct differential: the old and new `xpr.num` run over every battery
   string plus boundary strings, compared on value or SQLSTATE. Then K1–K4.
3. **Lever (b).** Then K1–K3, and a case-level differential against the shipping compiler,
   reported.
4. **The negative control through the timing harness** (T-4's §6.1 injections, plus one for each
   new arm). **No millisecond is quoted before it passes.**
5. **Verify the corpus** (row counts; selectivity 4.5–6.0% on both encodings; PostgreSQL 16.14;
   bytes per row). Then report `ready to time` and **wait for the foreman's quiet window**.
6. **Time 20,000 and 100,000 rows**, both encodings, all seven arms. Then synthesis.

**Stop rules.** A candidate that fails K1–K4 is **not timed**, because a fast wrong answer has no
latency worth reporting. If every candidate fails correctness, the run reports FAIL without a
timing window. A change to a candidate after its first timed cell voids that candidate's cells;
re-timing it in the same window needs K1–K4 re-run first. **No tuning a candidate until it
passes:** the candidates are the designs in §3, as written here.

**Timebox:** one overnight run (2026-10-01). The timing step needs one quiet window of about
30 minutes. Anything left over is reported as untested, never estimated.

---

## 7. Out of scope

- **Equality semantics** (T-23's deferred question). The levers do not touch `==` / `!=`.
- **Sort and limit in SQL** (T-4's B2). The shippable shape keeps them in Python.
- **The `days_left` date control.** Lever (b) does not change the date path. The host check is
  arm A against T-4's record (784.04 ms at 100,000 rows, 197.94 ms at 20,000), plus C_spike
  against 2,004.61 ms.
- **1,000,000 rows.** Not required by this bar. It is not cheap: C_ship would take minutes per
  repetition set.
- **Indexes** (Q11: off, permanently). Every compiled plan must still be a bare scan (T-4 §6
  item 4).
- **Anything in GIMS.** Both checkouts are read-only. Run with `PYTHONDONTWRITEBYTECODE=1`.
- **Building the shipping change.** That is a separate ticket, filed only on a clear PASS.

---

## 8. Environment

- **Interpreter:** a scratch venv from `/usr/bin/python3.12` with `psycopg2-binary`, `boto3` and
  `fastapi`, never `GIMS-Project/.venv` (its pip runs the live spine's Python). Arm A imports GIMS's
  committed code read-only.
- **Database:** `autosql-corpus` on `127.0.0.1:55434` (held; restart policy `no`). Batteries run
  in their own database in that container, so the corpus database is never written by a
  battery. The runtimes go into `autosql_spike` side by side, each in its own schema. The schema
  `xpr` is left exactly as T-4 left it. What it holds is read from `pg_proc`, not assumed.
- **Never** port 55433 (`glp-strong-db`, the live database) or 8100 (the live GIMS). Both
  harnesses already refuse 55433.

---

## 9. Rulings made in this framing, and how to overturn them

| ruling | reversal |
|---|---|
| R1. Gate on both encodings [A3] | One line from the owner or the foreman: gate on (i) only, and report (ii). |
| R2. Plain decimal strings are inlined (§3.2) | Drop that branch. Lever (b) then measures the 2026-09-26 sketch as written. |
| R3. 1M is not measured | Add it: about 15 minutes of exclusive host per encoding. |
| R4. Identity is a correctness condition [A2] | Demote it to admissibility (void, as in T-4). |
| R5. No days_left control | Add it back as reported-only: about 5 minutes. |

**The risky part, for the next seat:** lever (a) rewrites `xpr.num`. That is the one place in this
spike where a parallel label is a claim about code, not about a body read off the page. If the
rewrite is not exactly equivalent, every arm on that runtime is wrong *in the same way*, and the
batteries alone may not show it. The differential in §6 step 2 is what catches that. Run it
before anything else on lever (a).

---

## 10. AMENDMENT, 2026-10-01, written before the first timed repetition: the host is loaded

**What changed.** After §1–§9 were committed, the foreman reported a second, separate foreman
run on this machine (GUTS, 7+ Claude seats, started ~23:50 MDT). Its test suites hold the
1-minute load near **40 on 20 cores**, and one of its seats drives a browser. Q3's machine
takeover was granted before that run existed. Stopping it would break another foreman's work,
so **nothing belonging to it is stopped.** Steam and Discord may be stopped if running, and
nothing else. T-4 §5.1's quiet host cannot exist tonight.

**The owner's standing words**, said of T-4's own disturbed timing window (2026-09-08,
`.autodev/handoffs/2026-09-08-run.md`): *"I couldn't give 2 shits about the dirtiness of it"*,
and, asked what that meant for the ruling, *"Just use this info as if it were pristine so you
can keep going as if that info were completely accurate."*

**So, for this run only, and replacing T-4 §5.1 and §6 item 1 wherever they disagree:**

1. **Interleaved rounds.** Each (size × encoding) cell runs all seven arms once per round.
   Each round starts one arm later than the round before, so the same-session Python arm sees
   the same load as every candidate. n = 25 rounds per cell, at 20,000 and 100,000 rows, on
   both encodings.
2. **Load is recorded and never voids.** The 1-minute load average is read immediately before
   **every repetition** and stored beside it. Each cell also stores a host snapshot at start
   and end (load, top processes, memory, containers). Every other admissibility rule stands:
   corpus row count, index help, identity, the invented-widget label, and the negative control
   first.
3. **S1 is read literally on the measured times, treated as pristine.** That is ≤ 300 ms
   median and ≤ 600 ms p95 at 100,000 rows. Load can only slow a candidate down, and the
   parallel arms most of all, since each needs three cores at once. **So a pass measured under
   load is a pass.** A miss measured under load is reported exactly as measured, with its load
   beside it, and goes to the owner as NEAR-MISS or FAIL. There, "re-time on a quiet host" is
   offered as one option, for the morning only. **No load-corrected number appears in the
   verdict.**
4. **S2 and S3 read on the interleaved same-session medians**, with the paired per-round
   differences (candidate minus arm A) reported beside them.
5. **Host check, reported and not gated.** Arm A's same-session median is compared with T-4's
   quiet-host record (784.04 ms at 100,000; 197.94 ms at 20,000). The ratio is the load's
   measured cost to Python, and it appears in the report, never in the verdict.
6. **Nothing connects to 55433.** T-4's §5.4 item 16 read two counters from the live database.
   This run drops them, because tonight's charter forbids any connection there.

The foreman accepted this amendment before it was written down. It is committed before the
first timed repetition.
