# T-3 · Framing — the correctness run

Stage: `sp-frame` (spike@v2) · lean: ON (ruled, §11 R3) · risk: medium (ruled, §11 R2) ·
decision authority: `recommend-and-wait` (ruled, §11 R2)
Framed: 2026-08-21 · every figure below re-read from the file it came from, or measured
live on this machine that day and marked **[measured 2026-08-21]**.

> **Refreshed 2026-08-22** — `sp-frame` re-validated before `sp-investigate`. Nothing about
> the question (§1), the bar (§3), the wrong-answer/refusal line (§4.1–4.7), the
> admissibility list (§5), the risk statement (§10) or the glossary (§12) changed — those
> sections were audited against the repo as it stands and hold. What did change:
> **(1)** GA-4's scope is now **confirmed wide by Evan himself** — wrap-up item 1, answered
> 2026-08-22, recorded as **GA-6** with `scope_confirmed: true` — so §2 C1 and §11 R1 no
> longer rest on an unconfirmed delegation; the loud-refusal ruling also survived its own
> wrap-up question (item 7) on the stated default. §2 C1, §6 and §11 updated.
> **(2)** Evan confirmed the GIMS boundary (wrap-up item 2): the "don't build yet" tick
> governs GIMS and **nothing enters GIMS until T-3 and T-4 pass**; the note describes the
> demo. §6 and §7 updated. **(3)** Every `conformance.py`/`differ.py` line number this
> document cited drifted the day it was written: commit `01e75b0` — the very commit that
> first checked this file in — rewrote nine spike scripts to fail closed on the live
> database, shifting the cited lines. Corrected in §2 C2–C4, §4.8 and §11, each marked
> **[re-verified 2026-08-22]**. **(4)** §9 rewritten: the scratch database `autosql_spike`
> was **dropped** later on 21 Aug (Q31, same commit), so "T-3 needs no database rebuild" is
> reversed — the run brings up its own throwaway container and must never point at
> `glp-strong-db`, Evan's live container, which every spike script now refuses by port.
> Container health, Postgres 16.14, Python 3.12.3, the instruments, and the two 297-digit
> guard literals were all re-verified live on 2026-08-22; disk is at 96%.
> **(5)** §8 gains the one calendar fact GA-6 item 28 supplies: T-3 is on today's slate.

> **What this document is, and why it exists before the work.** T-3 is a *spike* — AutoDev's
> word for a piece of research that answers a question rather than shipping a feature. A spike
> runs through five stages (`sp-frame → sp-investigate → sp-synth → sp-decide → sp-spawn`);
> this is the first. Its entire job is to **fix the bar before any evidence is collected**, so
> that when the numbers arrive nobody — including me — can quietly move the target to fit them.
> Nothing here is a result. Nothing here has been run.
>
> This follows the shape of `spikes/T-1/FRAMING.md`, which did the same job for the parent
> investigation, and it is bound by the full specification in `spikes/T-1/EXPERIMENTS.md` §1.
> Where the two differ, EXPERIMENTS.md §1 is the specification and this is the bar.

---

## 1. The question

> On the **restricted 32-construct subset only**, with the known 12-digit guard defect fixed
> first, does the SQL autoSQL generates ever disagree with GIMS's Python evaluator — a
> different value, a value becoming null, a null becoming a value, or Python raising where SQL
> quietly returns a number — at **any** of Postgres's three `extra_float_digits` settings?

One sentence, and it is the whole ticket. Everything else in this document exists to stop that
question being answered dishonestly.

**The subset, so "restricted" is not vague.** 32 of the expression language's 48 constructs,
covering 68 of the 130 contract test cases (`FINDINGS.md` §5.7). The functions in it are exactly
seven — `abs coalesce count if length max min`. Dates, strings, `sum`, `avg`, `round`, `floor`,
`ceil` and `%` are all outside it.

**`extra_float_digits`** is a Postgres session setting that controls how many digits Postgres
prints when it turns a floating-point number into text. It is not cosmetic here: it changes what
`to_jsonb(float8)` itself returns, so it is on the **value** channel, not the display channel
(`analysis/fuzz/M_encoding_guc.txt` §M1):

```
efd =  1    1/3 -> 0.3333333333333333
efd =  0    1/3 -> 0.333333333333333
efd = -3    1/3 -> 0.333333333333
```

The three settings in the question are `1`, `0` and `-3`. Evan required all three (Q10).

---

## 2. Four corrections to the ticket as written

The T-3 ticket file was checked line by line against the machine before this framing was written.
Four things in it no longer hold. None changes the question; all four change what the run must do.

### C1 — the ticket's "BLOCKED ON EVAN" line is already answered, and T-3 is not blocked

The ticket says:

> "BLOCKED ON EVAN: how to handle that surviving divergence — exclude such expressions, write a
> named carve-out into the bar, or refuse the subset. Do not pick for him."

