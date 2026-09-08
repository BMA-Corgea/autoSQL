# Decision — T-4's timing verdict: the compiled path is 2.5× slower, and what to do about it

**Status: OPEN. This is the packet for `sp_decide`, not the ruling.** `sp_decide` is the
owner's under GA-24 Q2 and is parked for his hand — it is the decision this repo exists to
produce, and a clean result is not the same as a delegated one.

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
