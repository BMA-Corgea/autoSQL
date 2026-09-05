# Decision — don't build the expression-to-SQL compiler yet; fund two experiments first

**Decided by:** `human:owner` · **Date:** 2026-08-21 · **Status:** SIGNED · both open parts closed
2026-08-21 by **rulings on delegated authority** (§3's number, §6's ambiguity) — his delegation, not his
decisions; either is overturnable in one line
**Ticket:** T-1, gate `sp_decide` cleared 2026-08-21, logged as go-ahead **GA-3** in `.autodev/events.jsonl`
**Decisions:** `kb/notes/owner-answers.md` (Q1; item 1 of the follow-up round) · **Evidence:**
`spikes/T-1/RECHECK-2026-08-21.md`, distilled in [`expr-ast-to-postgres-sql.md`](expr-ast-to-postgres-sql.md)

The research recommends; this records what was decided.

## 1. The question

GIMS builds a dashboard widget by reading records out of storage into Python and reshaping them there
— deriving fields, filtering, sorting, cutting to a limit. Because that happens *after* the data is
pulled out, GIMS refuses to pull more than `MAX_SCAN = 20 000` records and flags the answer
`truncated`. T-1 asked whether the small expression language those widgets use — in its parsed form an
**AST**, the tree a parser turns `price * 1.2` into — could be translated into Postgres SQL, so the
database does that work and only the finished answer comes back. Go/no-go was asked about **one
shape**: a standalone compiler in this repo plus a thin adapter inside GIMS to call it. That shape, not
the general idea of generating SQL, was on the table.

## 2. The decision

**Do not build the standalone-compiler-plus-thin-adapter architecture as scoped, yet.** Fund two
follow-up runs and let a build be *earned* from their results:

- **The correctness battery** (**E1** in the research). Take the restricted set of constructs the
  compiler could plausibly handle — 32 of 48 — generate every expression shape inside it, run each
  both ways, require agreement. The bar is absolute: **zero** cases where SQL returns a different
  value from Python, zero where a value becomes NULL or a NULL becomes a value, zero where Python
  raises but SQL quietly returns something. It also closes a loose end: the whole 130-case run pinned
  one Postgres output setting (`extra_float_digits = 1`), and 68 of the 130 pass a number through a
  float conversion where it could matter. The owner ruled (Q10) that E1 tests **all three** settings.
- **The like-for-like speed run** (**E2**). The spike never compared the two paths on equal footing —
  same widget, same table, same corpus. E2 does, at 20 000 / 100 000 / 1 000 000 rows. See §3: he
  changed how its bar is set.

**Order and money:** both runs, **correctness first** (Q6, re-confirmed as item 6 of the follow-up
round, resolving a conflict with an earlier answer); no spending cap on the speed run (Q9). The runs
may edit the spike's throwaway code in place rather than rebuilding it (Q7). The existing 130-case
fixture is explicitly **not** accepted as the acceptance test for a third implementation of this
language (Q2) — E1 has to build a real one.

**What this is not.** Not "the translation is impossible": it was demonstrated, 130 of 130 fixture
cases agreeing with a maximum SQL-versus-Python difference of exactly **0.0**. Not "throw the work
away". It is: *this evidence does not fund this build.*

## 3. His caveat, verbatim — it changes E2's design

> **"Benchmark absolute user-facing latency rather than treating a 3.79×–7.15× relative slowdown as
> intrinsically fatal."**

The research set E2's bar as a *ratio* — beat the current path's 13.4–15.0 microseconds per row. The owner
rejected that framing. A path can be several times slower per row and still be the better product if
the wait a person actually experiences is acceptable — and the current path is answering the wrong
question anyway once it truncates. **E2 must be designed around a wall-clock target for a real widget
load, not a speed ratio.**

