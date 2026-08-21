# T-1 — specifications for the two follow-up runs

**Written 2026-08-21.** Evan funded two runs and put the correctness one first (Q6, re-confirmed as
item 6 of the second form). This document is the specification for both: what each one asks, the
exact number it has to beat, what it measures, what it has to build first, what would make its
answer worthless, and what it costs to run.

It is a plan, not a result. Nothing in here has been run.

Every figure quoted from the investigation is cited to the section it came from and was re-read from
the file before being written here. Figures marked **[measured 2026-08-21]** are new — taken on this
machine, read-only, while writing this spec.

**Two things in here you should read before the rest.**

**(1) Three decisions in here are mine, not yours.** You delegated them (GA-4: *"I feel like these
questions can be answered with your best judgement"*), so they are recorded as **rulings on delegated
authority** and each one shows the answers of yours it was derived from. They are: **§1.2** — an
above-DBL_MAX divergence becomes a *reported runtime refusal* rather than a carve-out; **§2.2** —
Run 2's latency bar is **three numbers, one per collection size** (350 ms / 1,000 ms / 5,500 ms), not
one; and **§2.2's kill condition** — the compiled path must beat the in-memory path at the same row
count. Each is overturnable by you in one line, and **nothing about what either run measures changes
if you move a line.**

**(2) Writing this spec turned up a defect that changes what Run 1 is for.** The restricted feature
set does not pass the correctness bar today — that is already measured, in a file nobody cross-read
against the subset — and the cause is a single mistyped literal in the prototype's SQL runtime that is
**12 digits too short**. Consequence: every stored number of magnitude 1.8e296 or above silently
becomes null instead of being compared. Details, evidence and reachability in §1.2. Nothing in your
real data is anywhere near it, and fixing it is twelve characters.

---

## The correction this document is built around

Evan's words, verbatim, from his re-confirmation of the ruling (GA-3, recorded in
`ANSWERS-FROM-EVAN.md` under Q1):

> "Benchmark absolute user-facing latency rather than treating a 3.79×–7.15× relative slowdown as
> intrinsically fatal."

He is right, and his own measured numbers make the point better than any argument. Both ends of that
3.79×–7.15× range, from `FINDINGS.md` §4.4:

| collection size | Python | compiled | the ratio | **the extra wait** |
|---:|---:|---:|---:|---:|
| 1,000 rows | 13.84 ms | 57.47 ms | 4.15× | **44 ms** — nobody can feel this |
| 1,000,000 rows | 8,331 ms | 59,590 ms | 7.15× | **51 seconds** — everybody can feel this |

**The ratio moves by less than a factor of two across those two rows. The wait moves by a factor of
about twelve hundred.** A bar written in ratios says roughly the same thing at both ends, which means
it says almost nothing about whether a person would mind.

**What that changes, concretely:**

