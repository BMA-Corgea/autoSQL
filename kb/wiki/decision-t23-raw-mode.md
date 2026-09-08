# Decision — raw-mode divergence: what to do about equality on exact data

**Status: OPEN for the parts that need him. This is the packet, not the ruling.**
Evidence: `spikes/T-23/FINDINGS.md` · battery `spikes/T-23/raw_battery.py` · commit `e1f440b`.

---

## What was found

**The correctness claim is scoped, not wrong.** *"Zero wrong numbers over 11,367 expressions"*
holds — for **`py`-mode data only**. In `raw` mode the two engines disagree.

**7 divergences in 204 expressions.** Every one is an equality or an inequality; **no arithmetic
diverges.**

| expression | `a` | Python | SQL |
|---|---|---|---|
| `$.a == 0.1` | `0.1000000000000000000000001` | True | **False** |
| `$.a == 0.1` | `0.1000000000000000055511151231257827` | True | **False** |
| `$.a == 1` | `0.99999999999999999` | True | **False** |

*(plus the matching `!=` and `$.a == $.b` forms — seven in total)*

**The second value is the exact decimal expansion of the double `0.1`** — what an ETL job
produces when it serialises a float at full precision.

### The mechanism, measured

```sql
SELECT '0.1000000000000000000000001'::jsonb = '0.1'::jsonb;                    -- false
SELECT xpr.f8('0.1000000000000000000000001'::jsonb) = xpr.f8('0.1'::jsonb);    -- true
```

Arithmetic routes through `xpr.num` / `xpr.f8` and lands on the same `float8` Python uses.
**Equality compares the jsonb values directly**, where jsonb holds an exact `numeric`. Two
comparison domains, on inputs whose difference lives below a double's resolution.

## THE NUMBER IS NOT A RATE, and must never be quoted as one

**7 in 204 is a count over a hand-picked adversarial set** — 17 expression shapes over 12 JSON
numbers chosen *because* a double cannot hold them. It is **not** a frequency, and **no frequency
estimate exists**. What has been established is that the class is **non-empty and reachable**;
nothing here says how often it fires on real data, and nothing here supports an estimate.

This is stated at this length because the project has already shipped a figure whose name
described something other than what was measured.

## What this is, and is not

- **Not a regression.** T-6's fix stands; its numbers are sound for what they measured.
- **A blind spot in the battery**, not a sampling shortfall. `py` mode cannot express these
  inputs, so a larger `py` run — 100,000 expressions, a million — would never find them. **The
  gap is domain, not sample size.**
- **Pointed at real data.** `differ.py` calls `raw` *"the shape of any row written by something
  that is not this Python process"*, and T-7 found **six of seven GIMS write paths never check
  the declared type.**

---

## The open question — DEFERRED, with a trigger, and deliberately not filed as work

**Should equality route through `xpr.f8` the way arithmetic does?**

It would close all seven divergences. **It would also change what equality means on exact data:**
two jsonb values that genuinely differ would begin comparing equal whenever their difference
falls below a double's resolution. That is a real semantic change with its own consequences, and
it is a design decision, not a defect fix.

**This has deliberately NOT been filed as a ticket.** Filing it would be building on a foundation
that has not been ruled on:

> **The trigger is his T-4 ruling.** T-4's verdict is a **kill** — the compiled path is ~2.5×
> slower than the Python path at every size and misses every pre-registered bar. **If that kill
> stands, this question never arises**, because nothing ships the compiled equality path at all.
> It becomes live only if T-4 is ruled to continue in some form.

Recorded here so that it is in front of him when he rules on T-4, rather than sitting in a
backlog as work nobody authorised.

## Recommendation

**Three things, none of which need him today:**

1. **The scope statement stays where the claim is made.** Done — `README.md` now says what the
   11,367 figure covers and what it does not, rather than leaving it to a findings file nobody
   reads first.
2. **No fix, no ticket, no estimate.** See the deferral above.
3. **If T-4 is ever revived,** this question is a prerequisite to the design, not a follow-up to
   it — the equality semantics decide what the compiled path can promise.

---

## ADR — the decision taken, 2026-09-08

**Decided by:** an agent on the owner's recorded authority (GA-31; the true actor is in the
ledger, which is not public). **T-4's `sp_decide` is excluded from that authority and remains
his**; this ADR does not touch it.

**Context.** The project's headline correctness figure was measured on one of two ingestion
modes. The other mode is reachable, is what non-Python writers produce, and diverges.

**Decision.**

1. **Scope the claim where it is made.** `README.md` states what the 11,367 figure covers and
   what it does not. *Taken and shipped.*
2. **Do not fix the divergence.** Routing equality through `xpr.f8` is a semantic change, not a
   defect repair.
3. **Do not file it as work.** Deferred with a trigger: **his T-4 ruling.** If T-4's kill stands,
   nothing ships the compiled equality path and the question never arises.
4. **Publish no frequency.** The count is over an adversarial set; no rate exists.

**Consequences.**

- The correctness claim is narrower than it read, and now says so. Anyone relying on it for
  non-Python-written data has been told the limit.
- If T-4 is revived, the equality semantics are a **prerequisite** to that design, not a
  follow-up — they decide what the compiled path can promise.
- The battery is re-runnable, so the question can be re-measured against any future runtime
  without re-deriving the setup.

**Alternatives rejected.**

- *Route equality through `xpr.f8` now.* Closes all seven, and silently makes genuinely different
  values compare equal. Not a fix a spike gets to make.
- *File a ticket.* Builds on a foundation not yet ruled on, and manufactures work that a kill
  verdict would make void.
- *Report the count as a rate.* The denominator was chosen adversarially; the figure would
  describe something other than what was measured, which is the exact defect shape this project
  keeps finding.