He gave the direction, not the figure. **The figure was set on 2026-08-21 as a ruling on delegated
authority** (GA-4, quoted in §6) — **not one bar but three, one per collection size**, because what a
person will wait for depends on how big a question they asked: **350 ms at 20 000 rows, 1 000 ms at
100 000, 5 500 ms at 1 000 000**, plus a kill condition that the compiled path must beat the
in-memory path measured in the same session. Every number and its derivation is in
`spikes/T-1/EXPERIMENTS.md` §2.2. Run 2 reports the milliseconds either way, so he can redraw any
line afterwards without re-running anything.

## 4. Why — the three facts it turns on

**1. A fallback would be silent, and the spike forbade that in advance.** Not every expression
compiles; the honest design compiles what it can, evaluates the rest in Python, and *says* which
happened. It cannot. The GIMS function returning a widget's data, `resolve()` at
`GIMS-Project/api/dashboard/sources.py:357`, returns exactly `{records, count, truncated}` — **no
field** for "ran in the database" or "fell back" — and fallbacks reported today = **0**. That is a
live fact about GIMS's code, and no compiler work reaches it.

**2. The compiled path is slower everywhere, and the gap widens.** Across six table sizes from 1 000
to 1 000 000 rows it ran **3.79× to 7.15× slower** than today's path, with **no crossover** — it never
wins at any size. At a million rows: **59 590 ms against 8 331 ms**. The usual cure for a slow query is
an **index**, a lookup structure letting Postgres jump straight to matching rows instead of reading
the whole table. §7 explains why that cure is permanently unavailable here.

**3. Half the ways the two could disagree cannot be caught at all.** Of 33 distinct divergence classes
between the Python evaluator and the SQL translation, **18 are undetectable at query time by any
mechanism** — no runtime check would notice, so a wrong number comes back looking like a right one.
The restricted subset E1 would certify covers only **68 of 130** fixture cases (52.3%), refusing the
other **62** (47.7%), and its residual risk is measured non-empty: 8 of 16 paths that diverge at
extreme values sit *inside* the subset, one returning SQL `1` where Python returns `1e+300` — a
silently wrong number, the stated disqualifier.

## 5. What the re-check changed — the argument this decision lost

The owner made the ruling conditional on two checks running first (Q4, Q5). Both ran, and **one removed an
argument the write-up had been using to support the very ruling recorded here.** That is stated
plainly rather than quietly dropped.

The conformance harness compares each case's Python answer against its Postgres answer. Nobody had
ever seen it report a *failure*: a line tracer over a full run measured **0 executions** of every
branch that reports one. The write-up (`FINDINGS.md:5251`, closure log → *What the repairs did to
the argument*) used that to call one leg of its case
"firmer" — 130/130 scored by a rig whose failure paths had "never been emitted, only inferred". The
re-check drove the rig with six deliberately wrong compilations; it reported all six correctly, and
put the case that failed to compile in the **denominator** (`Pass rate = 125/130 = 96.2%`) rather than
scoring 130/130 again. **Those branches were dead, not broken. That argument is spent and must not be
used again.**

