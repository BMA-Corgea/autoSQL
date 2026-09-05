# T-7 · Framing — which write path stores rows that skip the schema type check?

Stage: `sp-frame` (spike@v2) · **lean OFF**, risk low · Framed: **2026-09-01** ·
Authority: GA-15 (*"Loop until everything is closed"*), lifting the owner's Q6 park
(*"log it as a ticket, do not chase now"*)

**READ-ONLY.** Every database opened `mode=ro&immutable=1`; both GIMS checkouts read, never written.

## The question

> **`Glove.size` is declared `type: float` and holds `'lmao im a changling'`. Which write path put
> it there — and what does that mean for anything autoSQL wants to assume about declared types?**

## Why it is worth an hour

Not for the nine junk rows. **For the assumption.** T-1's `f3` §3.6 (hazard H3) turns on building
per-path expression indexes typed by the schema's declared type. If a declared type is not a
guarantee about stored content, that design inherits an assumption that does not hold — and it
fails as a `CREATE INDEX` error on real data, in production, not in a test.

## The bar — deliberately low, and stated so it cannot creep

This is an hour of reading, not a project. It passes if it produces **either**:

- **(a)** the specific write path, named with file and line, **or**
- **(b)** a statement of why the specific path **cannot** be determined, with the evidence that was
  looked at — *plus*, in either case, the answer to the question that actually matters: **is a
  declared type a guarantee, or not?**

**(b) is a pass, not a failure.** Nine rows written in August 2025 by an unknown hand may simply not
be attributable, and an hour spent proving that is an hour well spent if it stops the next person
looking. What would **not** be a pass is guessing at a path and asserting it.

## What is out of scope

- **Fixing anything.** Not the rows, not the write paths, not GIMS. The owner's Q3 park stands: nothing
  under either GIMS checkout is modified.
- **Deleting or repairing the nine rows.** They are somebody's data, junk or not.
- **A full audit of GIMS's write surface.** Only the paths that reach `put_record`.

## Stop conditions

1. Any write to either GIMS checkout — stop, report.
2. The hour is up — report (b) with what was covered.
3. The answer turns out to matter more than expected (e.g. a path that bypasses validation is on a
   *user-facing* route) — that is a finding to surface, not to quietly fix.
