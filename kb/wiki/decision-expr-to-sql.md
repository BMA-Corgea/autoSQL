# Decision — don't build the expression-to-SQL compiler yet; fund two experiments first

**Decided by:** `human:evan` · **Date:** 2026-08-21 · **Status:** SIGNED (one part open, §6)
**Ticket:** T-1, gate `sp_decide` cleared 2026-08-21, logged as go-ahead **GA-3** in `.autodev/events.jsonl`
**Decisions:** `ANSWERS-FROM-EVAN.md` (Q1; item 1 of the follow-up round) · **Evidence:**
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
  float conversion where it could matter. Evan ruled (Q10) that E1 tests **all three** settings.
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

The research set E2's bar as a *ratio* — beat the current path's 13.4–15.0 microseconds per row. Evan
rejected that framing. A path can be several times slower per row and still be the better product if
the wait a person actually experiences is acceptable — and the current path is answering the wrong
question anyway once it truncates. **E2 must be designed around a wall-clock target for a real widget
load, not a speed ratio.** That number is not set; he gave the direction, not the figure. Setting it is
a prerequisite to running E2.

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

Evan made the ruling conditional on two checks running first (Q4, Q5). Both ran, and **one removed an
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
restricted build instead, and is part of why §6 stays open.

## 6. The ambiguity — OPEN, not settled

He selected **"don't build yet; fund the two experiments"**. His note alongside says something else:

> "Continue. Build the bounded SQL path with explicit fallback, instrument which path ran, and run the
> dedicated subset acceptance tests before treating that subset as production-safe."

The selection points at *experiments first*; the note points at *start building the restricted
version*. **This session acts on the selection**, because the asymmetry favours it: E1 and E2 cost two
bounded runs and foreclose nothing, while building first risks shipping the silent-fallback failure
the spike exists to rule out. The note is treated as **the shape any eventual build must take** —
bounded subset, explicit fallback, instrumentation of which path ran, subset acceptance tests before
anything is called production-safe — and, per §3, as a re-specification of E2's bar. **One line from
Evan settles which he meant.** Until then this is open, and no build ticket should be opened on the
strength of the note alone.

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

1. Get the one line that closes **§6** — selection or note.
2. Set **E2's absolute wall-clock target** (§3); a proposal is being drafted for him to accept or change.
3. Spawn **E1 and E2 as tickets**, correctness first — bounded runs on instruments that already exist.
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
| Every decision quoted here, verbatim | `ANSWERS-FROM-EVAN.md` |
| The ruling as logged, in his words | `.autodev/events.jsonl` — go-ahead `GA-3`, 2026-08-21 |
| The evidence, and what the re-check moved | `spikes/T-1/RECHECK-2026-08-21.md` (§4 what changed, §5 what is still open) |
| The research distilled, and the full working | [`expr-ast-to-postgres-sql.md`](expr-ast-to-postgres-sql.md) → `spikes/T-1/FINDINGS.md` |
| The bar, set before any evidence was collected | `spikes/T-1/FRAMING.md` §4/§5 |
