# Decision — T-4's timing verdict: the compiled path is 2.5× slower, and what to do about it

**Status: RULED — C, "test a faster design first".** The owner ruled on the decision form
`autosql-foreman-2026-09-26` (submitted 2026-09-27 03:50 UTC), recorded in the ledger as
**GA-34**. `sp_decide` was cleared on that authority on 2026-10-01. The packet below is kept
exactly as he ruled on it; **the ADR is the last section.**

**Evidence:** `spikes/T-4/FINDINGS-T4.md` at `1b78aef` · measurements and negative control
in `.autodev/evidence/T-4/`.

---

## What was measured, in one paragraph

On a quiet, exclusive host, with the instrument proved before use (§6.1 negative control
12/12), the shippable compiled path (**arm C**) misses every bar that was set in advance
and fails §4.2's kill condition: **413.76 ms against a 350 ms bar** at 20,000 rows, and
**2,004.61 ms against 1,000 ms** at 100,000 — where it is **2.56× slower than the Python
path it would replace**. The ratio is **flat at 2.09× / 2.56× / 2.55×** across a 50-fold
range of row counts, so there is no size at which it crosses over. This is *better* than
T-1's recorded 3.79×–7.15×, and it still loses.

**The widget is invented** (§7.2) and every figure above belongs to it.

---

## What the numbers rule out, and what they do not

**Ruled out by measurement: tuning.** A flat 2.5× is not a constant overhead that a faster
scan or a bigger cache erodes; it is a per-row cost of ~20 µs that does not move with size.
Arm C's own split shows where it lives: **1,971.92 of its 2,004.61 ms at 100,000 rows is
SQL**, and the Python sort-and-limit tail the shippable shape keeps out of SQL costs
**5.36 ms**. There is nothing to reclaim at the edges.

**Not ruled out: a different way of doing the same work.** The same predicate, over the same
rows, through native Postgres operators (**arm B4**) costs **28.43 ms at 100,000** — against
a **1,000 ms bar**. That is **35× of headroom**, and the gap between B4 and arm C is
**45×–70×**. B4 is *not* a candidate as it stands: `::numeric` raises on a malformed value
where the language must return null, which is the entire reason the `xpr` runtime exists.
**But the cost being measured is null-safety, not SQL, and 35× of headroom is a lot of room
to buy it in.**

---

## The options

| | option | what it costs | what it buys |
|---|---|---|---|
| **A** | **Kill the compiled-SQL path.** The bar was pre-registered, it failed at every size in the favourable direction, and the ratio is flat. | The correctness problem stays unsolved: today's answer is **26% recall at 100,000 rows and 8% at 1,000,000** — 37 of 50 displayed rows do not belong, and neither does the top one. | Closes a design honestly and cheaply. Nothing further is spent on it. |
| **B** | **Ship it anyway: slower but right.** Accept 2.5× on the explicit ground that users currently get wrong answers quickly. | A dashboard widget that takes ~2 s instead of ~0.8 s at 100,000 rows, and ~21 s at 1,000,000. | Correct answers. This is the only option that fixes the defect *now*. |
| **C** | **Redesign around the measured cost** — a native-operator path with explicit null guards, sitting between B4's 28 ms and arm C's 2,005 ms. | A new spike. The null-safety that `xpr` provides per-row in plpgsql has to be expressed inline instead, and *that* is the open question, not the arithmetic. | Correctness *and* latency, if it lands anywhere under ~10× B4. |
| **D** | **Spend a second exclusive window** completing the 1,000,000-row row of the table. | ~50 minutes of exclusive host. | Completeness of the record only. **It cannot change the verdict** — §4.5 makes the clean FAIL at 100,000 decisive on its own. |

---

## Recommendation

**C, with B as the interim — and explicitly not D.**

**Why C.** It is the only option the evidence actually points at. The run did not merely
establish that the compiled path is slow; it localised the cost to the `xpr` runtime by
measuring the identical predicate through native operators on the same rows in the same
session. **B4 clears the 100,000-row bar with 35× to spare.** Even a null-guarded native
path costing ten times B4 lands near **284 ms**, inside a 1,000 ms bar. That is a real
target with a measured basis, not an optimistic one.

**Why B in the meantime.** A is clean but leaves a widget that is confidently wrong at
scale, and wrongness is the more expensive failure: a slow dashboard is annoying, a
dashboard whose top row does not belong is misleading. If C is not funded, **B is better
than A** on those grounds — but that is a product judgement about which failure the owner
prefers, which is exactly why it is his and not ours.

**Why not D.** It buys a table cell, not an answer, and it costs the scarcest resource this
project has: an exclusive machine.

**The honest caveat on C.** Nobody has yet shown that null-safety *can* be expressed in
native operators without per-row function calls. If it cannot, C collapses into A or B. The
recommendation is to spend a small timeboxed spike finding out — not to assume it works.