| | old bar | new bar |
|---|---|---|
| the unit | a multiple of today's time (3.79×–7.15×) | milliseconds a person waits |
| the reference point | today's Python path, whatever it happens to cost | a fixed wall-clock number per collection size |
| the second bar in the record | ≤ 5.5 microseconds per row at 1M (`panel.json[2]`'s C-0, restated in `FINDINGS.md` §5.7 condition 4) | still per-row underneath, but stated as the millisecond total it produces, because that is what a person experiences |
| what a pass means | "not much slower than before" | "fast enough that someone using the dashboard is not annoyed" |

**One thing the correction does not ban.** It bans ratios as the *bar*. It does not ban measuring
them. Ratios say useful things about mechanism — where the time went, whether a change helped — and
Run 2 still reports them. They just stop deciding anything.

---

## What both runs are already told, before either is designed

Five decisions on the record constrain these runs. None of them is negotiable inside the run.

| decision | what it says | what it does to the runs |
|---|---|---|
| **Q11** — "Not acceptable — index work stays off" | the compiler may not write tenant-supplied field names into SQL text, so the generated query can never be helped by a database index | **Neither run may assume index help.** Run 2's compiled query is a full scan of the collection every single time. This is why the 3.79×–7.15× gap is now described on the record as *a floor, not a starting point* — the one lever that could have closed it is gone. |
| **Q10** — "Make the correctness run test all three settings" | the Postgres float-digit setting must be tested at all three values | Run 1 runs everything three times and **reports the three separately**. A pooled pass rate is forbidden: it would hide which setting broke. |
| **Q7** — "Let them edit the existing code in place" | the throwaway prototype and test generators may be modified | Both runs edit `spikes/T-1/proto/` and `spikes/T-1/analysis/fuzz/` directly. No rebuild from scratch. Both GIMS checkouts stay read-only. |
| **Q31** — "Leave it gone" | the 1,000-to-1,000,000-row test tables were dropped and stay dropped | **Run 2 must rebuild the corpus from nothing.** Confirmed still gone **[measured 2026-08-21]**: `autosql_spike` holds zero `measure_instances_*` tables. The 21 `xpr` runtime functions and PostgreSQL 16.14 are still there, so Run 1 needs no rebuild at all. |
| **item 7 of the second form** — "TAKE THE DEFAULT" | no real widget was named (Q8 superseded) | Run 2 uses an **invented** widget, labelled as invented everywhere it appears. If Evan names a real one before the run starts, it replaces the invented one and nothing else in this spec changes. |

---

# RUN 1 — the correctness run

*The investigation calls this **E1**, defined in `FINDINGS.md` §5.7 and §5.11. Same thing.*

## 1.1 The question

Take the restricted set of language features the investigation identified as the only candidate for
a SQL version — 32 of the language's 48 constructs, covering 68 of the 130 contract test cases
(`FINDINGS.md` §5.7). The functions in it are exactly seven: `abs coalesce count if length max min`.
Everything to do with dates, strings, `sum`, `avg`, `round`, `floor`, `ceil` and `%` is outside it.

**Does that restricted set produce the same answer in Postgres as it does in Python — on every input
the run can generate, at every Postgres float-digit setting?**

That is the whole question. It is not "does it pass the 130 cases" — it already does, and the
investigation ruled that the 130 cases cannot serve as the acceptance test (`FINDINGS.md` §5.2, and
Evan's own Q2, "Not good enough — build a real one"). Run 1 *is* the real one.

### Why the float-digit setting is in the question at all

Postgres has a session setting called `extra_float_digits`. It controls how many digits Postgres
prints when it turns a floating-point number into text. The default on modern Postgres is `1`, which
means "print enough digits that reading it back gives you exactly the same number". Lower values
print fewer digits and silently round.

The investigation found this is not a cosmetic setting for autoSQL. It is on the **value** channel,
not just the display channel — `to_jsonb(float8)` itself changes what it returns
(`analysis/fuzz/M_encoding_guc.txt` §M1, re-read):

```
efd = 1    1/3 -> 0.3333333333333333
efd = 0    1/3 -> 0.333333333333333
efd = -3   1/3 -> 0.333333333333
```

So the number the dashboard receives depends on a session setting. **68 of the 130 contract cases
carry a value through a float-to-text or float-to-JSON conversion** — 54 that return a number
outright and 14 more whose compiled SQL contains `xpr.str` (`FINDINGS.md` §1.2). Every one of those
68 would have to be rechecked at any other setting, and none ever has been: `proto/conformance.py:341`
hard-codes `SET extra_float_digits = 1` and every run in the record inherited it.

Worse, four of the runtime's SQL functions (`ecma_num`, `f8`, `num`, `str`) are declared `IMMUTABLE`
— a promise to Postgres that they always return the same answer for the same input — while actually
reading this setting (`analysis/fuzz/L_misc.txt` §L5). Postgres believes the promise without
checking it. That is not merely untidy; `analysis/index-shape.md` §6.4 demonstrates the same query,
in the same session, returning two different answers depending only on whether the planner chose to
use an index. Q11 has since taken indexes off the table, which removes that particular route, but
the underlying mis-declaration is still there and Run 1 is where it gets priced.

## 1.2 The pass/fail bar

The run produces, **for each of the three settings separately**, a count in each outcome class. The
classes already exist in `analysis/fuzz/differ.py:74-78` and are not being redefined.

**PASS requires all four of these, at each of `extra_float_digits` = 1, 0 and −3:**

| # | class | count required |
|---|---|---|
| 1 | **different value** — both sides returned a value, and the mirrored comparison rule says they differ | **0** |
| 2 | **value → NULL** — Python returned a value, Postgres returned null | **0** |
| 3 | **NULL → value** — Python returned null, Postgres returned a value | **0** |
| 4 | **Python raised, Postgres returned a value** (bucketed `PY_RAISE` today) | **0** |

Class 4 is the one the existing runs cannot see. `differ.py` buckets `PY_RAISE` away from `DIVERGE`,
so a run can report zero divergences while Postgres is quietly answering questions Python refuses to
answer at all. That is the exact direction `FINDINGS.md` §5 is worried about and it has to be counted
separately.

**Three of these are FAIL. There is no partial credit and no "acceptable rate".** A wrong number on a
dashboard has no acceptable rate.

**A fifth outcome exists and is deliberately not one of the four: Postgres refuses.** Where the SQL
raises an error instead of answering, the case is counted, reported and kept in the denominator — but
it is not a wrong answer, so it does not fail the bar. That is a **ruling on delegated authority**
made 2026-08-21; its derivation, its conditions, and what happens if it cannot be implemented are two
subsections below. It is load-bearing: without it the corrected subset cannot pass, and with it the
zero stays a real zero rather than a zero with an exception written under it.

### The state to beat, so a zero means something

These are the current measured divergence counts from the three broad fuzz batteries, over
*unrestricted* expressions (`FINDINGS.md` §5.7, re-derived there from `analysis/fuzz/H_*.txt`).
Denominators are **expressions that actually ran** — agree plus diverge plus SQL-raise — not the
agree count, and not the 4,000 drawn:

| battery | diverging | ran |
|---|---:|---:|
| `H_ordinary` (values that look like dashboard data) | **0** | 3,881 |
| `H_unicode` (non-ASCII strings) | **4** | 3,867 |
| `H_extreme` (pathological magnitudes) | **23** | 3,880 |

Under the restriction to the 32-construct subset, all three should go to zero — every construct
blamed for those 27 divergences is outside it. If they do not, the subset does not exist and Run 1
has killed the project, cheaply, which is the outcome it is designed to be able to produce.

### Except that the subset already fails, and the failure is already measured

This is the most important thing in Run 1's spec, and it is not in `FINDINGS.md` §5.7's version of the
experiment.

`analysis/fuzz/A_f8_guard.txt` §A2 tested twenty expression paths against a record holding
`a = 1e300` — an **ordinary finite double**, not an infinity, well inside what a float8 column can
hold. Sixteen of the twenty diverge. **Eight of those sixteen are entirely inside the restricted
subset** — that count is `FINDINGS.md` §5.5's own, and the eight are enumerated here for the first
time, re-read from the file:

| expression | Python returns | Postgres returns | why it matters |
|---|---|---|---|
| `$.a + 0` | `1e+300` | **null** | plain addition |
| `$.a * 1` | `1e+300` | **null** | plain multiplication |
| `- $.a` | `-1e+300` | **null** | unary minus |
| `abs($.a)` | `1e+300` | **null** | `abs` is one of the seven permitted functions |
| `$.a < 1e301` | `True` | **null** | **this is the pushdown-predicate path** — in a `where` clause a null means the row silently vanishes |
| `$.a > 1` | `True` | **null** | same |
| `$.a >= $.a` | `True` | **null** | same, both operands |
| `max($.l)` | `1e+300` | **`1`** | **a wrong number, not a null.** `max` is permitted. `FINDINGS.md` §5.5 names this one witness; the other seven appear nowhere outside the raw battery file. |

Seven of the eight are "value → NULL" — class 2 of the bar. The eighth is "different value" — class 1.
**The corrected subset, as it stands today, fails Run 1's bar at the very first setting.**

**The cause is one literal, and it is a typo.** `proto/runtime.sql` guards the JSON-to-float8
conversion by refusing anything above the largest double Postgres can represent. The guard literal
is written out in full as an integer, and **it is 297 digits long when it should be 309**
— re-counted mechanically from the file **[measured 2026-08-21]**, and matching
`A_f8_guard.txt` §A1's own count:

| | |
|---|---:|
| digits in the guard literal in `runtime.sql` | **297** |
| the value that produces | 1.797693134862316e+296 |
| digits the real limit needs | **309** |
| the real limit | 1.7976931348623157e+308 |
| **shortfall** | **12 digits** |

So every finite number of magnitude 1.8e296 or larger is treated as out of range and converted to
null — about **12 of the float8 exponent's 632 decades**, bisected in `A_f8_guard.txt` §A3 to a
boundary of `1.79769313486231587e+296`.

**Is it reachable in Evan's real data? Measured: no, with a very wide margin.** The read-only sweep in
`FINDINGS.md` §D.3 examined **5,235,942 numeric values** across every GIMS database on this machine
and found **0** at or above the guard, and 0 above even a tripwire set a decade early. The largest
number any GIMS writer here has ever stored is **1,787,169,706,037** — an epoch timestamp in
milliseconds — which is **284 decimal orders of magnitude** below the guard.

**What this does to Run 1's design.** Three things:

1. **Step zero is fixing the literal** (12 digits), which Q7 explicitly permits, and re-running the twenty
   `A_f8_guard.txt` §A2 paths as a before-and-after. If the eight in-subset divergences do not go to zero,
   the cause is not the literal and Run 1 has found something larger.
2. **The bar stays at zero.** A defect that is unreachable in one corpus on one machine is not a defect
   that is safe — §D.8 says so about its own sweep in as many words, and Q15 says autoSQL is aimed at
   high-volume data GIMS does not hold yet, i.e. at data nobody has sampled.
3. **It tells you what Run 1 is really for.** Not "does the subset pass" — today, measurably, it does not.
   It is: *after the one known defect is fixed, what else is in there, and does the picture change at the
   other two float-digit settings.* That is a question nobody can answer by argument.

### And one divergence the fix does not close — RULED: it becomes a reported runtime refusal

Fixing the literal moves the guard from 1.8e296 to its correct place at 1.8e308. It does not remove
the guard, and it cannot, because above that point the two engines genuinely cannot agree. Checked
live on this database **[measured 2026-08-21]**:

| | |
|---|---|
| `('1e400'::jsonb #>> '{}')::float8` | **raises**, "value out of range" — so without a guard the compiled query aborts mid-scan |
| `jsonb_typeof('1e400'::jsonb)` | `number` — so a JSON document *can* legally hold such a value, and jsonb will store it |
| `to_jsonb('Infinity'::float8)` | returns the jsonb **string** `"Infinity"`, not a number (`jsonb_typeof` → `string`) |

Python's evaluator returns the float `inf` here. Postgres has no JSON *number* that means infinity.
`runtime.sql` therefore chooses to return null instead, and says so in its own comment at the top of
the function. That is a defensible choice and it is also, by construction, a "value → NULL"
divergence inside the subset that no amount of fixing removes. It is not decidable when the SQL is
generated, either, because whether it happens depends on the row.

Three options were put up: exclude any expression that could produce a magnitude above DBL_MAX;
accept a written, named carve-out in the pass bar; or refuse the subset.

---

#### THE RULING — a ruling on delegated authority, 2026-08-21

**None of the three.** The divergence becomes a **reported runtime refusal**. The generated SQL
detects the out-of-range condition *while it is running* and refuses loudly — it raises a named,
catchable error instead of returning a number or a null — and the caller reports that as a fallback
to the Python path. **The pass bar stays at zero wrong answers, because a reported refusal is not a
wrong answer.**

**Whose decision this is.** Evan's, delegated to me. Logged as **GA-4** in `.autodev/events.jsonl`,
2026-08-21T19:43:01Z, verbatim:

> "I feel like these questions can be answered with your best judgement. I give them to you to fulfill
> what I had said in the form. I approve the spec for T-2"

Labelled a **ruling on delegated authority**, not his personal decision, everywhere it is recorded.
GA-4 is logged against ticket T-2 while its wording covers the open questions generally; this ruling
treats it as covering this one. He overturns it in one line — *"take the carve-out"* or *"exclude
those expressions"* — and only the reporting changes, nothing needs re-running.

#### The derivation

| source | what it says | what it forces |
|---|---|---|
| `FRAMING.md` §5 — the bar set *before* any evidence was collected | "A fallback to in-memory evaluation must be **reported, never silent**", and NO-GO "if any case diverges *silently* — i.e. produces a number rather than an error or an explicit fallback" | a null returned where Python has a value is precisely the silent form the spike exists to refuse. An **error** is the form the same sentence names as acceptable. The spike's own non-negotiable therefore picks the option |
| Evan's note (Q1, re-confirmed as GA-3) | "Build the bounded SQL path with **explicit fallback, instrument which path ran**" | a refusal that is caught and named *is* that instrument. A null is not — nothing downstream can tell it from a legitimately absent value |
| Evan's Q11 — "Not acceptable — index work stays off" | the generated query can never use an index | there is no performance argument for guessing instead of refusing. The corner being cut by substituting a null buys nothing that is still available to buy |

The three offered options each fail one of those. *Excluding the expressions* cannot be done — the
spec says so two paragraphs up, it depends on the row, not on the SQL. *A carve-out* writes the silent
null into the bar, which is the thing `FRAMING.md` §5 forbids by name. *Refusing the subset* throws
away a subset over a case that is 284 orders of magnitude from anything in Evan's data, without first
asking whether the engine could simply say so.

#### Why this is implementable — measured, not asserted

**Most of the behaviour already exists.** Postgres float8 arithmetic already refuses rather than
guessing. Straight from `analysis/fuzz/B_overflow.txt` and `B2_overflow.txt`:

| expression | Python returns | Postgres does |
|---|---|---|
| `$.a * $.b` (1e150 × 1e160) | `inf` | **raises `22003`** — "value out of range: overflow" |
| `$.qty * $.price` — labelled there "the shape a real dashboard writes" | `inf` | **raises `22003`** overflow |
| `$.a / $.b` | `inf` | **raises `22003`** overflow |
| `sum($.l) * sum($.l)` | `inf` | **raises `22003`** overflow |
| `$.a * $.a` (1e-200 squared) | `0.0` | **raises `22003`** — "value out of range: **underflow**" |
| `round($.a, 20)` at `a = 1.7e296` | raises `OverflowError` | **raises `22003`** overflow — both refuse |

`B_overflow.txt`'s own count: **9 of 13 probes made Postgres raise.** So the refusal is not a
mechanism anyone has to invent. It is what the database already does everywhere *except* the one
place the prototype chose to substitute a null.

**The one place is two lines.** `proto/runtime.sql` answers `THEN NULL::float8` on the out-of-range
branch of `xpr.f8` and again inside `xpr.num`. Step zero already edits both to fix the 12-digit
literal (Q7 permits it). The ruling adds: after the fix, that branch **raises**, with its own error
identity so it can be told apart from a genuine SQL bug.

**And it fits the file's own idiom.** `runtime.sql` already declares seven functions
`LANGUAGE plpgsql IMMUTABLE` (lines 80, 196, 221, 248, 267, 319, 359), and plpgsql can `RAISE`. The two
guard functions are `LANGUAGE sql`; converting them costs nothing this file does not already do.

**One consequence, stated so nobody is surprised: a raise aborts the whole query.** The refusal is
therefore per-widget, not per-row — one pathological row makes the entire widget fall back to Python.
That is the conservative behaviour and it is exactly what "explicit fallback" means, but the partial
scan is wasted work. That is a cost for Run 2 to be aware of, not a correctness problem.

#### What Run 1 must now report

1. **Refusals get their own line**, per battery and per float-digit setting, never pooled into the
   agree count. A subset that passes at zero wrong answers while refusing a large share of its inputs
   has passed the correctness bar and failed as a product, and only the count makes that visible.
   No threshold is set here: there is no measurement to set one from. Run 1 produces the rate; Evan
   draws a line across it afterwards if he wants one.
2. **Underflow is counted separately from overflow.** The witnesses above show Postgres refusing on
   underflow too, where Python returns `0.0`. Underflow is reachable at far less extreme magnitudes
   than overflow — it needs a product or quotient that falls below the smallest double, not a value
   near DBL_MAX — so its refusal rate is the one more likely to matter in real data. **Nobody has
   measured it.** The §D.3 sweep that found 0 values near the overflow guard across 5 235 942 numeric
   values looked at *stored magnitudes*; it says nothing about what an expression produces from them.
   The measurement needed: the same read-only sweep, re-run for the smallest non-zero magnitudes.
3. **The refusal must be distinguishable.** A raise the caller cannot tell apart from a broken query
   is not a report. Run 1 records the SQLSTATE and message of every refusal — the existing ones are
   `22003` — and asserts they are distinct from parse errors, type errors and missing-function errors.
4. **A refusal is not an agreement.** Where Python returns a value and SQL refuses, that stays in the
   run's output as a refusal, in the denominator, forever. It is being ruled *not a failure*; it is not
   being ruled *a pass*.

#### If the detection cannot be built

**Then it is a carve-out and Run 1 FAILS its bar. There is no escape hatch.** If `xpr.f8` and
`xpr.num` cannot be made to raise distinguishably, or if the raise cannot be caught and reported by
the caller, then the divergence reverts to a named carve-out — and a carve-out is a written admission
that the subset returns a null where Python returns a value. That is class 2 of the bar, and class 2
is zero-tolerance. **Run 1 must record that as a FAIL and say so plainly.** No partial credit, and no
"unreachable in practice" defence: §D.8 disclaims its own sweep in as many words, and Q15 points
autoSQL at high-volume data nobody has sampled.

### What may not be claimed from a pass

Stated here because the record has been burned by it once. A pass means: *on the inputs this run
generated, at these three settings, the restricted set agreed.* It does **not** mean:

- a percentage of production traffic is safe. There is no corpus of real tenant widget definitions
  in either GIMS tree (`FINDINGS.md` §2.9), so no fraction of traffic may be quoted at the gate.
- the 130-case fixture is now the acceptance test. It is not, and `FINDINGS.md` §5.10 predicts the
  temptation exactly: *"the next seat will be tempted to reuse it, and it will pass."*

## 1.3 What gets measured, and over what

| input set | size | what it is | change needed |
|---|---:|---|---|
| the contract fixture | 130 cases | `GIMS-Project/tests/fixtures/expr_vectors.json`, run through `proto/conformance.py` | one line: parameterise `:341` |
| the operand-kind probes | 403 | `proto/coverage_probe.py` — every comparison over every pair of JSON value kinds | restrict to subset; widen values |
| the fuzz batteries in `run_all.sh` | 21 batteries | `analysis/fuzz/` — A through O, including 3 × 4,000 random-expression draws | restrict generator to subset; widen the value domain |
| **three batteries the script does not regenerate** | 3 | `A_range`, `A2_boundary`, `B2_overflow` — output files exist, producer scripts do not | **write the three producers** |

All of that runs **three times**, once per setting.

*No total evaluation count is given here, because it would be invented. The volumes vary enormously
by battery — 130 fixture cases and 403 probes, against 3 × 4,000 random-expression draws in battery H,
200,000 doubles in `F1b_ecma_rate`, 40,000 pairs in `G_fmod_round` — and the record never timed any of
them. Run 1 should record its own wall clock per battery so the next run can be planned from a
number instead of a guess.*

### The value domain has to be widened, and this is the single most important part of the spec

The investigation's most instructive failure is worth restating, because Run 1 will repeat it if the
spec does not forbid it. `FINDINGS.md` §2.4 originally reported **403 probes, 403 agreements** and
drew confidence from it. Cross-cutting section A.3 then showed that the 403-probe generator could
not reach a single one of the eight ways the Python evaluator raises on data — not by luck, by
construction:

| the raise site needs | what the 403 probes actually contained |
|---|---|
| a number whose magnitude reaches ~1.8e308 | the largest number anywhere in all 403 records was **9** |
| `round()` called with a huge or tiny second argument | the only `round` second arguments were **−1** and **2** |
| `floor`/`ceil` given infinity | `floor()` and `ceil()` appear **zero-argument only** |
| the `%` operator with an infinite dividend | the token `%` occurs in **0 of 403** sources |
| a date within four days of year 1 or year 9999, carrying a UTC offset | the only dates present were `2026-01-01` and `2026-01-02` |
| containers nested 498 deep | maximum nesting depth **4** |

Zero failures over a domain that cannot fail is not evidence. It is a measurement of the generator.

**So Run 1 carries a gate on its own inputs, which must pass before any conformance number it
produces is allowed to be quoted.** The gate has two halves, because the subset changes what is
reachable.

**Half one — the eight raise sites are excluded by construction, and that has to be shown, not
assumed.** Reading `FINDINGS.md` §A.2 against the corrected subset: R1 needs a date function, R2–R5
need `round`, R6 needs `floor`/`ceil`, R7 needs `%`, and R8 needs `==` over containers — and every
one of those is outside the subset. So the "Python raised, Postgres returned a value" class should be
**structurally empty**, and Run 1's job is to demonstrate that rather than report a zero that means
nothing. Two specific checks: the run confirms mechanically that no generated expression contains any
of those constructs, **and** it deliberately composes infinity from permitted operations
(`1e200 * 1e200` is legal arithmetic inside the subset) and confirms that nothing downstream of it
raises. If anything does, that is a ninth raise mechanism nobody has catalogued, and it is a finding.

**Half two — the magnitudes must be reached, because that is where the measured in-subset failure
lives.** §1.2 shows eight in-subset divergences at `a = 1e300`, seven of which silently turn a value
into a null. The generator's value domain must therefore reach, and print witnesses for, at least:

| what the domain must reach | why |
|---|---|
| the float8 guard boundary, `1.79769313486231587e+296` and either side of it | the measured in-subset failure (§1.2), before and after the literal is fixed |
| the real limit, `1.7976931348623157e+308`, and either side | where the guard is *supposed* to sit |
| infinity composed by arithmetic (`1e200 * 1e200`) | half one |
| subnormals — `5e-324`, `1e-320` | `xpr.num` has an unguarded underflow that raises; `xpr.truthy` returns true for `1e-400` where Python gives `0.0` and therefore false |
| the 2⁵³ integer-precision boundary — `2**53` and `2**53 + 2` | where JSON numbers stop being exactly representable |
| `0.0` and `-0.0` | sign-of-zero handling differs between engines more often than anyone expects |
| numeric strings that coerce — `" 7 "`, `"1e3"`, `"１２３"` | the tolerant coercion class is the one §D.6 measured as *actually reached, repeatedly*, in real GIMS data |

If the generator cannot reach one of these, the run says so explicitly and reports that row as
untested rather than passed. **A zero over a domain that cannot fail is a measurement of the
generator, not of the compiler.**

## 1.4 Instruments — what exists, what has to be built

**Exists and is reused unchanged:**
- `analysis/fuzz/differ.py` — runs one expression both ways and classifies the result.
- `proto/conformance.py` — the 130-case harness, its 23 negative controls, and its input-hash recording.
- `proto/closure_subset_coverage.py` — walks an expression tree and reports which constructs it uses. Run 1 uses it as the subset checker.
- The `xpr` schema in Postgres — **confirmed present, 21 functions, PostgreSQL 16.14 [measured 2026-08-21]**.

**Has to be built or edited (all permitted by Q7):**

| # | work | size |
|---|---|---|
| **0** | **Fix the 297-digit guard literal in `proto/runtime.sql` to its correct 309 digits** (§1.2), and re-run the twenty `A_f8_guard.txt` §A2 paths before and after so the effect is on the record | **12 characters, and the highest-value change in either run** |
| 1 | Parameterise `proto/conformance.py:341` so the float-digit setting is an argument, and record the value used in the output JSON | one line plus plumbing |
| 2 | Add a construct allowlist to `analysis/fuzz/H_ast_fuzz.py` so it only generates subset-legal expressions | small |
| 3 | Widen that generator's value domain — magnitudes to the float8 boundary, offset-bearing dates at the calendar edges, deep nesting | moderate |
| 4 | Add the "Python raised, Postgres returned a value" check as its own reported class | small |
| 5 | Write producer scripts for `A_range`, `A2_boundary` and `B2_overflow` | three small scripts |
| 6 | **Injection controls for `differ.py`** — see below | moderate |

### Why item 6 is not optional

Evan asked (Q4) for proof that the test rig can actually report a failure, and got it: the
re-check drove `proto/conformance.py` with deliberately wrong compilations and it correctly emitted
"diverges", "did not compile" and "SQL error" through the real loop
(`RECHECK-2026-08-21.md` §2.1–§2.5). That is what makes Run 1 believable at all.

But that proof covers `conformance.py` only. `RECHECK-2026-08-21.md` §5.1 flags this plainly, and
calls it the important one: **the instrument that was not tested is `differ.py`, and it is the one
that produced every decision-relevant divergence in the entire investigation.** Run 1's headline is
a count of zeros coming out of `differ.py`. A zero from an instrument that has never been shown
capable of printing anything else is not a result.

So: before Run 1's numbers count, `differ.py` gets the same treatment `conformance.py` got — a
handful of deliberately broken compilations pushed through the real path, each of which must land in
the correct class, with the run refusing to report if any injection is scored as agreement.

## 1.5 What would make the result inadmissible

Any one of these voids the run:

1. **Any battery run at only one float-digit setting**, or the three pooled into a single number. Q10 requires three, reported separately.
2. **The input-domain gate of §1.3 not passed, or not printed** — either half: the demonstration that the eight raise sites are unreachable, or the witnesses for every magnitude class the domain must reach. This is the §A.3 mistake and it is the easiest one in this project to make twice.
3. **`differ.py` not shown able to report a failure** (§1.4 item 6).
4. **The generator emitting an out-of-subset construct.** Verify mechanically with the subset checker on every generated expression, not by inspection. If out-of-subset expressions get in, the run has answered a question nobody asked.
5. **Input fingerprints not recorded.** The existing harness records hashes for the fixture, `expr.py`, `compile.py` and `runtime.sql`. Keep that, add the float-digit value, or the run cannot be re-derived later.
6. **Results quoted as a fraction of production traffic**, or the 130-case fixture presented as the acceptance test (§1.2).
7. **The guard-literal fix applied without a before-and-after.** The fix changes what `xpr.f8` returns, and therefore moves conformance results for the 130 cases as well as the fuzz batteries. Both states have to be recorded, or nobody can tell which zeros the fix bought.
8. **The above-DBL_MAX divergence quietly folded into a pass or a fail** instead of reported as its own line for Evan to rule on (§1.2).
9. **Anything written into either GIMS checkout.** Both are read-only. Import the parser with bytecode writing disabled so no `__pycache__` lands in Evan's tree — the investigation's own passes did this and it is the reason those trees are still clean.

## 1.6 What it costs

**Machine time: small, and — importantly — it does not need a quiet machine.** A divergence is a
divergence whether the host is busy or idle; correctness results are not load-sensitive. Run 1 can
run alongside anything else on this box, which is worth something given §2.6. Its dominant cost is
one Postgres round trip per generated expression, against a database that is already up and a schema
that is already installed. No large tables are created; two batteries make and drop small scratch
tables of their own. Disk cost is negligible.

*No total runtime or evaluation count is quoted, because the record never timed these batteries and a
made-up number would be worse than none. Run 1 should record its own wall clock per battery so the
next run can be planned from a measurement.*

**Build time: this is the real cost.** Seven items in §1.4, of which 3, 5 and 6 are genuine work
rather than edits. Item 0 is twelve characters and is the cheapest correctness improvement available
anywhere in this project. Realistically one working session for the instruments and a second for the
runs and the write-up.

**Currency: cannot be quoted from this record, and should not be guessed.** `FINDINGS.md` §5.10
states it directly — `.autodev/metrics.jsonl` holds one row with no cost fields. What *is* on the
record for scale: the whole original investigation ran 4 hours 1 minute across three worker sessions
and produced 2.1 MB and about 117,000 words. Run 1 is a fraction of that scope.

---

# RUN 2 — the timing run

*The investigation calls this **E2**, defined in `FINDINGS.md` §5.7 condition 4 and §5.11. This spec
re-writes its bar per Evan's correction, and changes its shape in three other places, all noted.*

## 2.1 The question

**How long does a person wait for one dashboard widget, at each of three collection sizes, on each
of the paths available — and is the compiled path's wait short enough to be worth building?**

Not "is it faster than Python". Not "by what multiple". How many milliseconds.

### Why every existing measurement fails to answer this

There are six sizes of measured end-to-end timings in `FINDINGS.md` §4.4, and none of them answers
the question, for two independent reasons.

**First, the widget that was measured is outside the restricted subset.** The measured widget's
whole point is `days_between(today(), $.due_date)` — a date function. Date functions are excluded
from every candidate subset. `FINDINGS.md` §5.11 states the consequence: *"every end-to-end number
in the record was measured on a widget every proposed subset excludes."* So the record contains
precisely zero measurements of the thing that might actually be built.

That matters quantitatively, not just formally. Here are the measured per-row costs of five compiled
predicates, from the same rig (`analysis/index-shape.md` §4.1, divided here by the rows each
predicate actually scanned):

| compiled predicate | rows scanned | execution | **per row** |
|---|---:|---:|---:|
| `$.status == "open"` | 50,000 | 136.5 ms | **2.73 µs** |
| `$.score > 90` | 50,000 | 371.5 ms | **7.43 µs** |
| `$.score * 2 > 180` | 50,000 | 1,158.8 ms | **23.2 µs** |
| `contains($.summary, "hold")` | 150,000 | 870.6 ms | **5.80 µs** |
| `days_between(today(), $.due_date) < 7` | 50,000 | 3,301.9 ms | **66.0 µs** |

The date predicate is **24× more expensive per row than a simple equality**. Everything the record
says about the compiled path's speed was measured on the most expensive shape in the language, and
then excluded from the subset anyway.

**Second, the host load during the sweep was never recorded.** `FINDINGS.md` §4.6 re-ran four of the
sweep's own queries at a measured 1-minute load average of 29 and the per-row date cost moved
**+246% to +282%**. §4.11 splits the error band by what the number is bound by: CPU-bound per-row
costs are the fragile ones, scan- and IO-bound costs are robust. The single headline multiplier
moves by a third (3.79× down to 2.55×) between the sweep and the one load-controlled re-run in the
record. A latency bar in absolute milliseconds is unusable against numbers taken at an unknown load.

**This machine is at load 16.18 on 20 cores as this is written [measured 2026-08-21].** Run 2 cannot
start today.

## 2.2 THE BAR — ruled on delegated authority, 2026-08-21

> **This section used to be a proposal waiting on Evan.** He delegated it. Logged as **GA-4** in
> `.autodev/events.jsonl`, 2026-08-21T19:43:01Z, verbatim:
>
> > "I feel like these questions can be answered with your best judgement. I give them to you to fulfill
> > what I had said in the form. I approve the spec for T-2"
>
> So the numbers below are a **ruling on delegated authority** — mine, derived from his recorded
> instruction, **not his own decision**, and labelled that way wherever they appear. GA-4 is logged
> against ticket T-2 while its wording covers the open questions generally; this ruling treats it as
> covering this one. **Nothing about what Run 2 measures changes if he moves a line.** The run produces
> milliseconds; the bar is a line drawn across them afterwards. Moving it costs nothing and re-runs
> nothing.

His instruction, verbatim (Q1, re-confirmed as GA-3):

> "Benchmark absolute user-facing latency rather than treating a 3.79×–7.15× relative slowdown as
> intrinsically fatal."

### The shape of the ruling: a bar per collection size, not one number

**Because "what a person actually waits" is not one thing.** A 20,000-row widget is a page load; a
million-row widget is a report someone asked for knowing it was big. Same person, different patience.
The document's own opening table makes the point: across those two sizes the *ratio* moves by less
than 2× while the *wait* moves by about 1,200×. A single absolute number inherits the same defect from
the other side — set it where the million-row case is winnable and it says nothing at 20,000; set it
where 20,000 is meaningful and the million-row case is failed before the run starts.

So: **three bars, one per size.** Tight where the interaction is interactive, looser where the person
has already accepted they asked a big question.

**Measured as: the median wall clock of one complete widget resolve, on the shippable compiled path,
on a quiet host, over at least 5 repetitions.** *(Median = the middle measurement of the repetitions,
so one slow outlier cannot move it. 95th percentile = the wait that 19 loads out of 20 come in under —
the bar on the unlucky load rather than the typical one.)*

| collection size | **PASS if median ≤** | and 95th percentile ≤ | today's Python, measured | is today's answer correct? |
|---:|---:|---:|---:|:--|
| **20,000** | **350 ms** | 700 ms | 300.10 ms | **yes** — top-50 recall 100% |
| **100,000** | **1,000 ms** | 2,000 ms | 899.26 ms | **no** — recall 38%, 31 of 50 displayed rows do not belong |
| **1,000,000** | **5,500 ms** | **8,331 ms** | 8,331.43 ms | **no** — recall 4%, 48 of 50 rows wrong, top row wrong |

All three must pass. Today's figures are `FINDINGS.md` §4.4; the recall figures are §4.7.

*On the two tail numbers at 20,000 and 100,000: the 2× allowance is a **convention, not a
measurement**, and is flagged as such. For scale, the measured spread within the old sweep's own
repetitions was small — Python at 20,000 ran [277.15–313.17] around a 300.10 median (±6%), at 100,000
[879.17–921.43] around 899.26 (±2.3%), and the compiled arm at 1M [59,269.94–60,409.79] around
59,590.03 (±1%) (§4.4). A 2× tail allowance is generous against that; its job is to catch an outlier,
not to encode a target. **The 1M tail number is not a convention** — see the kill condition below.*

### The hard condition — it must beat what already exists

**At 100,000 and 1,000,000 rows the compiled path's median must be strictly below the Python path's
median measured in the same session.** At a million rows that is the **8,331.43 ms** in the table
above. **Failing to beat what exists is a kill, whatever the absolute number** — there would be no
reason to build it. This document already said so about the 1M line; the ruling makes it a condition
rather than a remark, and extends it to 100,000.

**At 20,000 rows the same principle takes a different form.** Today's answer at 20,000 rows is already
exactly right — row-for-row identical to the compiled arm (§4.7) — so the compiled path buys no
correctness there and cannot be justified by winning a race it does not need to win. The test at that
size is **no perceptible regression: within +100 ms of the Python path measured in the same session.**
100 ms is roughly the point at which a person starts to notice a page got slower. Note this is an
absolute increment, not a ratio; it is consistent with Evan's correction rather than a smuggled-back
multiple.

*(This split is the one place the ruling interprets rather than applies, so it is flagged. If Evan
wants the strict form everywhere — compiled must beat Python at 20,000 too — that clause simply
becomes "< the same-session Python median" and nothing else in the spec changes. Worth knowing what he
would be choosing: the compiled arm measured **1,138.61 ms** at 20,000 rows against Python's 300.10
(§4.4), so strict-beat-at-every-size is close to a decision taken in advance.)*

**Use the same-session number, not the recorded one.** The kill test compares against Python measured
in the same session on the same host. If that number lands far from the recorded 8,331.43 ms, that is
itself evidence the host was not quiet — and §2.5 item 1 voids the cell.

### Why 5,500 ms at a million rows, and not the 2,500 ms this document used to propose

The reason is in this document's own arithmetic. Every figure here is measured or cited, none is new:

| | µs per row | what it is |
|---|---:|---|
| scan that reads one JSON key, no expression | **0.11** | §4.6 at 1M |
| native operator ceiling (unsafe) | **0.23** | §4.4, B4 at 1M |
| scan that touches and serialises every row | **0.50** | §4.4 — the 502 ms floor |
| **2,500 ms — the earlier proposal** | **2.5** | |
| cheapest compiled predicate ever measured (`$.status == "open"`, W1) | **2.73** | §2.1's table, from `analysis/index-shape.md` §4.1 |
| **5,500 ms — THE RULING** | **5.5** | `panel.json[2]`'s C-0 gate, restated in `FINDINGS.md` §5.7 condition 4, converted into the milliseconds it produces |
| `$.score > 90` (W2) | **7.43** | same source |
| **8,331 ms — the kill floor** | **8.3** | today's measured Python median at 1M, §4.4 |
| one `xpr.pdate_ms` call | **11.95** | §4.6, constant across three orders of magnitude of table size |
| the arithmetic predicate `$.score * 2 > 180` (W3) | **23.2** | same source as W1/W2 |

**2.5 µs/row is below the cheapest compiled predicate that has ever been measured.** A bar set below
every measurement in the record is a bar the run cannot inform — it decides the answer before the run
starts, and Run 2 is the expensive one (§2.6: an exclusive quiet host, a full corpus rebuild, 2–3
hours). Evan's instruction was to stop treating a *multiple* as fatal and start measuring the *wait*.
It was not an instruction to set the wait so low that only an encoding nobody has written could reach
it.

**5.5 µs/row is not invented for this ruling.** It is the gate the earlier panel set *before* the
evidence was collected (`panel.json[2]`'s C-0, restated in `FINDINGS.md` §5.7 condition 4). All the
ruling does is convert it out of the unit the record used and into the unit Evan asked for. A
pre-registered line, restated in milliseconds, is the most defensible number available here.

**And it still delivers everything the bar exists to test:**

- **1.5× faster than the 8,331 ms a person waits today** — nobody waits longer than they do now, while
  the answer stops being 96% wrong. That is the user-facing claim Run 2 exists to test.
- Comfortably inside the ten-second conventional limit of held attention. *(General human-factors, not
  measured on this machine or on Evan's users — flagged as the softest input to this ruling, exactly as
  it was flagged for 2,500.)*
- **~3× better than the correctness-matched alternative** — the 20,000-row cap lift Evan already
  approved under Q16, which costs about **16.7 s** at 1M. *(INFERENCE, by `FINDINGS.md` §5.5's method;
  Run 2 converts it into a measurement, §2.3.)*
- **Achievable in principle, measured:** the unsafe native-operator arm ran this exact widget over
  1,000,000 rows in **229.99 ms** returning a row-for-row identical answer (§4.4). 5,500 ms leaves a
  **24× budget for the cost of doing it safely.**
- It is **11× the 502 ms floor** for a scan that touches and serialises every row, and **52× the 106 ms
  floor** for a scan that reads one JSON key per row (§4.4, §4.6).

**What loosening the line gives up, stated so it can be argued with.** At 5,500 ms the widget is
correct and moderately faster; it does not feel *fast*. A person waits five and a half seconds and
watches a spinner. 2,500 ms was the line at which the compiled path would win on both axes a person
can feel, and the ruling trades that for a bar the run can actually decide. If Evan wants the ambitious
line back, one word restores it — and this document's own closing note applies: Run 2 reports the
milliseconds either way, so the line can be redrawn afterwards without re-running anything.

### The interactive bars — these are the tight ones

**20,000 rows → 350 ms.** Anchor: the measured Python median at this size is **300.10 ms** (§4.4), and
at this size the answer is already perfect (§4.7). So this is a no-regression bar, not an improvement
bar. The +50 ms of headroom sits below the threshold at which a change in page speed is perceptible.

**100,000 rows → 1,000 ms.** Four anchors:

- One second is the conventional threshold below which a person keeps their train of thought. **This
  is a general human-factors number, not something measured on this machine or on Evan's users** — the
  softest input at this size, flagged as such.
- Today's Python answers in **899.26 ms** but 62% of the displayed rows are wrong (§4.4, §4.7).
  Spending ~100 ms more to be right is a good trade.
- The correctness-matched Python alternative — the cap lift Evan approved under Q16 — costs about
  **1.6 s** at this size. *(INFERENCE, my arithmetic, by `FINDINGS.md` §5.5's method at 1M: the
  already-paid 728 ms acquisition plus derive at 7.27 µs/row and filter at 1.23 µs/row over 100,000
  rows.)* So 1,000 ms also beats the cheap alternative.
- **Achievability:** a full scan at this size reading one JSON key out of every row measures
  **25.74 ms** (§4.6). That is 2.6% of the budget, leaving 97% of the second for expression work. The
  bar is not below the physics.

**Per-row budget across the three: 17.5 → 10.0 → 5.5 µs/row.** It tightens with size because a
person's patience does not scale with the row count. **The 1,000,000-row bar is still the binding
one** — if it passes, the other two almost certainly follow. If Evan only wants to argue about one
number, that is still the one.

### The three lines side by side, so the choice stays visible

| line at 1M | per-row budget | what it means for a person | status |
|---:|---:|---|---|
| 2,500 ms | 2.5 µs | correct *and* feels fast — but below every compiled predicate ever measured | the earlier proposal — **not taken** |
| **5,500 ms** | **5.5 µs** | correct, 1.5× faster than today, ~3× faster than the approved cap lift; a spinner, not a coffee break | **RULED** |
| 8,331 ms | 8.3 µs | correct instead of 96% wrong, but no faster than today | **the kill line** |

**The 8,331 ms line is not a bar, it is a floor.** At or above it the compiled path is not faster than
what a person waits today, and its only remaining argument is correctness — which the cap lift Evan
already approved under Q16 also delivers, for one line of code. A result at or above 8,331 ms means
**build nothing**.

### One thing the bar cannot decide on its own: the widget

A bar in milliseconds only means something once the widget's per-row cost is known, and the compiled
predicates measured on the same rig differ by **8.5×** — 2.73 to 23.2 µs/row (§2.1, from
`index-shape.md` §4.1). Against the ruled bars:

| bar | budget | `$.status == "open"` · 2.73 µs | `$.score > 90` · 7.43 µs | `$.score * 2 > 180` · 23.2 µs |
|---|---:|---|---|---|
| 20,000 → 350 ms | 17.5 µs/row | fits | fits | **does not fit** |
| 100,000 → 1,000 ms | 10.0 µs/row | fits | fits | **does not fit** |
| 1,000,000 → 5,500 ms | 5.5 µs/row | fits, ~2.8 µs/row left for scan, sort and transfer | **does not fit** | **does not fit** |

§2.1 names the arithmetic shape `$.score * 2 > 180` as the predicate this run uses. **On the isolated
measurements, that shape fits none of the three bars.** Those numbers were taken as standalone
predicate scans on a 50,000-row table, not as arm C over the corpus, so they do not settle it — but
they make one step mandatory:

**Pre-flight, before the expensive 1M pass:** run the chosen widget's predicate alone over the
100,000-row table under `EXPLAIN (ANALYZE, BUFFERS)`, divide the execution time by the rows scanned,
and record the µs/row. It costs one query, and it is exactly the method of `index-shape.md` §4.1. If
that figure times 1,000,000 already exceeds 5,500 ms, the 1M pass still runs and still reports its
milliseconds — but nobody should book the exclusive quiet host believing the answer is open.

## 2.3 What gets measured, and at what sizes

### Sizes

**Required: 20,000 · 100,000 · 1,000,000.** These are the three bar sizes. 20,000 is the current
`MAX_SCAN` cap and just above the largest real collection on this machine (17,148 rows, 85.7% of the
cap — `FINDINGS.md` §D.8). 1,000,000 is the "high-volume data GIMS does not have yet" that Evan named
as autoSQL's target in Q15.

**Optional if the window allows: 1,000 · 10,000 · 25,000**, purely to keep the curve comparable with
the existing sweep.

### The arms

An "arm" is one way of answering the widget. Five, per widget:

| arm | what runs where | why it is in the run |
|---|---|---|
| **A — today** | everything in Python, with the 20,000-row cap in place | what a person waits today. The baseline. |
| **A-uncapped** | everything in Python, cap lifted | **the correctness-matched baseline, and currently only an inference.** `FINDINGS.md` §5.5 quotes ≈16.7 s at 1M as arithmetic, never measured. Evan approved the cap lift in Q16; this is the number he approved, and it should be a measurement. |
| **C — the shippable compiled path** | Postgres evaluates the derive and the `where` predicate; Python does the sort and the limit | **the arm the bar applies to.** See below. |
| **B2 — fully compiled** | Postgres does everything including sort and limit | the ceiling if the sort obligations are ever discharged. Reported, not gated. |
| **B4 — native operators** | the same answer using raw Postgres date/number operators | the physics ceiling. **Not a candidate** — it raises an error on a malformed value where the language must return null, which is the whole reason the safe runtime exists. Reported so the headroom is visible. |

**Two arms from the original sweep are dropped, deliberately:**
- **B1** ("faithful" translation, rebuilding the whole JSON document per row) — measured at 30–36 µs/row of pure overhead at every size and slower than B2 everywhere. The question is closed.
- **B3** (the compiled query rewritten so the production GIN index becomes usable) — **Q11 closes this question permanently.** Its result was known anyway: across all six sizes B3 and B2 differ by at most 1.4%, and across 36 measured query plans the production index was used **zero times**.

**Why the bar applies to arm C and not to B2.** `FINDINGS.md` §5.7 condition 3 keeps `sort` and
`limit` out of the compiled path until ten separate ordering obligations are compiled and tested —
Postgres and Python sort mixed-type JSON values differently at 9 of 9 tested positions. So the
honest, shippable architecture today is: SQL evaluates the derive and the `where` predicate, Python
does the sort and the limit. That is arm C, and its Python tail is a real part of what a person waits — at 1M with ~5% selectivity it
means about 52,000 rows come back and get decoded in Python, roughly 310 ms of the budget by the
sweep's own measured decode rate. **A ratio hides that tail. An absolute bar cannot.** This is one of
the concrete reasons Evan's correction improves the experiment.

### The widget

**INVENTED. Labelled as invented here and required to be labelled as invented everywhere it appears
in the run's output.** Q8 asked Evan to name a real one; item 7 of the second form took the default.
If he names one before the run starts, it replaces this and nothing else changes.

```json
{ "type": "noun", "noun_type": "Sample",
  "derive": { "load_score": "coalesce($.queue_depth, 0) + coalesce($.retest_count, 0) * 25" },
  "where":  "$.load_score > 195",
  "sort":   { "field": "load_score", "dir": "desc" },
  "limit":  50 }
```

Why this shape:

- **Every construct is inside the restricted subset.** `coalesce` is one of the seven permitted functions; `+`, `*` and `>` are permitted operators; the field paths are plain keys. It must be verified mechanically with the subset checker before any timing runs — see §2.5.
- **It has no `filters` clause**, which matches the one real tenant widget found on this machine (`FINDINGS.md` §4.1) and sidesteps a clause that cannot be pushed down anyway — the obvious JSON-equality translation of `filters` silently drops 2 of 3 rows that Python's tolerant key matching keeps, and that test currently fails.
- **It sorts on a derived column**, which is the part that makes pushdown genuinely hard and which the one real tenant widget also does.
- **`coalesce` around a frequently-missing key** reproduces the real problem the date widget had with a missing `due_date`, without using a date function.
- **Its compiled predicate is the `$.score * 2 > 180` shape measured at 23.2 µs/row** — so there is an existing measured anchor for what it costs today, and the thing on trial is the numeric coercion machinery, which is 8.5× more expensive per row than a simple equality. That machinery is the right thing to put on trial, because Q11 means you cannot index your way out of a per-row coercion cost.

**The old date widget runs too, as a control.** Same corpus, same session, same recorded load. This
costs little and buys a lot: it re-establishes the entire existing sweep under a *recorded* host
load for the first time, which converts `FINDINGS.md` §4.11's largest caveat into a measurement, and
it gives a direct like-for-like comparison between a subset-legal widget and the excluded one.

### The corpus

Q31 left the tables gone, so the corpus is rebuilt. `proto/gen_data.py` keeps its seed (1729) and
every existing field, and gains two:

```python
row["queue_depth"] = rnd.randint(0, 200)
if rnd.random() < 0.15:
    row["retest_count"] = rnd.randint(0, 3)     # absent 85% of the time — this is what coalesce is for
```

Keeping every existing field means the date widget still runs on the same corpus, which is what makes
the control possible.

**Selectivity is a bar on the corpus, not a hope.** The threshold of 195 was chosen by simulating the
two new fields' distributions over 200,000 draws **[measured 2026-08-21]**:

| threshold | rows kept |
|---:|---:|
| 185 | 10.38% |
| 190 | 7.91% |
| **195** | **5.36%** |
| 200 | 2.83% |

5.36% lands on top of the original sweep's measured 5.00%–5.35%, which is what makes the two
comparable. **Required: measured selectivity between 4.5% and 6.0% at every size, reported.** If it
lands outside, tune the literal in the generator and regenerate *before* timing anything — never
after, and never by tuning until a timing looks good.

**Also required to be reported:** the new mean stored JSON size per row. The original was 283 bytes
compact and 315–317 bytes on the wire; two added keys will move it, and every payload and scan number
in the run moves with it.

**The index question.** The corpus keeps the production GIN index, because the real `instances` table
has one and the corpus's DDL is otherwise byte-identical to GIMS's own migration. Q11 does not mean
the index disappears from production; it means the generated query can never benefit from it. Run 2
must *demonstrate* that rather than assume it — see §2.5.

### One measurement the record has never taken, added here

**Concurrency, at 100,000 rows: 1, 3 and 8 widget resolves at once, reporting median and 95th
percentile latency per resolve.** Not gated — there is no baseline to set a bar against — but
reported, because "user-facing latency" measured one request at a time is a single-user number, and
`FINDINGS.md` §5.11 names concurrency as the standing gap where the memory difference between the two
paths would matter most. The Python path holds about 2.4 GB of heap per request at 1M; the compiled
path holds database CPU. Those do not degrade the same way under load.

Confined to 100,000 rows on purpose. Three concurrent 1M Python resolves would want ~7 GB of heap
against 33 GB available **[measured 2026-08-21]** — survivable, but a memory experiment rather than a
latency one, and it is not what this run is for.

## 2.4 Instruments — what exists, what has to be built

**Exists and is reused:** `proto/bench.py` (the harness, its phase timing, its ground-truth check and
its identity check), `proto/gen_data.py`, `proto/load_data.py`, `proto/compile.py`, `proto/runtime.sql`,
and the `xpr` schema already installed in Postgres.

**Has to be built or edited (all permitted by Q7):**

| # | work | why |
|---|---|---|
| 1 | **Record host load** — read `/proc/loadavg` before and after every size, into the output JSON | the sweep's own load was never recorded and it is the largest known error source |
| 2 | **Add the two generator fields**, and report measured selectivity and mean record size | §2.3 |
| 3 | **Add arm C** — compiled derive and `where`, Python sort and limit | this is the arm the bar applies to and it does not exist |
| 4 | **Add arm A-uncapped** — Python with `MAX_SCAN` raised out of the way | converts `FINDINGS.md` §5.5's ≈16.7 s from arithmetic into a measurement |
| 5 | **Make the widget selectable**, so the invented widget and the date control both run in one session | `WIDGET` is currently hard-coded at `bench.py:32` |
| 6 | **Drop the B1 and B3 arms** | §2.3 |
| 7 | **Capture and assert on the query plan** for every compiled arm at every size | the Q11 check, §2.5 |
| 8 | **Report dispersion**, not just medians: min, median, 95th percentile, max, and the repetition count per cell | medians alone hid the load sensitivity last time |
| 9 | **Pin and record `synchronize_seqscans`** | `FINDINGS.md` §4.9 measured a **170× spread on an identical query and table** — 40.76 ms versus 6,916.85 ms — from this setting alone. An unrecorded value makes a millisecond bar meaningless. |
| 10 | **Fix the peak-memory measurement or drop it** | the existing figure is a whole-process high-water mark read once, so the 1M number carries the 100k arm's residue. Either one process per size, or measure per call, or do not report it. |

## 2.5 What would make the result inadmissible

Any one of these voids the run, or the affected cell:

1. **Host load not recorded, or above the ceiling.** Required: the 1-minute load average is ≤ 2.0 when a size starts and ≤ 4.0 when it ends, on this 20-core host, recorded both times. Outside that, the cell is void and re-run. *(For scale: this machine reads 16.18 right now.)* This is the condition `FINDINGS.md` §5.7 condition 4 asks for as "quiet host, load recorded" and it is the one the original sweep did not meet.
2. **Any compiled arm using an index.** Capture `EXPLAIN (ANALYZE, BUFFERS)` for every compiled arm at every size and assert no index-scan node appears other than the primary key doing the `collection = …` lookup. If a generated query turns out to benefit from an index, its timing is inadmissible as evidence about the world Q11 creates.
3. **The widget not verified subset-legal**, mechanically, before timing. If it uses a construct outside the 32-construct subset, the run has measured something nobody proposes to build — which is exactly what happened to the entire existing sweep.
4. **The arms not returning the same answer.** Required: row-for-row identity between arms at sizes where Python is correct (≤ 20,000), and identity against ground truth computed by an uncapped query above the cap. If the arms disagree, the timing comparison is between two different questions.
5. **Fewer than 5 repetitions at any size**, or dispersion not reported. The old sweep used 3 at 1M.
6. **Corpus selectivity outside 4.5%–6.0%**, or mean record size not reported. Both silently move every number in the run.
7. **Cache state not stated.** Report buffer hits and reads from the plans and state the warm-up policy. The original document claimed everything was warm-cache at every size; that was false at 100,000 and 1,000,000 rows.
8. **`synchronize_seqscans` unrecorded** (§2.4 item 9).
9. **A ratio quoted as the verdict.** Ratios are reported; the bar is milliseconds. This is Evan's correction and it applies to the write-up as much as to the design.
10. **Anything written into either GIMS checkout.** Read-only, both.

## 2.6 What it costs

**This is the expensive run, and most of the cost is scheduling.**

| item | cost |
|---|---|
| **Exclusive quiet host** | The binding constraint. Twenty cores, currently at load 16.18 **[measured 2026-08-21]**. Nothing else may run on this machine during measurement — including other AutoDev work. Realistically 2–3 hours of exclusive window, since voided cells have to be re-run. |
| **Corpus rebuild** | Mandatory under Q31. Roughly 823 MB of database across the six sizes, of which 700 MB is the 1,000,000-row table (419 MB of data, 281 MB of index), plus a CSV per size — 359 MB at 1M. Disk: **20 GB free of 457 GB, 96% used [measured 2026-08-21]**. It fits, but not comfortably; generate and drop the CSVs one size at a time. |
| **Known load failure to plan around** | The 1,000,000-row load previously aborted at its `VACUUM ANALYZE` with `DiskFull: could not resize shared memory segment`. The container's `/dev/shm` is the Docker default of 64 MB, and `max_parallel_maintenance_workers` — which was set to 0 to get that load through — has since been reverted to 2. Either set it back to 0 for the load or enlarge `/dev/shm`. **Load timings are not quoted here: the record's own figures were struck as uncitable because their output was never captured. Run 2 should record its own.** |
| **Measurement time** | Estimated 25–40 minutes per complete pass, dominated by the 1M cells: five arms × two widgets × at least five repetitions, with the fully-compiled date arm alone at about 60 s per repetition. Budget 2–3 passes — which, with corpus rebuild and voided cells, is where the 2–3 hour window above comes from. |
| **Build time** | Ten items in §2.4. Items 3, 4 and 7 are real work; the rest are edits. About one working session. |
| **Currency** | Not quotable from this record — same reason as Run 1. Q9 in any case sets no cap on this run. |

---

## What happens after each run

**Run 1 fails after the guard is fixed** → the restricted subset does not exist as a safe set, and
the NO-GO stops being provisional. Cheapest possible ending, which is why Evan put it first. *(Run 1
fails **before** the guard is fixed — that is already known, §1.2 — so "Run 1 failed" only means
something once step zero is done and recorded.)*

**Run 1 passes, Run 2 fails** → there is a provably-agreeing subset that is too slow to be worth
shipping for speed. That is not nothing: it makes the correctness argument on its own merits, against
the cap lift Evan already approved, and it says so with a number rather than a multiple.

**Both pass** → the ticket's premise is established on evidence, and the remaining work is the one
the investigation says was always the hard half: the GIMS-side changes that let a fallback be
*reported* rather than silently taken. Nothing in either run touches that.

**A note on moving the bar.** Run 2 produces milliseconds. If the 1M number lands at, say, 6,500 ms,
that is a FAIL under §2.2's ruled bar — but a FAIL that still beats the 8,331 ms a person waits today,
which is a very different decision from a FAIL at 23,000 ms. The spec requires the number to be
reported either way, and Evan can redraw any line afterwards without re-running anything. **What he
cannot redraw away is the kill condition** (§2.2): at or above the same-session Python median, the
compiled path has no argument left.

---

## Words used above that are worth pinning down

Written because Evan asked for the database reasoning explained and the coding basics skipped (Q41).

**Sequential scan** — Postgres reading every row of a table in order, because nothing lets it skip
any. Under Q11 this is what every autoSQL query does, always. Its cost is proportional to the row
count, which is why absolute latency bars get harder as the collection grows.

**Index** — a separate structure that lets Postgres jump to the rows it wants instead of reading all
of them. Q11 rules them out for generated queries. The production one still exists on the table; it
just never helps here — across 36 measured query plans it was used zero times.

**Query plan / `EXPLAIN`** — Postgres explaining what it intends to do, or what it did, before or
after running a query. It names which indexes it used, how many rows it threw away, and how many
disk pages it read. Run 2 uses it to prove no index helped.

**Selectivity** — what fraction of rows survive the filter. It is the single biggest lever on both
paths' cost, which is why it is pinned rather than left to chance.

**Buffer cache** — Postgres's in-memory copy of recently-read pages. A query hitting warm cache and
the same query hitting cold disk are different measurements, so the run states which it took.

**`extra_float_digits`** — the Postgres session setting controlling how many digits a float prints
as. Q10 puts it at the centre of Run 1. Explained at §1.1.

**`IMMUTABLE`** — a promise the author of a SQL function makes to Postgres: same input, always same
output. Postgres trusts it without checking. Four of the runtime's functions make that promise and
break it by reading `extra_float_digits`.

**Pushdown** — doing the filtering inside the database instead of pulling every row into Python and
filtering there. It is the whole point of autoSQL.

**Median / 95th percentile** — the middle timing, and the timing 95% of runs come in under. The
median is what a person usually waits; the 95th is the bad day they remember.

**Common-subexpression elimination** — noticing that the same expression is written several times in
one query and computing it once. The current compiled query evaluates the derive expression four
times per scanned row; this is the first and most obvious thing an implementation would fix.

**Arm** — one of the several ways the same widget is answered, timed side by side.

**Battery** — one file of related test cases in `analysis/fuzz/`, each printing its own evidence.

**Fixture** — the 130 hand-authored expression test cases GIMS ships (`expr_vectors.json`). It is the
contract between the Python and JavaScript versions of the language. Evan ruled (Q2) that it is not
adequate as the acceptance test for a third, SQL version — Run 1 is what replaces it.

**Negative control** — a deliberately broken input, used to prove the test rig can report a failure
at all. A rig that has only ever printed "pass" has not been shown to be capable of printing anything
else. This is what Evan asked for in Q4, and §1.4 item 6 extends it to the one instrument the Q4 run
did not cover.

**Inadmissible** — the run produced a number, but something about how it was produced means the
number cannot be used to decide anything. Each run's §5 lists what does that.