The honest reading: **130/130 got stronger, not this decision weaker** — it was never what the
decision rested on, it is the fact *for* building that the decision must account for. §4's three facts
were untouched, and the one result that would have overturned the ruling (the rig scoring "did not
compile" as a pass, voiding every conformance number) is exactly the one the pass did not get.

Two further findings concern the write-up's account of itself, not its conclusions: a reviewing pass
died mid-run and `FINDINGS.md` never says so, leaving 6 corrections unapplied, 2 still wrong in the
published text; and a `+463%` figure cited 11 times rests on one measurement whose producing script
did not survive — struck, the claim prices at **+2.2%**. That second one is a real argument for the
restricted build instead — the build shape §6 now routes into the demo rather than into GIMS.

## 6. The ambiguity — RESOLVED 2026-08-21, on delegated authority

**Status: closed.** This is a **ruling on delegated authority** — a decision *I* made because the owner
handed me the decision, not one he made himself. It is labelled that way deliberately, and he can
overturn it in one line (end of this section).

### What was ambiguous, kept as history

He selected **"don't build yet; fund the two experiments"**. His note alongside read as the opposite:

> "Continue. Build the bounded SQL path with explicit fallback, instrument which path ran, and run the
> dedicated subset acceptance tests before treating that subset as production-safe."

The selection points at *experiments first*; the note points at *start building the restricted
version*. Until 2026-08-21 this section recorded that conflict as OPEN, acted on the selection, and
said one line from him would settle it.

### The authority this ruling rests on

Logged as **GA-4** in `.autodev/events.jsonl`, 2026-08-21T19:43:01Z, verbatim:

> "I feel like these questions can be answered with your best judgement. I give them to you to fulfill
> what I had said in the form. I approve the spec for T-2"

That authorises a *reading of his intent*. It does not authorise a preference of mine, so the ruling
below is derived from his own recorded answers and shows its working. **One caveat on the record:**
GA-4 is logged against ticket T-2, and its wording covers the open questions put to him generally.
This ruling treats it as covering T-1's ambiguity too, because the ambiguity was one of those open
questions. If he meant it narrowly, this section reverts to OPEN and nothing else changes.

### The ruling

**The tick and the note are not in conflict. They are about two different pieces of work.**

- **The tick governs the GIMS integration.** No build work against GIMS — no compiler wired into
  `resolve()`, no change to what a widget returns, no storage migration — until Run 1 (correctness)
  and Run 2 (timing) have earned it. His own first clause in the same note says so in the same
  breath: *"Do not ship the prototype as a universal replacement for Python."*
- **The note describes work already authorised elsewhere: the demo.** "The bounded SQL path with
  explicit fallback, instrument which path ran" **is T-2**, the fake-data UI demo. He green-lit it
  himself (Q18), told it to reuse the throwaway generator (Q19), and required the side-by-side
  Python answer (Q24) that makes any divergence visible rather than silent.
- **"Acceptance tests before production-safe" is the gate on integration, not on the demo.** The demo
  runs on invented data with both answers on screen. Nothing there is production-safe and nothing
  claims to be. Run 1 *is* the acceptance test, and it stands between the demo and GIMS.

Read that way, nothing he wrote is contradictory. The note describes the demo; the tick describes the
integration.

### The derivation — why this reading and not another

| his answer | what it fixes |
|---|---|
| **Q18** "Green light, but only the safe operations" | he had already released the demo *before* the note — so "Continue" has an authorised home that is not GIMS |
| **Q19** "Reuse the throwaway program as-is" | he has already agreed SQL-generating code may run inside the demo |
| **Q24** "Both answers side by side on screen" | the instrumentation the note asks for — *which path ran, and did it agree* — is already specified, for the demo |
| **Q3** "Yes, but only after the demo" | GIMS's contract may not change until the demo is seen. He set that ordering himself, independently of the tick |
| **Q6 / follow-up item 6** "Right — both, correctness first" | he funded both runs in the *same* message as the note, so the note cannot mean "skip the runs" |
| **GA-3's own first clause** "Do not ship the prototype as a universal replacement for Python" | the note is itself a restriction on shipping — which is what the tick restricts |
| **Q1 tick** "Don't build yet" | what is left for the tick to govern is exactly the GIMS-integration build |

The two rival readings each kill one of his own answers. Reading the note as *start the GIMS build*
contradicts Q3 and Q6. Reading the tick as *stop everything* contradicts Q18. **This reading leaves
every recorded answer standing**, which is the test a delegated reading has to pass.

### What it permits and forbids, concretely

| may proceed now | still gated behind the two runs |
|---|---|
| T-2's fake-data demo end to end, including its SQL-generating layer (Q18, Q19) | any compiler code written into either GIMS checkout |
| the bounded subset compiler **as demo code**, with the fallback reported on screen (Q24) | adding the fallback-reporting fields `resolve()` lacks (§4, and Q3 — after the demo) |
| Run 1 (correctness) then Run 2 (timing), in that order (Q6) | the storage migration into GIMS's `instances` table (Q14) |
| — | calling any subset "production-safe" before Run 1 passes |

**The demo's SQL layer is demo code.** It is not a build against GIMS, it may not be promoted into one
on its own strength, and §8 keeps the standing obligation to re-read it against this decision.

### How he overturns this, in one line

*"The note meant start the GIMS build"* re-opens the tick. *"The tick meant stop the demo too"* halts
T-2. Either costs one line and re-runs nothing.

## 7. Standing constraints his other answers create

- **No database indexes, ever (Q11).** He rejected writing tenant-supplied field names straight into
  SQL text, and index work goes with it. Every generated query is a full table read by construction.
  **§4's 3.79×–7.15× gap is therefore a floor, not a starting point** — the one route by which the
  compiled path could have got faster is closed.
- **All three widget source types are in scope (Q13)** — the largest option offered, including a
  separate SQL path into the hand-written verb-log query, which has no shared storage layer to attach a
  filter to at all.
- **autoSQL owns the storage migration, as a prerequisite (Q14).** Moving records into GIMS's shared
  `instances` table is autoSQL's job and comes first. Weigh against the measured figure: that
  migration changes today's Python answer on **4 166 of 17 345 real rows**.
- **The target is high-volume data GIMS does not hold yet (Q15).** No GIMS collection observed today
  reaches the 20 000-row cap, so near-term value is **completeness of answers, not speed**. That
  reframes the performance leg; it does not dissolve it.
- **GIMS contract changes come after the demo (Q3).** `resolve()` may grow the fallback-reporting
  field §4 says it lacks — but only once T-2's fake-data UI demo has been seen working.

## 8. What happens next

1. ~~Get the one line that closes §6~~ — **closed 2026-08-21** by the ruling in §6. The owner may still
   overturn it in one line; until he does, the demo proceeds and GIMS stays untouched.
2. ~~Set E2's absolute wall-clock target~~ — **set 2026-08-21** by the ruling in `EXPERIMENTS.md` §2.2,
   summarised in §3. Three bars, one per collection size, plus a kill condition.
3. Spawn **E1 and E2 as tickets**, correctness first — bounded runs on instruments that already exist.
   E1 carries one further ruling of its own (`EXPERIMENTS.md` §1.2): the above-DBL_MAX divergence
   becomes a **reported runtime refusal** — the SQL refuses loudly instead of returning a number — so
   the pass bar stays at zero wrong answers.
4. **T-2, the fake-data UI demo, proceeds independently** (Q3 puts it ahead of any GIMS contract
   change). Its SQL-generation layer is still governed by this decision and must be re-read against it.
5. **Flagged, unfunded** (`RECHECK-2026-08-21.md` §5.1): Q4 asked whether "the test rig" can report a
   failure, and only the conformance harness was tested. `differ.py` — the instrument that produced
   *every* decision-relevant divergence — and `bench.py` still have no such check.
6. **`FINDINGS.md`'s two published errors get fixed and the document re-fingerprinted** (follow-up
   round, item 2).

## 9. Sources

| For | Read |
| --- | --- |
| Every decision quoted here, verbatim | `kb/notes/owner-answers.md` |
| The ruling as logged, in his words | `.autodev/events.jsonl` — go-ahead `GA-3`, 2026-08-21 |
| The evidence, and what the re-check moved | `spikes/T-1/RECHECK-2026-08-21.md` (§4 what changed, §5 what is still open) |
| The research distilled, and the full working | [`expr-ast-to-postgres-sql.md`](expr-ast-to-postgres-sql.md) → `spikes/T-1/FINDINGS.md` |
| The bar, set before any evidence was collected | `spikes/T-1/FRAMING.md` §4/§5 |