---

## What would overturn this

- A widget the owner actually uses, if its shape differs materially from the invented one
  (§7.2 says it substitutes directly and nothing else changes).
- A ruling that the 20,000-row bar is the only one that matters, since that is where the
  Python path is already exactly right and the gap is smallest (2.09×).
- Evidence that the 1,000,000-row size is not a real use case, which would remove the
  binding bar and leave only 100,000 — where the miss is still 2.0× on the absolute bar.

---

## ADR — the ruling, recorded 2026-10-01 at `sp-decide`

**Decided by:** the owner, on the decision form `autosql-foreman-2026-09-26` (submitted
2026-09-27 03:50 UTC, 7 of 7 questions answered, no notes), recorded in the ledger as
**GA-34**. **Recorded by:** an agent on that authority. The true actor is in the ledger,
which is not public.

**Context.** T-4 measured the compiled path at about 2.5× slower than Python at every
size, and it failed a bar fixed before the run. The cost sits in the per-row runtime
functions. Native operators (B4) answered the same predicate in 28 ms at 100,000 rows,
against 2,005 ms for arm C. But native operators raise an error on a malformed value,
where the language must return a blank.

### Decision

**C — test a faster design first.** In the form's own words: *"write the safety checks
inline instead of as per-row functions, and confirm it still gives zero wrong numbers. The
pass bar is written down before it runs."*

1. **The compiled path is neither closed (A) nor shipped as measured (B).**
2. **A child spike tests a faster design**, filed at `sp-spawn`. It covers two levers,
   cheapest first. (a) Mark the runtime functions that are genuinely safe for parallel
   query. None is marked today, so Postgres ran arm C in one process while plain SQL used
   two workers. (b) Write the number checks inline, in place of per-row `xpr.num` calls.
3. **The pass bar is fixed in the child's framing before anything runs.** The target the
   owner saw when he ruled: **under ~0.3 s at 100,000 rows**. The rule he set on 5 Sep
   still stands: **it must beat Python**, measured in the same session.
4. **Who rules the child's verdict (GA-34 Q2 = A).** A *clear* pass against that bar is
   cleared on the owner's behalf, and it moves to building the shipping change. A fail or
   a near-miss goes back to him as A or B, "with the answer in hand".

### Consequences

- **T-4's FAIL stands as a measurement.** Nobody re-litigates it, and the child does not
  re-run T-4.
- **The corpus teardown is held.** `autosql-corpus` stays until the child has re-timed
  against it. This overrides the 2026-09-09 trigger, under which this ruling would have
  fired it. After the child's verdict, the teardown is a question for the owner.
- **T-4 timed the frozen spike compiler, not the shipping one.** This was found while
  writing this record. Every T-4 measurement file fingerprints
  `spikes/T-1/proto/compile.py` (`b71b1538…`) and `spikes/T-1/proto/runtime.sql`
  (`1c58d548…`). The shipping compiler (`compiler/compile.py`, promoted by T-11) differs
  in one deliberate way. Every number it returns goes through `xpr.j(...)`, a SQL function
  that carries its own `SET extra_float_digits = 1` (T-9). A function with a `SET` clause
  cannot be inlined, so the shipping path makes more per-row calls than arm C did.
  **The shipping path's latency has never been measured.** The verdict is unaffected,
  because a slower shipping path fails by more. But the child's baseline must be the
  shipping compiler and runtime, timed in the child's own session. Those have also never
  been through the correctness batteries: `differ.py` imports the frozen spike compiler.
  The child runs the batteries on the shipping pair first, so that any later divergence
  can be traced to the lever that caused it.
- **T-23's deferred question is not a prerequisite of the child, but it is one of any
  shipping change.** T-23 asked whether `==` should route through `xpr.f8`, and named this
  ruling as its trigger (`decision-t23-raw-mode.md`). Ruling C keeps the compiled path
  alive only on a condition. The child leaves equality untouched by design: it changes
  only how a value becomes a number and how two numbers are ordered. So the question stays
  deferred through the child. If the child passes, it becomes a prerequisite of the
  shipping change, and it is recorded there.
- **GIMS is not changed by this ruling.** A later go-ahead, GA-35 (2026-10-01), replaced
  GA-34 Q4 ("stop before GIMS") and Q7 (the budget park) for the overnight run. It does
  not change this ruling.

### Alternatives rejected, by the owner, on the form

- **A — close the SQL path.** Dashboards stay fast, and they stay wrong above 20,000
  records.
- **B — ship the slow-but-right path.** It overrides the "must beat Python" rule from 5 Sep.
- **D — re-run the missing 1M size.** About 50 minutes of exclusive machine time to fill
  one table cell. It cannot change the verdict.
