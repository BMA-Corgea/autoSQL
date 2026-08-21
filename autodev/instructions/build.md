# build — autoSQL

## What this repo is

autoSQL is a **greenfield** repo that generates SQL: you pick the data, the
window, and the transformation in a UI, and autoSQL writes the query underneath.
It exists to fix one specific flaw in GIMS — GIMS currently pulls rows OUT of
the database and transforms them in a templated Python script, which is too slow
for heartbeat volume. autoSQL is eventually integrated back into GIMS.

**The rule that follows from that:** the transformation belongs in the SQL. If
you find yourself writing Python (or JS) that loops over fetched rows to
compute a total, group, or window, you have re-created the exact problem this
project exists to remove. Push it into the query.

## The target you are writing SQL for

- **Postgres** via GIMS's `PgRecordStore` (behind `GIMS_RDS_ENABLED`) is the
  real target. SQLite (`SqlRecordStore`) is the local/dev path — do not assume
  a feature exists on both. Window functions, `FILTER`, and JSONB behave
  differently or not at all on SQLite; say which store a query targets.
- GIMS owns the ledger: `LedgerRecord` (history) and `UserRequest` /
  `Proposal` / `ProposalItem` (intent), behind an append-only, HMAC-chained
  compliance trail. **autoSQL reads these. It never writes them.** No generated
  `UPDATE`, `DELETE`, or `TRUNCATE` against those tables, ever.
- Heartbeats are "Firehose" volume: high rate, mostly byte-identical repeats.
  The stated strategy is **collapse, never sample**, and **backpressure widens
  the window; it never drops**. A transformation that throws rows away to go
  faster is wrong even when it is faster.

## Reading the context repos

GUTS and GIMS-Project are private. `gh` is not installed and WebFetch is
unauthenticated (it 404s), so read them with **git** — `git ls-remote`, or clone
and read locally. `GUTS/proposals/guts_enterprise.md` is the design source for
the facts above.

## Conventions

Follow the conventions already in GIMS and GUTS rather than inventing a second
set — this code is going back into GIMS. If you genuinely need a new pattern,
ask before introducing it.

## What "done" means at this stage

Not "it compiles" and not "the tests pass". A build stage here ends with **the
generated SQL and the rows it produced on a known fixture**, so the next stage
has a number to check rather than a promise. If you changed how a value is
computed, show the value before and after.