That block is **cleared**. `EXPERIMENTS.md` §1.2 contains a **ruling on delegated authority**
(AutoDev's term for a decision Evan handed to me rather than made himself) picking **none of the
three**: the divergence becomes a **reported runtime refusal**. The authority is **GA-4**, a
*go-ahead* — a recorded line from Evan authorising a class of decisions — logged verbatim in
`.autodev/events.jsonl` at `2026-08-21T19:43:01.819Z`:

> "I feel like these questions can be answered with your best judgement. I give them to you to
> fulfill what I had said in the form. I approve the spec for T-2"

**The scope of that line is no longer an open question [settled 2026-08-22].** GA-4 was
logged against T-2 only, with `scope_confirmed: false`, and this framing leaned on it anyway
— that gap was put back to Evan as wrap-up item 1 (*"GA-4 approved one ticket; it was used
to rule on three"*). He answered: **"It covered everything I was asked."** Recorded as
**GA-6** (`.autodev/events.jsonl`, `2026-08-22T17:35:37.208Z`, `scope_confirmed: true`).
Every ruling taken under GA-4 — this one included — stands as written, on confirmed
authority rather than on a session's reading of one sentence.

**Why the ticket still says otherwise:** it was created at `19:26:07Z` (T-1's `sp-spawn` receipt),
just under seventeen minutes *before* GA-4 was recorded (16 min 54 s). The ticket is stale, not
contradictory. Ticket files are never edited by this seat, so the correction lives here.

**Consequence, and it is the largest one in this document:** the pass bar stays at **zero wrong
answers**, because a reported refusal is not a wrong answer. Without that ruling the corrected
subset cannot pass at all, and the zero would have to be a zero with an exception written beneath
it. §4 makes the wrong-answer/refusal line sharp enough to hold weight.

**One line from Evan overturns it** — *"take the carve-out"* or *"exclude those expressions"* —
and only the reporting changes. Nothing needs re-running. That exact choice was in fact put in
front of him, verbatim, as wrap-up item 7 on 2026-08-22; he left it on its stated default —
**the ruling stands.** So it has now survived twice: once under item 1's wide-scope answer,
once under its own dedicated question.

### C2 — two line citations in the spec have drifted, and the run edits those exact lines

| `EXPERIMENTS.md` §1 says | actually **[re-verified 2026-08-22]** |
|---|---|
| "parameterise `proto/conformance.py:341`" | the pin is at **`conformance.py:367`** — `cur.execute("SET extra_float_digits = 1")` |
| "the classes already exist in `analysis/fuzz/differ.py:74-78`" | the class list is at **`differ.py:91-97`**, and there are **seven** classes, not five |

Trivial in themselves. Not trivial in effect: both are lines the run is required to edit, and a
seat editing by line number instead of by content edits the wrong line.

And the drift happened to *this document* too, the day it was written. The framing measured
the pin at `conformance.py:343` and the classes at `differ.py:81-87` at 14:47; commit
`01e75b0` — the very commit that first checked this file in — then rewrote nine spike
scripts to fail closed on the live database (§9) and shifted every one of those lines. The
table above holds the 2026-08-22 positions. The rule is now double-proved: **find these
lines by their content, never by their number.**

### C3 — the same float-digit pin exists a second time, in the instrument that matters more

`analysis/fuzz/differ.py:79` **[re-verified 2026-08-22; sat at `:69` when framed]** also
hard-codes `SET extra_float_digits = 1`, with the comment `# PG12+ default, pinned`.
`EXPERIMENTS.md` §1.4 lists the parameterisation work against `conformance.py` only.

**So the fuzz batteries — which is to say all 21 of them, every random-expression draw, the entire
body of evidence this run is built on — would silently run at setting 1 three times over**, and
produce three identical passes that look like Q10 was satisfied. This is added to the
inadmissibility list as §5 item 11, with a positive control attached.

### C4 — `differ.py`'s own code contradicts the GA-4 ruling and must be split before the run

`differ.py:169` **[re-verified 2026-08-22]** classifies a Postgres raise as `SQL_RAISE` with
the inline comment `# FRAMING section 5: highest severity`, and its docstring at `:93` calls
it a "totality violation". Under T-1's framing that was correct. Under the GA-4 ruling it is no longer:
a **named, deliberate** refusal is now an allowed outcome, while an **unexplained** raise is still
a defect. The instrument currently cannot tell those apart, so it would score the ruling's
intended behaviour as the highest-severity failure.

`SQL_RAISE` must be split into two reported classes before any number is quoted — §4.4.

---

## 3. The pass bar

**Zero wrong answers of any kind, at each of `extra_float_digits` = 1, 0 and −3, reported
separately.** Not "few". Not "none we could reach". Not "none in Evan's data". Zero.

| # | wrong-answer class | count required, per setting |
|---|---|---|
| 1 | **different value** — both sides returned a value and they differ under the mirrored comparison rule | **0** |
| 2 | **value → null** — Python returned a value, SQL returned null | **0** |
| 3 | **null → value** — Python returned null, SQL returned a value | **0** |
| 4 | **Python raised, SQL returned a value** (`PY_RAISE` in `differ.py`) | **0** |

Three separate reports, one per setting. **A pooled figure across the three settings is
forbidden** — it would hide which setting broke, which is the entire reason Q10 exists.

**Class 4 is the one the existing instruments cannot see.** `differ.py` buckets `PY_RAISE` away
from `DIVERGE`, so today a run can print "zero divergences" while Postgres is confidently
answering questions Python refuses to answer at all. That is the exact direction the project is
worried about and it gets its own counted line.

**There is no partial credit and no acceptable rate.** A wrong number on a dashboard has no
acceptable rate. This is not severity theatre: `FRAMING.md` §5 (T-1) set the same bar before any
evidence existed and it has not moved.

### The state to beat, so a zero means something

Current measured divergence counts from the three broad fuzz batteries over **unrestricted**
expressions (`FINDINGS.md` §5.7, from `analysis/fuzz/H_*.txt`). Denominators are expressions that
actually ran — agree + diverge + SQL-raise:

| battery | diverging | ran |
|---|---:|---:|
| `H_ordinary` (values shaped like dashboard data) | **0** | 3,881 |
| `H_unicode` (non-ASCII strings) | **4** | 3,867 |
| `H_extreme` (pathological magnitudes) | **23** | 3,880 |

Under the restriction to the 32 constructs all three should go to zero — every construct blamed
for those 27 is outside the subset. If they do not, the subset does not exist and T-3 has killed
the project cheaply, which is an outcome this run is designed to be able to produce.

### And the subset fails this bar today — that is the starting position, not a surprise

`analysis/fuzz/A_f8_guard.txt` §A2 drove twenty expression paths against a record holding
`a = 1e300` — an ordinary finite double, not an infinity, comfortably inside what a `float8`
column holds. **16 of the 20 diverge.** Eight of those sixteen are entirely inside the restricted
subset:

| expression | Python | SQL | class |
|---|---|---|---|
| `$.a + 0` | `1e+300` | **null** | 2 |
| `$.a * 1` | `1e+300` | **null** | 2 |
| `- $.a` | `-1e+300` | **null** | 2 |
| `abs($.a)` | `1e+300` | **null** | 2 |
| `$.a < 1e301` | `True` | **null** | 2 — and this is the `WHERE`-clause path: the row silently vanishes |
| `$.a > 1` | `True` | **null** | 2 — same |
| `$.a >= $.a` | `True` | **null** | 2 — same, both operands |
| `max($.l)` | `1e+300` | **`1`** | **1 — a wrong number, not a null** |

Re-confirmed live against the scratch database **[measured 2026-08-21 — the scratch database
itself was dropped later that day, so re-running these three lines needs the throwaway
container of §9]**:

```
xpr.f8('1e300'::jsonb) IS NULL   ->  t
xpr.num('1e300'::jsonb) IS NULL  ->  t
xpr.f8('1e290'::jsonb)           ->  1e+290      (below the guard, fine)
```

**The cause is one mistyped literal.** `proto/runtime.sql` guards its JSON-to-`float8` conversion
against anything above the largest representable double. The guard is spelled out as a full
integer and it is short **[counted mechanically at both sites 2026-08-21; re-counted
2026-08-22 — unchanged, still 297 digits at `runtime.sql:33` and `:51`]**:

| | |
|---|---:|
| digits in the literal, `runtime.sql:33` (`xpr.f8`) | **297** |
| digits in the literal, `runtime.sql:51` (`xpr.num`) | **297** |
| digits the real limit needs | **309** |
| **shortfall** | **12 digits** |

So every finite number of magnitude ≈1.8e296 or larger is treated as out of range and turned into
null — about 12 of the exponent's 632 decades, bisected in `A_f8_guard.txt` §A3 to
`1.79769313486231587e+296`. Both sites answer `NULL::float8` on that branch (`runtime.sql:34` and
`:53`).

*A note on the size, because it differs from the spec's figure.* `EXPERIMENTS.md` §1.2 calls the
fix "twelve characters". It is twelve digits **per site**, and there are **two sites** — the spec
says so itself ("the one place is two lines"), but its headline number counts one. So step zero is
**24 characters across `runtime.sql:33` and `:51`**, both counted mechanically when framed and
re-counted unchanged on 2026-08-22. A seat that
fixes only `xpr.f8` and not `xpr.num` leaves the string-coercion path — the one `FINDINGS.md` §D.6
measured as *actually reached, repeatedly*, in real GIMS data — still guarded 12 orders of
magnitude too tight.

**Step zero of this run is fixing those 24 characters** (Q7 permits it) and re-running the twenty
`A_f8_guard.txt` §A2 paths as a before-and-after. If the eight in-subset divergences do not go to
zero, the cause is not the literal and T-3 has found something larger.

**The bar does not move because the defect is unreachable in Evan's data.** It is unreachable:
the read-only sweep at `FINDINGS.md` §D.3 examined **5,235,942 numeric values** across every GIMS
database on this machine and found **0** at or above the guard; the largest number any GIMS writer
here has ever stored is **1,787,169,706,037**, an epoch timestamp in milliseconds, **284 decimal
orders of magnitude** below it. That sweep disclaims itself in §D.8, and Q15 points autoSQL at
high-volume data GIMS does not hold yet — i.e. at data nobody has sampled. Unreachable in one
corpus on one machine is not safe.

---

## 4. Wrong answer versus refusal — the line the whole result turns on

This is the single most load-bearing section in the document. Get it wrong in either direction and
the run reports the opposite of the truth.

### 4.1 The definitions

**A wrong answer** is: **SQL produced something a consumer would use as the answer, and it is not
what Python produced.** A value, a null, a `true`, a `false` — anything that lands in a cell, or
that a `WHERE` clause uses to keep or drop a row.

**A refusal** is: **SQL produced nothing at all.** The query aborted with a raised error that
carries an identity the caller can name, and the caller reported a fallback to the Python path.

### 4.2 The operational test, so nobody has to reason from first principles

> **Would the dashboard show something, or use it to filter a row?**
> Yes → it is an **answer**, and if it differs from Python it is a **wrong answer**.
> No, the query died → it is a **refusal**.

### 4.3 The trap, stated as bluntly as it can be

> **A null is an ANSWER, not a refusal.**

Every one of the seven class-2 rows in §3 *feels* like the engine declining to answer. It is not.
`xpr.f8('1e300')` returns SQL `NULL` — verified live above — and in a `WHERE` clause that null
silently drops the row. Nothing downstream can distinguish it from a legitimately absent value.
That is precisely the silent failure the project exists to prevent, and it is class 2 of the bar,
zero-tolerance.

### 4.4 Examples of each, all from the record or measured 2026-08-21

**Wrong answers — every one of these fails the bar:**

| case | Python | SQL | class | source |
|---|---|---|---|---|
| `$.a + 0` at `a = 1e300` | `1e+300` | `null` | 2 | `A_f8_guard.txt` §A2; re-verified live 2026-08-21 |
| `max($.l)`, `l` containing `1e300` | `1e+300` | `1` | 1 | `A_f8_guard.txt` §A2 |
| `$.a > 1` at `a = 1e300`, used as a filter | `True` | `null` → row vanishes | 2 | `A_f8_guard.txt` §A2 |
| any expression where Python raises and SQL returns a number | raises | a number | 4 | structurally excluded — §5 item 2 makes the run *prove* that rather than assume it |

**Refusals — none of these fails the bar:**

| case | Python | SQL | source |
|---|---|---|---|
| `('1e400'::jsonb #>> '{}')::float8` | — | **ERROR** `"…" is out of range for type double precision` | **[measured 2026-08-21, live]** |
| `$.qty * $.price` at 1e150 × 1e160 — labelled in the battery "the shape a real dashboard writes" | `inf` | **raises `22003`**, overflow | `B_overflow.txt` |
| `$.a * $.a` at `a = 1e-200` | `0.0` | **raises `22003`**, **underflow** | `B_overflow.txt` |
| `xpr.f8` on a value above the *real* limit, after step zero and the GA-4 ruling | `inf` | **raises**, with its own error identity | the ruling, `EXPERIMENTS.md` §1.2 |

`22003` is a **SQLSTATE** — Postgres's five-character machine-readable error code, here meaning
"numeric value out of range". `B_overflow.txt`'s own count: **9 of 13 probes made Postgres raise.**
The refusal mechanism is not something anyone has to invent; it is what the database already does
everywhere *except* the one place the prototype chose to substitute a null.

### 4.5 The three conditions. A raise that fails any of them is not a refusal

1. **It aborts.** No row, no cell, no filter decision, no partial answer.
2. **It is identifiable.** It carries a SQLSTATE and message the caller can tell apart from a parse
   error, a type error, a missing-function error, or a genuine compiler bug. A raise the caller
   cannot name is not a report.
3. **It is counted, on its own line, in the denominator, per battery and per setting** — never
   folded into the agree count.

**If any of the three fails, the outcome reverts to whatever SQL actually returned** — and if that
differs from Python it is a wrong answer and the bar is failed. `EXPERIMENTS.md` §1.2 is explicit
about the escape hatch that does not exist: if `xpr.f8` and `xpr.num` cannot be made to raise
distinguishably, the divergence reverts to a written carve-out, a carve-out is an admission of a
class-2 wrong answer, and **the run records FAIL and says so plainly.**

### 4.6 The direction asymmetry — easy to get backwards, so it is stated twice

| direction | verdict |
|---|---|
| **Postgres refuses where Python answers** | a **refusal**. Allowed. Counted, reported, never a pass and never a fail. |
| **Python refuses (raises) where Postgres answers** | **class 4, a wrong answer.** Fails the bar. |

### 4.7 A refusal is not an agreement

Ruled in `EXPERIMENTS.md` §1.2 and restated here because it will be tempting: where Python returns
a value and SQL refuses, that case stays in the run's output as a refusal, in the denominator,
forever. It is being ruled **not a failure**. It is **not** being ruled a pass.

**No refusal-rate threshold is set, deliberately.** A subset that returns zero wrong answers while
refusing a large share of its inputs has passed the correctness bar and failed as a product — and
only the count makes that visible. There is no measurement in the record from which to set a
threshold, so the run produces the rate and Evan draws a line across it afterwards if he wants one.
**Overflow and underflow are counted separately**, because underflow is reachable at far less
extreme magnitudes (it needs a product that falls below the smallest double, not a value near the
largest) and nobody has ever measured its rate.

### 4.8 The three leftover buckets in `differ.py`, ruled here so the run does not improvise

`differ.py:91-97` **[re-verified 2026-08-22]** has seven classes, and §3's bar names four. The
other three are ruled as follows.

| bucket | ruling | derivation |
|---|---|---|
| `BOTH_RAISE` — both engines refuse | **not a wrong answer.** Reported on the refusal line. | Neither side produced an answer, so nothing can be wrong. §4.1. |
| `NULLNESS` — values decode equal, but one side is SQL `NULL` and the other the jsonb literal `null` | **reported on its own line; does not fail the bar by itself — *unless* the two representations behave differently in a `WHERE` or `ORDER BY`, which the run must test rather than assume.** If they do, every affected case is class 2 and the bar is failed. | Both sides mean "no value", so it is not a value↔null flip, which is what `FRAMING.md` §5 forbids by name. But `differ.py:97` calls it "a leak of the representation contract", and the filter path is where a leak becomes a dropped row. Cheapest to reverse: reporting it separately means Evan can promote it to a failure with one line and no re-run. |
| `UNCOMPILABLE` — `compile.py` refused to compile the expression | **on a subset-legal expression this is a STOP** (§8), not a class. `differ.py:96` already says it: "an honest gap, never a pass". | Either the generator emitted an out-of-subset construct — which is inadmissible, §5 item 4 — or the subset is not the 32 constructs it is claimed to be. Both make every number the run has produced meaningless until resolved. |

---

## 5. What would make the result inadmissible

**Inadmissible** = the run produced a number, but something about how it was produced means the
number cannot decide anything. These are the ways this run could hand back a green light it has
not earned. Items 1–9 are `EXPERIMENTS.md` §1.5, restated so this framing stands alone. Items 10–12
are added here.

1. **Any battery run at only one float-digit setting**, or the three pooled into one number.
2. **The input-domain gate not passed or not printed** — either half (§5.3). This is the §A.3
   mistake and it is the easiest one in this project to make twice.
3. **`differ.py` not shown able to report a failure** — see the negative control below.
4. **The generator emitting an out-of-subset construct.** Verified mechanically with
   `proto/closure_subset_coverage.py` on *every* generated expression, never by inspection.
5. **Input fingerprints not recorded** — hashes of the fixture, `expr.py`, `compile.py`,
   `runtime.sql`, plus the float-digit value, or the run cannot be re-derived later.
6. **Results quoted as a fraction of production traffic**, or the 130-case fixture presented as
   the acceptance test. There is no corpus of real tenant widget definitions in either GIMS tree
   (`FINDINGS.md` §2.9), so no fraction of traffic may be quoted at the gate.
7. **The guard-literal fix applied without a before-and-after.** The fix changes what `xpr.f8`
   returns and therefore moves the 130-case results too. Both states recorded, or nobody can tell
   which zeros the fix bought.
8. **The above-DBL_MAX divergence quietly folded into a pass or a fail** instead of reported as
   its own line.
9. **Anything written into either GIMS checkout.** Both are read-only. Import the parser with
   bytecode writing disabled so no `__pycache__` lands in Evan's tree.
10. **Any real number quoted before the negative control has passed.** Ordering rule, below.
11. **The float-digit setting not proven to have actually changed** (correction C3). Positive
    control, below.
12. **`SQL_RAISE` reported as one undifferentiated class** (correction C4) — a named refusal and
    an unexplained raise scored together means the refusal line and the defect line are the same
    line, and neither can be read.

### 5.1 The negative control — required, and required FIRST

**A negative control is a deliberately broken input, used to prove the rig can report a failure at
all.** A rig that has only ever printed "pass" has not been shown capable of printing anything
else.

**This project has already made exactly this mistake once.** `proto/conformance.py` assigns
outcomes at four sites, all inside its per-case loop. A full normal run under a line tracer showed
**`DID_NOT_COMPILE` hits=0, `SQL_ERROR` hits=0, `COMPILED_DIVERGES` hits=0, `COMPILED_AGREES`
hits=130** (`RECHECK-2026-08-21.md` §2.3). Three of the four failure branches had never executed —
measured, not inferred. The 23 negative controls the harness shipped with never drove the per-case
loop at all. Every conformance headline in the record was produced by a rig whose failure branches
were dead surface, and it stayed that way until Evan explicitly asked for the check (Q4). When it
was finally driven, the branches worked — **dead, not broken** — but nobody knew that, and nobody
could have.

**And the instrument that was tested is not the instrument that matters.** `RECHECK-2026-08-21.md`
§5.1 records it verbatim: only `conformance.py` was covered, while
*"the instrument that produced every decision-relevant divergence has not itself been shown able to
fail"* — that is `differ.py`, and `differ.py` is where T-3's entire headline comes from.

**So, binding:**

- Before any real result is quoted, `differ.py` gets the same treatment `conformance.py` got:
  deliberately wrong compilations pushed through the **real** path, each declaring in advance which
  class it must land in. `proto/conformance_injection_test.py` is a working template — it swaps
  the compiler handle and asserts on the emitted outcome string without modifying the harness.
- The injections must provoke, at minimum, one of each: **class 1** (different value), **class 2**
  (value → null), **class 3** (null → value), **class 4** (`PY_RAISE`), a **named refusal**, and an
  **unexplained raise** — the last two being correction C4's split.
- **If any injection is scored as agreement, the run refuses to report anything.** Not a caveat in
  the write-up. No output.
- **Ordering rule: no real number may be quoted, in any document, until the control has passed.**
  A control run afterwards is a control that already knows the answer it needs.

### 5.2 The positive control — proof the setting actually took effect

Correction C3 means the run adds new code to switch `extra_float_digits`, in two instruments. If
that code silently fails, all three runs execute at setting 1 and print three identical passes that
look exactly like Q10 being satisfied. So, per setting, before the batteries:

1. Read the value back — `select current_setting('extra_float_digits')` — and record it in the
   output JSON alongside the input fingerprints.
2. **Show a value that actually differs**, e.g. `1/3` printing 16, 15 and 12 significant digits at
   `1`, `0` and `-3` respectively (`M_encoding_guc.txt` §M1). Two settings that print identically
   is a failed control, not a finding.
3. **Run the §5.1 negative control once per setting**, not once overall — it doubles as the check
   that the new plumbing is live on that path.

### 5.3 The input-domain gate — a zero over a domain that cannot fail is not a zero

The full requirement is `EXPERIMENTS.md` §1.3, which calls it "the single most important part of
the spec". It is restated here in bar form because §5 item 2 turns on it.

**The mistake it exists to prevent, from this project's own record.** `FINDINGS.md` §2.4 originally
reported **403 probes, 403 agreements** and drew confidence from it. Cross-cutting section A.3 then
showed the generator could not reach a single one of the eight ways the Python evaluator raises on
data — not by luck, by construction. The largest number anywhere in all 403 records was **9**; the
only `round` second arguments were **−1** and **2**; the token `%` occurred in **0 of 403** sources;
maximum container nesting was **4**. Zero failures over a domain that cannot fail is a measurement
of the generator, not of the compiler.

**Half one — the class-4 emptiness must be demonstrated, not assumed.** Under the subset, all eight
Python raise sites are excluded by construction (they need dates, `round`, `floor`/`ceil`, `%`, or
`==` over containers — all outside the seven permitted functions). So class 4 should be
*structurally* empty, and a printed zero would mean nothing on its own. Two checks are required:
mechanical confirmation that no generated expression contains any of those constructs, **and** an
attempt to compose infinity from permitted operations only (`1e200 * 1e200` is legal subset
arithmetic) with confirmation that nothing downstream raises. If something does, that is a ninth
raise mechanism nobody has catalogued, and it is a finding in its own right.

**Half two — the magnitudes must actually be reached, with a printed witness for each.** This is
where the measured in-subset failure lives, so a domain that stops short of it is a domain that
cannot fail. At minimum the generator must reach, and print a witness for:

| the domain must reach | why |
|---|---|
| the current guard boundary `1.79769313486231587e+296`, either side | the measured in-subset failure, before and after step zero |
| the real limit `1.7976931348623157e+308`, either side | where the guard is *supposed* to sit |
| infinity composed by permitted arithmetic (`1e200 * 1e200`) | half one |
| subnormals — `5e-324`, `1e-320` | `xpr.num` has an unguarded underflow that raises, and `xpr.truthy` returns true for `1e-400` where Python gives `0.0` and therefore false |
| the 2⁵³ integer-precision boundary — `2**53`, `2**53 + 2` | where JSON numbers stop being exactly representable |
| `0.0` and `-0.0` | sign-of-zero handling differs between engines more often than anyone expects |
| numeric strings that coerce — `" 7 "`, `"1e3"`, `"１２３"` | the tolerant-coercion class is the one `FINDINGS.md` §D.6 measured as *reached, repeatedly*, in real GIMS data |

**If the generator cannot reach a row, that row is reported as `untested` — explicitly, by name.**
Never as passed, and never silently absent from the table.

---

## 6. The binding constraints from Evan

These come from `ANSWERS-FROM-EVAN.md`. None is negotiable inside the run. Each is quoted, then
translated into what it does to the run.

| answer | his words | what it does to T-3 |
|---|---|---|
| **Q11** — indexes | *"Not acceptable — index work stays off"* | **No index help, anywhere, ever.** An **index** is a structure that lets Postgres jump to the rows it wants instead of reading all of them; Q11 rules them out for generated queries because they would require writing tenant-supplied field names into SQL text. For T-3 this means: no battery may create an index to make itself faster, no result may be conditioned on one existing, and the `IMMUTABLE`-plus-index split-brain hazard that `analysis/index-shape.md` §6.4 demonstrated is out of reach by construction. It also means the measured 3.79×–7.15× speed gap is now a **floor** — but that is T-4's problem, not this run's. |
| **Q10** — float digits | *"Make the correctness run test all three settings"* | **Everything runs three times and is reported three times.** A pooled pass rate is forbidden (§3). This is also why corrections C2 and C3 and the §5.2 positive control exist: two instruments pin the setting today, and only one of them is in the spec's work list. |
| **Q7** — instruments | *"Let them edit the existing code in place"* | `spikes/T-1/proto/` and `spikes/T-1/analysis/fuzz/` are **edited directly**. No rebuild from scratch, no parallel copy. This is what makes step zero — the 24-character guard fix — legal. Both GIMS checkouts stay read-only regardless. |
| **Q2** — the fixture | *"Not good enough — build a real one"* | **This run IS the acceptance test.** The 130-case fixture (`expr_vectors.json`) is GIMS's contract between its Python and JavaScript evaluators; Evan ruled it inadequate as an acceptance test for a third, SQL evaluator. It still runs here, as one input set among several, and it may never be presented as the bar. `FINDINGS.md` §5.10 predicts the temptation in as many words: *"the next seat will be tempted to reuse it, and it will pass."* |
| **Q4** — the rig | *"Yes — do that run before I rule"* | The negative control is his standing requirement, not a methodological flourish. §5.1 extends it to the instrument the first pass missed. |
| **Q1 / GA-3** — the ruling | *"Stands — don't build yet"*, with *"build the bounded SQL path with explicit fallback, instrument which path ran"* | T-3 exists to earn or refuse the build. The "explicit fallback, instrument which path ran" half is what makes a **reported refusal** the right shape for the surviving divergence — a caught, named error *is* that instrument; a null is not. |
| **Q15** — the target data | *"High-volume data GIMS does not have yet"* | Kills the "unreachable in practice" defence outright. Nobody has sampled the data autoSQL is aimed at. |
| **Q36 + shop config** — ceremony | *"Lightweight by default, full for the demo"*; `.autodev/shop.json` has `settings.lean: true` | **T-3 runs lean.** The full-ceremony carve-out is T-2, the demo. "Lean" is AutoDev's reduced-ceremony mode: fewer mandatory review seats per stage, same gates. |

**Confirmed since framing — 2026-08-22, GA-6** (Evan's wrap-up answers, logged verbatim in
`.autodev/events.jsonl` at `2026-08-22T17:35:37.208Z`, `scope_confirmed: true`):

- **Item 1 — GA-4's scope:** *"It covered everything I was asked."* All ~21 rulings taken
  under GA-4 stand, including every one this document derives from it (§2 C1, §11 R1).
- **Item 2 — the tick/note reading:** *"Right — tick is GIMS, note is the demo."* The
  "don't build yet" tick governs GIMS: **nothing enters GIMS until T-3 and T-4 pass.** The
  note describes the fake-data demo (T-2). T-3's verdict is one of the two that gate GIMS.
- **Item 7 — the loud refusal:** left unanswered, and its stated default is *"Stands."* The
  ruling behind §2 C1 and §11 R1 therefore survived its own dedicated wrap-up question.
- **Item 28 — the day's slate:** *"Correctness run + demo build."* T-3 runs now, sharing
  this machine with T-2's build; the T-4 timing run waits for a booked exclusive window (§8).

---

## 7. Out of scope

- **Speed, latency, throughput, row counts.** That is T-4 in full. T-3 records its own wall clock
  per battery — the record never timed these and the next run should be planned from a measurement
  rather than a guess — but it makes no performance claim and no performance decision.
- **The 16 constructs outside the subset**, and everything to do with dates, strings, `sum`,
  `avg`, `round`, `floor`, `ceil` and `%`. If the subset fails, widening it is not the response.
- **Fixing `compile.py` or the language.** T-3 measures and reports; it does not redesign. The one
  exception is step zero, the guard literal, which Q7 permits and `EXPERIMENTS.md` §1.4 requires.
- **The `IMMUTABLE` mis-declaration.** Four runtime functions (`ecma_num`, `f8`, `num`, `str`)
  promise Postgres that they always return the same answer for the same input, while actually
  reading `extra_float_digits` (`analysis/fuzz/L_misc.txt` §L5). Postgres believes the promise
  without checking it. **T-3 prices this; T-3 does not fix it.** Q11 has removed the index route by
  which it did visible damage, but the mis-declaration stands and the run says what it costs.
- **Indexes**, in any form (Q11).
- **The GIMS integration, the storage migration, the UI demo (T-2), the badge wording (Q16), the
  four GIMS issues (Q17).** Different tickets. The GIMS boundary is now Evan's own confirmed
  reading, not a session's **[GA-6 item 2, 2026-08-22]**: nothing enters GIMS until T-3 **and**
  T-4 pass.
- **Anything written to `GIMS-Project` or `GUTS/spine/L1-memory/gims-ledger`.** Read-only, both.
- **`.autodev/tickets/`, `.autodev/events.jsonl`, `tracker.mjs`.** Never touched by this work.
- **The 1,000-to-1,000,000-row corpus.** Dropped by Q31 and confirmed gone
  **[measured 2026-08-21: zero `measure_instances_*` tables in `autosql_spike`]** — and
  `autosql_spike` itself followed it later that day (commit `01e75b0`; re-verified
  2026-08-22: no such database on the container — §9). T-3 does not need the corpus and must
  not rebuild it; that is T-4's first task.

---

## 8. Stop rules — what makes this run halt rather than grind on

There is no clock in this factory, so the timebox is stated as scope with triggers. Hit one and the
run stops and writes what it has.

One calendar fact now bounds it from outside **[added 2026-08-22]**: GA-6 item 28 put T-3 on
today's slate alongside T-2's build — *"Correctness run + demo build"* — with the T-4 timing
run waiting on a booked exclusive window. A run that cannot finish inside that slate takes
soft stop 10 and goes to `sp-synth` with named gaps rather than holding the machine.

**Hard stops — the run halts immediately and reports; no further batteries:**

1. **A negative-control injection scores as agreement** (§5.1). Nothing may be reported. Fix the
   instrument, restart the control, then start over.
2. **The float-digit positive control fails** (§5.2) — the setting did not demonstrably change.
   Every number after that point is a number at setting 1 wearing another label.
3. **A subset-legal expression comes back `UNCOMPILABLE`** (§4.8). Either the generator leaked an
   out-of-subset construct or the subset is misdefined. Both invalidate everything already counted.
4. **Step zero does not close the eight** — the guard fix lands and the in-subset divergences from
   `A_f8_guard.txt` §A2 do not all go to zero. That is a second, uncatalogued cause and it is a
   bigger finding than anything else this run could produce. Stop and characterise it.
5. **The distinguishable refusal cannot be built** — `xpr.f8`/`xpr.num` cannot be made to raise
   identifiably, or the caller cannot catch and name it. Per `EXPERIMENTS.md` §1.2 this is not a
   design problem to solve; it is a **FAIL**, recorded plainly, and the run stops.

**Soft stops — the finding is written as it stands and not chased:**

6. **A wrong answer is found.** The bar is failed the moment any class 1–4 count is non-zero. The
   run continues **only to characterise that failure** — its cause, its class, a witness — and at
   the remaining settings, because Q10 requires all three reported. It **never** continues looking
   for a configuration in which the number comes out better.
7. **The generator cannot reach a magnitude class** the domain gate requires. Report that row as
   **untested**, explicitly. Do not redesign the generator to reach it, and do not report it as
   passed. A zero over a domain that cannot fail is a measurement of the generator, not of the
   compiler.
8. **A ninth Python raise site turns up** — something raises that `FINDINGS.md` §A.2's catalogue
   of eight does not name. Record it as a finding; do not chase its full blast radius.
9. **Scope creep into the other 16 constructs, into speed, or into fixing `compile.py`.** Note it
   and leave it.
10. **Out of room.** Write findings and go to `sp-synth` anyway. A partial matrix with honest,
    named gaps is a valid spike result; a stalled spike is not. What may **never** be partial is the
    negative control (§5.1) — a run without it has no result to be partial about.

---

## 9. Environment — verified 2026-08-21, re-verified 2026-08-22

First verified when framed **[measured 2026-08-21]**; every item re-checked live, read-only,
on **2026-08-22**. Two things changed after the first verification — the same day this
document was written — and one of them reverses a claim this section used to make.

- **Postgres:** docker container `glp-strong-db`, image `pgvector/pgvector:pg16`, up and healthy,
  host port **55433**. `select version()` → **PostgreSQL 16.14** (Debian 16.14-1.pgdg12+1).
  **[re-verified 2026-08-22]** — but read the next item before touching it.
- **CHANGED — that container is Evan's live database, and nothing in this run may point at
  it.** Since commit `01e75b0` (21 Aug, after framing) every spike script **fails closed**:
  no default connection string, and an outright refusal if `AUTOSQL_SPIKE_DSN` names port
  55433. `glp_strong` — Evan's real data, ~95 MB — lives there and is never touched.
- **CHANGED — the scratch database is gone, and the earlier claim "T-3 needs no database
  rebuild at all" is reversed.** `autosql_spike` (and the `xpr` schema with it) was dropped
  later on 21 Aug, executing Q31's "leave it gone" (same commit; zero active connections at
  the time). Re-verified 2026-08-22: the container's database list is `glp_strong`,
  `postgres` and the two templates — nothing else. T-3 brings up its **own throwaway
  container** and installs `proto/runtime.sql`; the completion check is a count of **21
  functions in the `xpr` schema** (`proto/REGENERATE-CORPUS.md` §4 — instructions verified
  end-to-end on a throwaway container before the database was dropped).
- **Disk: 96% full, 21 GB free [measured 2026-08-22].** Plenty for a runtime-only container
  (the dropped database was ~7.5 MB), but `REGENERATE-CORPUS.md` documents a teardown trap
  that strands a gigabyte on exactly this disk — tear the throwaway container down properly.
- **Instruments present [re-verified 2026-08-22]:** `spikes/T-1/proto/` (`conformance.py`,
  `compile.py`, `runtime.sql` — both guard literals re-counted, still 297 digits at `:33`
  and `:51` — `closure_subset_coverage.py`, `conformance_injection_test.py`, plus
  `REGENERATE-CORPUS.md`) and `spikes/T-1/analysis/fuzz/` (20 producer scripts, 25 output
  files, `run_all.sh` invoking 21 batteries). **Three outputs still have no producer** —
  `A_range.txt`, `A2_boundary.txt`, `B2_overflow.txt` are absent from `run_all.sh` and have
  no matching `.py`. Writing those three producers remains on the work list
  (`EXPERIMENTS.md` §1.4 item 5).
- **Python:** `GIMS-Project/.venv`, CPython **3.12.3** — the reference runtime, imported
  read-only. **[re-verified 2026-08-22]**
- **Both GIMS checkouts are read-only for this run.** Nothing is written to either — and
  wrap-up item 33 records that Evan's GIMS checkout carries his own uncommitted edits, one
  more reason no tool of this run may write there.

---

## 10. The risky part, for the next seat

T-1's framing said the conformance harness was the whole spike. T-3's version is sharper, and it is
the reason §5.1 is written the way it is:

> **T-3's headline is a count of zeros coming out of `differ.py` — and `differ.py` has never been
> shown able to print anything but a zero.**

Every ingredient of a false green light is already assembled and sitting on disk: an instrument
with untested failure paths, a language whose Python side is *total* (it never throws — it returns
`null`), a bar whose passing value is the same character an empty result prints, and a project
whose one previous rig turned out to have three dead failure branches that nobody noticed until
Evan asked.

Build so that **five outcomes stay visibly distinct end to end** — agrees · diverges (with its
class) · named refusal · unexplained raise · did-not-compile — never four, and never a pass column
plus an everything-else column. Then break it on purpose, in each of the five, before quoting a
single real number.

---

## 11. Rulings made in this document, and how to overturn them

Each was derived from Evan's recorded answers because he is AFK and cannot be asked. Each shows
its derivation. **Each is overturned by one line from him**, and the "cost to overturn" column is
what that line actually costs.

**Refreshed 2026-08-22:** the wrap-up pass put the highest-leverage of these back in front of
him, and the answers are in — §6's "Confirmed since framing" block. In particular R1 now
stands on **confirmed** authority (GA-6 fixed GA-4's scope wide, and wrap-up item 7 — R1's
own question — stood on its default), not on a derivation. The overturn column still holds:
any of these remains his to reverse with one line, at the stated cost.

| # | ruling | derived from | cost to overturn |
|---|---|---|---|
| **R1** | The ticket's "BLOCKED ON EVAN" line is **cleared**; the surviving above-DBL_MAX divergence is a **reported runtime refusal**, and the bar stays at zero (§2 C1, §4). | The `EXPERIMENTS.md` §1.2 ruling under **GA-4** (logged verbatim, `19:43:01.819Z`), itself derived from T-1 `FRAMING.md` §5 (*"reported, never silent"*) and Evan's Q1/GA-3 note (*"explicit fallback, instrument which path ran"*). **Confirmed 2026-08-22:** GA-6 item 1 fixed GA-4's scope wide (`scope_confirmed: true`), and wrap-up item 7 — this ruling's own question — stood on its default. **Settled.** | **Nothing re-runs.** Only the reporting changes. |
| **R2** | T-3 inherits T-1's **`risk: medium`** and **`decision_authority: recommend-and-wait`** — T-3 recommends, Evan decides at the `sp-decide` gate. | T-3's ticket carries neither field; T-1's carries both. T-3 was spawned by T-1's `sp-spawn` from Evan's own ruling, and Q1 (*"don't build yet"*) keeps the build decision with him. `spike@v2` has an `sp-decide` gate regardless. | **One line.** Recommending costs nothing to upgrade to deciding. |
| **R3** | T-3 runs **lean**. | `.autodev/shop.json` `settings.lean: true` + Q36 (*"Lightweight by default, full for the demo"*), and the demo is T-2, not T-3. | One line; changes ceremony, not measurements. |
| **R4** | The **negative control runs once per setting, and runs first** (§5.1, §5.2). | Q4 (*"do that run before I rule"*) + Q10 (three settings) + correction C3 — `differ.py:79` pins the setting, so a control that only ever ran at setting 1 proves nothing about the two new code paths. | One line. Running it three times and later deciding once was enough costs nothing; the reverse costs a full re-run. |
| **R5** | **All three settings run even if the first fails.** A fail at one setting does not cancel the other two. | Q10 requires each reported separately, and a setting that was not run cannot be reported. | One line. |
| **R6** | **`NULLNESS` is reported separately and does not fail the bar by itself**, unless the two null representations behave differently in a `WHERE`/`ORDER BY` — which the run tests rather than assumes (§4.8). | It is not a value↔null flip, which is what `FRAMING.md` §5 forbids by name; but `differ.py:97` calls it "a leak of the representation contract" and the filter path is where a leak drops rows. **Nothing in Evan's answers speaks to this**, so this is the cheapest-to-reverse option, chosen for that reason. | One line, **no re-run** — it is already a separate line in the output, so promoting it to a failure is a re-read of the same report. |
| **R7** | **`SQL_RAISE` is split** into *named refusal* and *unexplained raise* before any number is quoted (§2 C4). | GA-4's ruling makes a deliberate refusal an allowed outcome, while `differ.py:169`'s comment still calls every raise "highest severity". The instrument cannot serve the new bar unsplit. | One line — but overturning it means the refusal count and the defect count cannot be told apart, so it would have to be re-run. |
| **R8** | The **`IMMUTABLE` mis-declaration is priced, not fixed** (§7). | `EXPERIMENTS.md` §1.1 (*"Run 1 is where it gets priced"*) + T-1 `FRAMING.md` §3's stop-rule idiom: record cause, do not fix. | One line; fixing it is a separate, small piece of work. |

---

## 12. Words used above, glossed

Written because Evan asked for the database reasoning explained and the coding basics skipped (Q41).

**Spike** — research that answers a question rather than shipping a feature. Runs `sp-frame →
sp-investigate → sp-synth → sp-decide → sp-spawn`.

**Framing / `sp-frame`** — this stage. Sets the bar before any evidence exists, so the result
cannot be rationalised afterwards.

**Gate** — a point in the pipeline where something must be decided before work continues. `sp-decide`
is the one where Evan rules on this run.

**Lean** — AutoDev's reduced-ceremony mode: fewer mandatory review seats, same gates.

**Decision authority / `recommend-and-wait`** — the spike recommends; the human decides.

**Go-ahead (GA-*n*)** — a recorded line from Evan authorising a class of decisions, logged with a
timestamp and his verbatim words.

**Ruling on delegated authority** — a decision Evan handed to me under a go-ahead rather than made
himself. Always labelled as such, and always overturnable by one line from him.

**Battery** — one file of related test cases under `analysis/fuzz/`, each printing its own evidence.

**Fixture** — the 130 hand-authored expression cases GIMS ships (`expr_vectors.json`), the contract
between its Python and JavaScript evaluators. Q2 ruled it inadequate as the acceptance test for a
third, SQL evaluator.

**Negative control** — a deliberately broken input, used to prove the rig can report a failure at
all. **Positive control** — a deliberately *changed* input, used to prove a setting actually took
effect.

**Injection** — replacing one piece of the machinery (here, the compiler's output) with a known-wrong
version, so the rest of the real pipeline can be watched reacting to it.

**Inadmissible** — the run produced a number, but how it was produced means the number cannot decide
anything.

**Denominator** — what a count is *out of*. Refusals stay in it; that is what stops a refusal from
quietly becoming a pass.

**Witness** — one concrete case, printed in full, that demonstrates a claim. Counts without witnesses
are not evidence.

**`float8`** — Postgres's double-precision floating-point type. **DBL_MAX** — the largest value it
can hold, ≈1.7976931348623157e308. **Subnormal** — a number so close to zero that it loses precision;
`5e-324` is the smallest non-zero double.

**`jsonb`** — Postgres's binary JSON type. It can hold a number that `float8` cannot, which is the
entire root of §3's guard.

**SQLSTATE** — Postgres's five-character machine-readable error code. `22003` is "numeric value out
of range", used for both overflow and underflow.

**`extra_float_digits`** — the session setting controlling how many digits a float prints as. §1.

**`IMMUTABLE`** — a promise a SQL function's author makes to Postgres: same input, always same
output. Postgres trusts it without checking.

**Pushdown** — doing the filtering inside the database instead of pulling every row into Python and
filtering there. It is the whole point of autoSQL.

**Sequential scan** — Postgres reading every row in order because nothing lets it skip any. Under Q11
this is what every autoSQL query does, always.

**Total (of a function)** — it never throws. GIMS's Python evaluator is total: on bad input it returns
`null` rather than raising. SQL is not total, which is why the two engines can disagree about whether
a question even has an answer.
