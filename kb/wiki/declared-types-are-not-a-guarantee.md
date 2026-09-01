# A declared field type is not a guarantee about stored content

**Status:** finding, from T-7 · **Recorded:** 2026-09-01 · **Evidence:** `spikes/T-7/FINDINGS.md` ·
**Supersedes nothing; sharpens T-1 `f3` §3.6 (hazard H3)**

## The finding

**Six of GIMS's seven `put_record` write paths perform no schema validation at all.** Only the noun
workbench's create/update route and the CSV/XLSX bulk import validate — and those two do block
properly, which was checked rather than assumed.

So `noun_types.json` describes what a field is *supposed* to hold. It does not describe what is
*in* it.

## The observable proof

`Glove.size` is declared `type: float` and contains:

```
"lmao im a changling"   "3 more boss"   "omg it works"   "I cant believe it!!"
```

Nine rows. Someone typing into a form to see whether it worked, August 2025.

**The obvious explanation was tested and is wrong.** The schema was *not* retyped afterwards: git
shows `Glove.size` has been `float` since **2025-05-30**, three months before the rows. The schema
did not move; the write did not check.

**Which of the six paths wrote them cannot be determined** — the rows carry no provenance, and the
project's verb log records test runs rather than noun writes and starts two months later. That is
recorded as a limit, not papered over.

## Why it matters to autoSQL

**Hazard H3, made concrete twice over.** T-1 `f3` §3.6 contemplated per-path expression indexes
typed by the declared type. On real data that statement fails:

```sql
CREATE INDEX ... ON instances (((data->>'size')::float8));
-- ERROR: invalid input syntax for type double precision
```

There are now **two independent witnesses in two collections from two mechanisms**: these nine rows
(a `float` field holding prose) and T-1 §D.6.2's `$.payload.blocked_since` (a number on 315 rows,
an ISO date on 9). The hazard is not an edge case.

## How to apply it

- **Never assume a `CREATE INDEX ... ::float8` will succeed** because the schema says the field is a
  number. Build it guarded (a partial index over `jsonb_typeof(...) = 'number'`), or expect the
  failure and handle it.
- **Do not use declared types to decide what is safe to compile.** Use them to decide what to
  *attempt*, and let the runtime's own coercion rules — which handle a non-numeric string by
  returning null on both engines, in agreement — decide the answer.
- **When a design needs a type guarantee, it has to create one**, not inherit one.

## What this does NOT say

- It says nothing about the Postgres path — this was the SQLite tenant project.
- It does not claim the unvalidated paths are a vulnerability. Whether they are user-facing was
  not traced; if that matters it is a GIMS question and its own ticket.
- **Nothing in GIMS was changed.** Evan's GA-9 Q3 park stands.
